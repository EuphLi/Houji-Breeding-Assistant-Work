import { message } from 'ant-design-vue'
import { handleChatError } from '@/utils/errorHandler'
import { unref } from 'vue'

/**
 * Process a streaming response from the server
 * @param {Response} response - The fetch response object
 * @param {Function} onChunk - Callback function for each parsed JSON chunk. Return true to stop processing.
 */
const processStreamResponse = async (response, onChunk) => {
  if (!response || !response.body) {
    console.warn('Invalid response or missing body for stream processing')
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let stopProcessing = false

  try {
    while (!stopProcessing) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        const trimmedLine = line.trim()
        if (trimmedLine) {
          try {
            const chunk = JSON.parse(trimmedLine)
            if (onChunk && onChunk(chunk)) {
              stopProcessing = true
              break
            }
          } catch (e) {
            console.warn('Failed to parse stream chunk JSON:', e, 'Line:', trimmedLine)
          }
        }
      }
    }

    if (!stopProcessing && buffer.trim()) {
      try {
        const chunk = JSON.parse(buffer.trim())
        if (onChunk) {
          onChunk(chunk)
        }
      } catch (e) {
        console.warn('Failed to parse final stream chunk JSON:', e)
      }
    }
  } finally {
    try {
      reader.releaseLock()
    } catch {
      // Ignore errors on releasing lock
    }
  }
}

const contentToText = (content) => {
  if (content == null) return ''
  if (typeof content === 'string') return content

  if (Array.isArray(content)) {
    return content
      .map((item) => {
        if (typeof item === 'string') return item
        if (item && typeof item === 'object') {
          return item.text || item.content || ''
        }
        return String(item ?? '')
      })
      .join('')
  }

  if (typeof content === 'object') {
    try {
      return JSON.stringify(content, null, 2)
    } catch {
      return String(content)
    }
  }

  return String(content)
}

const ensureOnGoingMsgChunks = (threadState) => {
  if (!threadState.onGoingConv) {
    threadState.onGoingConv = { msgChunks: {} }
  }

  if (!threadState.onGoingConv.msgChunks) {
    threadState.onGoingConv.msgChunks = {}
  }

  return threadState.onGoingConv.msgChunks
}

const resolveRequestId = (chunk, threadState) => {
  return chunk?.request_id || chunk?.meta?.request_id || threadState?.pendingRequestId || null
}

const getRuntimeState = (threadState, requestId) => {
  if (!threadState.__agentStreamRuntime || threadState.__agentStreamRuntime.requestId !== requestId) {
    threadState.__agentStreamRuntime = {
      requestId,
      toolMessageIndex: 0,
      toolResultIndex: 0,
      currentToolMessageKey: null,

      // 如果旧渲染层仍然按 key 排序，zz-final-response 会自然排在 tool-call / tool-result 后面。
      finalResponseKey: requestId
        ? `${requestId}:zz-final-response`
        : `zz-final-response:${Date.now()}`,

      // 同一轮对话内的稳定展示顺序。
      nextStreamOrder: 0,
      messageOrders: {},

      // 关键新增：
      // final_response_delta 不再每个 token append 一个 chunk，
      // 而是累积到同一个 final response message。
      finalResponseText: ''
    }
  }

  return threadState.__agentStreamRuntime
}

const getMessageOrder = (runtime, messageKey) => {
  if (!runtime || !messageKey) return Number.MAX_SAFE_INTEGER

  if (runtime.messageOrders[messageKey] == null) {
    runtime.messageOrders[messageKey] = runtime.nextStreamOrder++
  }

  return runtime.messageOrders[messageKey]
}

const buildExtraMetadata = ({ msg = {}, requestId, status, runtime, messageKey, extra = {} }) => {
  const extraMetadata = {
    ...(msg.extra_metadata || {}),
    request_id: requestId,
    stream_status: status,
    ...extra
  }

  if (runtime && messageKey) {
    extraMetadata.stream_order = getMessageOrder(runtime, messageKey)
  }

  return extraMetadata
}

const getCurrentToolMessageKey = (runtime, requestId) => {
  if (!runtime.currentToolMessageKey) {
    runtime.currentToolMessageKey = `${requestId}:tool-call:${runtime.toolMessageIndex++}`
  }

  return runtime.currentToolMessageKey
}

const getTopLevelToolCalls = (msg = {}) => {
  if (Array.isArray(msg.tool_calls)) return msg.tool_calls
  if (Array.isArray(msg.additional_kwargs?.tool_calls)) return msg.additional_kwargs.tool_calls
  return []
}

const normalizeInitMessage = (chunk, requestId, runtime, initMessageKey) => {
  const msg = chunk.msg || {}

  return {
    ...msg,
    id: msg?.id || initMessageKey,
    type: msg?.type || 'human',
    role: msg?.role || 'user',
    content: contentToText(msg?.content),
    extra_metadata: buildExtraMetadata({
      msg,
      requestId,
      status: chunk.status || 'init',
      runtime,
      messageKey: initMessageKey
    })
  }
}

const normalizeToolCallDeltaMessage = (chunk, requestId, runtime, toolMessageKey) => {
  const msg = chunk.msg || {}

  return {
    ...msg,
    id: toolMessageKey,
    type: msg.type || 'AIMessageChunk',
    role: msg.role || 'assistant',
    content: contentToText(msg.content),
    extra_metadata: buildExtraMetadata({
      msg,
      requestId,
      status: chunk.status,
      runtime,
      messageKey: toolMessageKey
    })
  }
}

const normalizeToolCallMessage = (chunk, requestId, runtime, toolMessageKey) => {
  const msg = chunk.msg || {}
  const toolCalls = getTopLevelToolCalls(msg)

  return {
    ...msg,
    id: toolMessageKey,
    type: 'ai',
    role: msg.role || 'assistant',
    content: contentToText(msg.content),
    tool_calls: toolCalls,
    extra_metadata: buildExtraMetadata({
      msg,
      requestId,
      status: chunk.status,
      runtime,
      messageKey: toolMessageKey
    })
  }
}

const resolveToolResultIdentity = (chunk, requestId, runtime) => {
  const msg = chunk.msg || {}
  const toolCallId = msg.tool_call_id || msg.additional_kwargs?.tool_call_id || msg.id
  const resultIndex = runtime.toolResultIndex++
  const resultKey = `${requestId}:tool-result:${toolCallId || resultIndex}`

  return {
    toolCallId,
    resultKey
  }
}

const normalizeToolResultMessage = (chunk, requestId, runtime, resultKey, toolCallId) => {
  const msg = chunk.msg || {}
  const responseText = contentToText(chunk.response ?? msg.content)

  return {
    ...msg,
    id: msg.id || resultKey,
    type: 'tool',
    role: msg.role || 'tool',
    content: responseText,
    tool_call_id: toolCallId,
    name: msg.name || msg.tool_name || msg.additional_kwargs?.name,
    extra_metadata: buildExtraMetadata({
      msg,
      requestId,
      status: chunk.status,
      runtime,
      messageKey: resultKey
    })
  }
}

const normalizeFinalResponseMessage = (
  chunk,
  requestId,
  runtime,
  finalResponseKey,
  contentOverride
) => {
  const msg = chunk.msg || {}
  const responseText =
    contentOverride !== undefined ? contentOverride : contentToText(chunk.response ?? msg.content)

  return {
    ...msg,
    id: finalResponseKey,
    type: 'ai',
    role: msg.role || 'assistant',
    content: responseText,
    extra_metadata: buildExtraMetadata({
      msg,
      requestId,
      status: chunk.status,
      runtime,
      messageKey: finalResponseKey,
      extra: {
        is_final_response: true
      }
    })
  }
}

const appendChunkToMessage = (threadState, messageKey, msg) => {
  const msgChunks = ensureOnGoingMsgChunks(threadState)

  if (!msgChunks[messageKey]) {
    msgChunks[messageKey] = []
  }

  msgChunks[messageKey].push(msg)
}

const replaceMessageChunks = (threadState, messageKey, msg) => {
  const msgChunks = ensureOnGoingMsgChunks(threadState)
  msgChunks[messageKey] = [msg]
}

export function useAgentStreamHandler({
  getThreadState,
  processApprovalInStream,
  currentAgentId,
  supportsFiles,
  streamSmoother
}) {
  const debugPrefix = '[AgentStateDebug]'

  /**
   * Process a single stream chunk based on its status
   * @param {Object} chunk - The parsed JSON chunk
   * @param {String} threadId - The current thread ID
   * @returns {Boolean} - Returns true if processing should stop, e.g. error, finished, interrupted
   */
  const handleStreamChunk = (chunk, threadId) => {
    const { status, msg, request_id, message: chunkMessage, error_message: errorMessage } = chunk
    const displayMessage = chunkMessage || errorMessage
    const threadState = getThreadState(threadId)

    if (!threadState) return false

    const requestId = resolveRequestId(chunk, threadState)
    const runtime = requestId ? getRuntimeState(threadState, requestId) : null

    switch (status) {
      case 'init':
        {
          const resolvedRequestId = request_id || threadState.pendingRequestId

          if (resolvedRequestId) {
            delete threadState.__agentStreamRuntime

            const initRuntime = getRuntimeState(threadState, resolvedRequestId)
            const initMessageKey = resolvedRequestId

            threadState.pendingRequestId = resolvedRequestId

            replaceMessageChunks(
              threadState,
              initMessageKey,
              normalizeInitMessage(chunk, resolvedRequestId, initRuntime, initMessageKey)
            )
          }
        }

        threadState.replyLoadingVisible = true
        return false

      case 'loading':
        if (msg?.id) {
          // loading 通常是旧协议或临时状态，保留原逻辑。
          if (streamSmoother) {
            streamSmoother.pushChunk(msg, threadId)
          } else {
            appendChunkToMessage(threadState, msg.id, msg)
          }
        }
        return false

      case 'tool_call_delta':
        if (runtime && requestId) {
          streamSmoother?.flushThread(threadId)

          const toolMessageKey = getCurrentToolMessageKey(runtime, requestId)

          appendChunkToMessage(
            threadState,
            toolMessageKey,
            normalizeToolCallDeltaMessage(chunk, requestId, runtime, toolMessageKey)
          )

          threadState.replyLoadingVisible = true
        }
        return false

      case 'tool_call':
        if (runtime && requestId) {
          streamSmoother?.flushThread(threadId)

          const toolMessageKey = getCurrentToolMessageKey(runtime, requestId)

          replaceMessageChunks(
            threadState,
            toolMessageKey,
            normalizeToolCallMessage(chunk, requestId, runtime, toolMessageKey)
          )

          threadState.replyLoadingVisible = true
        }
        return false

      case 'tool_result':
        if (runtime && requestId) {
          streamSmoother?.flushThread(threadId)

          const { toolCallId, resultKey } = resolveToolResultIdentity(chunk, requestId, runtime)
          const toolResult = normalizeToolResultMessage(
            chunk,
            requestId,
            runtime,
            resultKey,
            toolCallId
          )

          replaceMessageChunks(threadState, resultKey, toolResult)

          runtime.currentToolMessageKey = null
          threadState.replyLoadingVisible = true
        }
        return false

      case 'final_response_start':
        if (runtime) {
          streamSmoother?.flushThread(threadId)
          runtime.currentToolMessageKey = null

          // 新一段最终回答开始时清空累积文本，避免 resume 或连续 run 污染。
          runtime.finalResponseText = ''

          // 提前分配最终回答的顺序。
          getMessageOrder(runtime, runtime.finalResponseKey)

          threadState.replyLoadingVisible = true
        }
        return false

      case 'final_response_delta':
        if (runtime && requestId) {
          const deltaMessage = normalizeFinalResponseMessage(
            chunk,
            requestId,
            runtime,
            runtime.finalResponseKey
          )

          const deltaText = contentToText(deltaMessage.content)
          runtime.finalResponseText = `${runtime.finalResponseText || ''}${deltaText}`

          const finalMessage = normalizeFinalResponseMessage(
            chunk,
            requestId,
            runtime,
            runtime.finalResponseKey,
            runtime.finalResponseText
          )

          // 关键修改：
          // 以前是 appendChunkToMessage，每个 token 都追加一个 chunk。
          // 现在固定只有一个 final response chunk，并持续替换它。
          // 这样可以降低 MessageProcessor / displayItems / 工具卡片的无意义刷新。
          replaceMessageChunks(threadState, runtime.finalResponseKey, finalMessage)

          threadState.replyLoadingVisible = true
        }
        return false

      case 'final_response':
        if (runtime && requestId) {
          streamSmoother?.flushThread(threadId)

          const finalMessage = normalizeFinalResponseMessage(
            chunk,
            requestId,
            runtime,
            runtime.finalResponseKey
          )

          runtime.finalResponseText = contentToText(finalMessage.content)

          replaceMessageChunks(threadState, runtime.finalResponseKey, finalMessage)

          threadState.replyLoadingVisible = true
        }
        return false

      case 'final_response_end':
        streamSmoother?.flushThread(threadId)
        threadState.replyLoadingVisible = false
        return false

      case 'internal_message':
        return false

      case 'error':
        streamSmoother?.flushThread(threadId)
        handleChatError({ message: displayMessage }, 'stream')

        if (threadState) {
          threadState.isStreaming = false
          threadState.replyLoadingVisible = false
          threadState.pendingRequestId = null

          if (threadState.streamAbortController) {
            threadState.streamAbortController.abort()
            threadState.streamAbortController = null
          }
        }
        return true

      case 'ask_user_question_required':
      case 'human_approval_required':
        streamSmoother?.flushThread(threadId)
        threadState.replyLoadingVisible = false

        console.log(`${debugPrefix}[approval_required]`, {
          threadId,
          currentAgentId: unref(currentAgentId)
        })

        return processApprovalInStream(chunk, threadId, unref(currentAgentId))

      case 'agent_state':
        console.log(`${debugPrefix}[agent_state_chunk]`, {
          threadId,
          supportsFiles: unref(supportsFiles),
          currentAgentId: unref(currentAgentId),
          hasAgentState: !!chunk.agent_state,
          todoCount: Array.isArray(chunk.agent_state?.todos) ? chunk.agent_state.todos.length : 0,
          fileCount: chunk.agent_state?.files ? Object.keys(chunk.agent_state.files).length : 0,
          artifactCount: Array.isArray(chunk.agent_state?.artifacts)
            ? chunk.agent_state.artifacts.length
            : 0
        })

        if (chunk.agent_state) {
          console.log(`${debugPrefix}[agent_state_apply]`, {
            threadId,
            todos: chunk.agent_state?.todos || [],
            files: chunk.agent_state?.files || {},
            artifacts: chunk.agent_state?.artifacts || []
          })

          threadState.agentState = chunk.agent_state
        } else {
          console.warn(`${debugPrefix}[agent_state_skip]`, {
            reason: 'empty_state',
            supportsFiles: unref(supportsFiles),
            hasAgentState: !!chunk.agent_state,
            currentAgentId: unref(currentAgentId),
            threadId
          })
        }

        return false

      case 'finished':
        streamSmoother?.flushThread(threadId)

        if (threadState) {
          threadState.isStreaming = false
          threadState.replyLoadingVisible = false
          threadState.pendingRequestId = null
          delete threadState.__agentStreamRuntime

          console.log(`${debugPrefix}[finished]`, {
            threadId,
            currentAgentId: unref(currentAgentId),
            hasThreadAgentState: !!threadState.agentState,
            supportsFiles: unref(supportsFiles)
          })

          if (unref(supportsFiles) && threadState.agentState) {
            console.log(
              `[AgentState|Final] ${new Date().toLocaleTimeString()}.${new Date().getMilliseconds()}`,
              {
                threadId,
                todos: threadState.agentState?.todos || [],
                files: threadState.agentState?.files || {},
                artifacts: threadState.agentState?.artifacts || []
              }
            )
          }
        }

        return true

      case 'interrupted':
        streamSmoother?.flushThread(threadId)

        console.warn(`${debugPrefix}[interrupted]`, {
          threadId,
          message: displayMessage,
          currentAgentId: unref(currentAgentId)
        })

        if (threadState) {
          threadState.isStreaming = false
          threadState.replyLoadingVisible = false
          threadState.pendingRequestId = null
          delete threadState.__agentStreamRuntime
        }

        if (displayMessage) {
          message.info(displayMessage)
        }

        return true

      case 'warning':
        if (displayMessage) {
          message.warning(displayMessage)
        }
        return false

      default:
        return false
    }
  }

  /**
   * Process the full agent stream response
   * @param {Response} response - The fetch response
   * @param {String} threadId - The thread ID
   * @param {Function} [onChunk] - Optional callback for each chunk, e.g. for logging
   */
  const handleAgentResponse = async (response, threadId, onChunk = null) => {
    console.log(`${debugPrefix}[stream_start]`, {
      threadId,
      currentAgentId: unref(currentAgentId),
      supportsFiles: unref(supportsFiles)
    })

    await processStreamResponse(response, (chunk) => {
      if (chunk?.status && chunk.status !== 'loading') {
        console.log(`${debugPrefix}[chunk_status]`, {
          threadId,
          status: chunk.status,
          requestId: chunk.request_id
        })
      }

      if (onChunk) onChunk(chunk)

      return handleStreamChunk(chunk, threadId)
    })

    console.log(`${debugPrefix}[stream_end]`, {
      threadId,
      currentAgentId: unref(currentAgentId)
    })
  }

  return {
    handleStreamChunk,
    handleAgentResponse
  }
}