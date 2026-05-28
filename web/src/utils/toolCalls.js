export const asArray = (value) => {
  return Array.isArray(value) ? value : []
}

export const parseMaybeJson = (value) => {
  if (!value) return value

  if (typeof value === 'string') {
    try {
      return JSON.parse(value)
    } catch {
      return value
    }
  }

  return value
}

export const getToolName = (toolCall) => {
  return (
    toolCall?.name ||
    toolCall?.tool_name ||
    toolCall?.toolName ||
    toolCall?.function?.name ||
    toolCall?.function_call?.name ||
    toolCall?.tool?.name ||
    toolCall?.tool_call?.name ||
    toolCall?.metadata?.tool_name ||
    toolCall?.metadata?.name ||
    ''
  ).toLowerCase()
}

export const getToolResultContent = (toolCall) => {
  return (
    toolCall?.tool_call_result?.content ||
    toolCall?.toolCallResult?.content ||
    toolCall?.result?.content ||
    toolCall?.result ||
    toolCall?.output ||
    toolCall?.content ||
    ''
  )
}

export const normalizeToolCall = (toolCall) => {
  return {
    ...toolCall,
    args: parseMaybeJson(toolCall?.args || toolCall?.function?.arguments || toolCall?.arguments),
    tool_call_result:
      toolCall?.tool_call_result ||
      toolCall?.toolCallResult || {
        content: getToolResultContent(toolCall)
      }
  }
}

export const isKnownToolCall = (value) => {
  if (!value || typeof value !== 'object') return false

  const name = getToolName(value)

  if (
    name === 'tavily_search' ||
    name === 'pubmed_search' ||
    name === 'query_knowledge_graph'
  ) {
    return true
  }

  if (
    name.includes('tavily') ||
    name.includes('pubmed') ||
    name.includes('knowledge_graph')
  ) {
    return true
  }

  const content = getToolResultContent(value)

  if (typeof content === 'string') {
    return (
      content.includes('"results"') ||
      content.includes('"triples"') ||
      content.includes('tavily_search') ||
      content.includes('pubmed_search') ||
      content.includes('query_knowledge_graph')
    )
  }

  if (content && typeof content === 'object') {
    return Array.isArray(content.results) || Array.isArray(content.triples)
  }

  return false
}

export const findToolCallsDeep = (root, maxDepth = 8) => {
  const result = []
  const seenObjects = new WeakSet()

  const walk = (value, depth) => {
    if (!value || depth > maxDepth) return

    if (typeof value !== 'object') return

    if (seenObjects.has(value)) return
    seenObjects.add(value)

    if (Array.isArray(value)) {
      value.forEach((item) => walk(item, depth + 1))
      return
    }

    if (isKnownToolCall(value)) {
      result.push(normalizeToolCall(value))
    }

    Object.values(value).forEach((child) => {
      walk(child, depth + 1)
    })
  }

  walk(root, 0)

  const seenKeys = new Set()

  return result.filter((toolCall, index) => {
    const key =
      toolCall?.id ||
      toolCall?.tool_call_id ||
      toolCall?.toolCallId ||
      toolCall?.call_id ||
      `${getToolName(toolCall)}-${JSON.stringify(getToolResultContent(toolCall)).slice(0, 120)}-${index}`

    if (seenKeys.has(key)) return false

    seenKeys.add(key)
    return true
  })
}

export const getMessageToolCalls = (message) => {
  if (!message) return []

  const directToolCalls = [
    ...asArray(message.tool_calls),
    ...asArray(message.toolCalls),
    ...asArray(message.response_metadata?.tool_calls),
    ...asArray(message.response_metadata?.toolCalls),
    ...asArray(message.metadata?.tool_calls),
    ...asArray(message.metadata?.toolCalls),
    ...asArray(message.meta?.tool_calls),
    ...asArray(message.meta?.toolCalls)
  ]

  const directToolResults = [
    ...asArray(message.tool_call_results),
    ...asArray(message.toolCallResults),
    ...asArray(message.response_metadata?.tool_call_results),
    ...asArray(message.response_metadata?.toolCallResults),
    ...asArray(message.metadata?.tool_call_results),
    ...asArray(message.metadata?.toolCallResults),
    ...asArray(message.meta?.tool_call_results),
    ...asArray(message.meta?.toolCallResults)
  ]

  const normalizedDirectCalls = directToolCalls.map(normalizeToolCall)

  const normalizedDirectResults = directToolResults.map((result, index) =>
    normalizeToolCall({
      id: result?.id || result?.tool_call_id || result?.toolCallId || `tool-result-${index}`,
      tool_call_id: result?.tool_call_id || result?.toolCallId,
      name: result?.name || result?.tool_name || result?.toolName,
      tool_name: result?.name || result?.tool_name || result?.toolName,
      tool_call_result:
        result?.tool_call_result ||
        result?.toolCallResult || {
          content: getToolResultContent(result)
        }
    })
  )

  const roleToolResult =
    message.role === 'tool' && message.content
      ? [
          normalizeToolCall({
            id: message.tool_call_id || message.id,
            tool_call_id: message.tool_call_id,
            name: message.name || message.tool_name || message.toolName,
            tool_name: message.name || message.tool_name || message.toolName,
            tool_call_result: {
              content: message.content
            }
          })
        ]
      : []

  const deepFound = findToolCallsDeep(message)

  return [
    ...normalizedDirectCalls,
    ...normalizedDirectResults,
    ...roleToolResult,
    ...deepFound
  ]
}

export const getConversationMessages = (conv) => {
  return (
    conv?.messages ||
    conv?.messageList ||
    conv?.chat_messages ||
    conv?.chatMessages ||
    conv?.items ||
    conv?.message_list ||
    []
  )
}

export const getConversationToolCalls = (conv) => {
  const fromMessages = getConversationMessages(conv).flatMap((message) => getMessageToolCalls(message))
  const fromWholeConv = findToolCallsDeep(conv)

  return [...fromMessages, ...fromWholeConv]
}