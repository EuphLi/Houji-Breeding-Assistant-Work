import { agentApi, threadApi } from './agent_api'

// 这个文件在链路中的作用：
// 1. 为育种工作台创建 YuXi Thread 和 Agent Run；
// 2. 轮询 Run 状态与消息历史；
// 3. 把“后端运行状态 + 历史消息 + 工具链”整理成前端可直接展示的快照。
//
// 可以把它理解为“工作台和 YuXi Agent Run 之间的适配层”。
// 页面本身不直接拼最终答案，而是通过这里持续读取真实 history。

const TERMINAL_RUN_STATUSES = new Set([
  'completed',
  'completed_with_warnings',
  'succeeded',
  'failed',
  'cancelled',
  'interrupted',
  'error',
  'finished'
])
const FORMAL_OMICS_BREEDING_TOOL = 'omics_breeding_analysis_run'
const USER_VISIBLE_TOOL_NAMES = new Set([FORMAL_OMICS_BREEDING_TOOL])
const POLL_INTERVAL_MS = 2000
export const NORMAL_WAIT_MS = 180000
export const HARD_TIMEOUT_MS = 420000

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

const hasCompletedResultContent = ({ frontendPayload = null, markdown = '' } = {}) => {
  if (frontendPayload) return true
  const normalizedMarkdown = typeof markdown === 'string' ? markdown.trim() : ''
  return normalizedMarkdown.includes('分析流程已完成')
}

// 这个函数在每次轮询 history 时被调用。
// 输入是 YuXi history 中的一条 message；输出是尽量稳定的纯文本内容。
// 它所处的步骤是“前端从真实历史消息里恢复可展示文本”。
// 这里不做智能分析，只解决消息结构可能是字符串或富文本数组的问题。
// Agent history 里消息内容的结构并不稳定，可能是纯字符串，也可能是富文本数组。
// 工作台最终展示必须尽量从真实历史消息中恢复，而不是依赖前端手写模板。
const extractMessageContent = (message) => {
  if (!message) return ''
  if (typeof message.content === 'string') return message.content.trim()
  if (Array.isArray(message.content)) {
    return message.content
      .map((item) => {
        if (typeof item === 'string') return item
        if (typeof item?.text === 'string') return item.text
        return ''
      })
      .filter(Boolean)
      .join('\n')
      .trim()
  }
  return ''
}

const tryParseJson = (value = '') => {
  if (typeof value !== 'string' || !value.trim()) return null

  try {
    return JSON.parse(value)
  } catch {
    // 有些 tool message 可能在 JSON 外层包了说明文字，这里做一个保守兜底。
  }

  const firstBrace = value.indexOf('{')
  const lastBrace = value.lastIndexOf('}')
  if (firstBrace < 0 || lastBrace <= firstBrace) return null

  try {
    return JSON.parse(value.slice(firstBrace, lastBrace + 1))
  } catch {
    return null
  }
}

const extractJsonPayloadFromMessage = (message) => {
  if (!message) return null

  const content = extractMessageContent(message)
  const parsedFromContent = tryParseJson(content)
  if (parsedFromContent) return parsedFromContent

  if (typeof message.content === 'object' && !Array.isArray(message.content)) {
    return message.content
  }

  if (typeof message.output === 'object' && message.output) {
    return message.output
  }

  if (typeof message.result === 'object' && message.result) {
    return message.result
  }

  return null
}

const extractFrontendPayloadFromHistory = (history = []) => {
  for (let index = history.length - 1; index >= 0; index -= 1) {
    const message = history[index]
    const payload = extractJsonPayloadFromMessage(message)

    if (payload?.frontend_payload) {
      return payload.frontend_payload
    }

    if (payload?.frontendPayload) {
      return payload.frontendPayload
    }

    if (payload?.schema_version === 'omics_frontend_payload.v1') {
      return payload
    }
  }

  return null
}

const extractMessageRequestId = (message = null) => {
  if (!message || typeof message !== 'object') return ''
  return (
    message?.request_id ||
    message?.extra_metadata?.request_id ||
    message?.metadata?.request_id ||
    ''
  )
}

const filterHistoryByRequestId = (history = [], requestId = '') => {
  const normalizedRequestId = typeof requestId === 'string' ? requestId.trim() : ''
  if (!normalizedRequestId) return history

  const matched = history.filter((message) => extractMessageRequestId(message) === normalizedRequestId)
  return matched.length > 0 ? matched : history
}

const pushUniqueToolName = (target, seen, name, inferred = false) => {
  if (typeof name !== 'string') return
  const normalized = name.trim()
  if (!normalized || seen.has(normalized)) return
  seen.add(normalized)
  target.push({ name: normalized, inferred })
}

// 这个函数在读取 `getAgentHistory` 结果后被调用。
// 输入是后端 history 响应；输出是统一的消息数组。
// 它在链路中的作用是屏蔽不同 history 返回结构，方便后续工具链和最终消息提取。
const normalizeHistoryResponse = (historyResponse) => {
  if (Array.isArray(historyResponse)) return historyResponse
  if (Array.isArray(historyResponse?.history)) return historyResponse.history
  return []
}

/** 工具调用链提取
 * 前端可以展示 Agent 可能调用过哪些 breeding/smoke 工具。
 * TODO：应优化为每一句的输出都要注明来源
 * */
// 这个函数在轮询过程中从 history 提取工具调用线索。
// 输入是 thread 的完整消息历史；输出是：
// - toolCalls: 后端显式记录的 tool call
// - actualToolChain: history 中明确出现过的工具
// - actualToolChain: history 中明确出现过的工具
//
// 它处于“前端解释 Agent 在干什么”的步骤，不参与业务决策。
// 真正的工具执行发生在后端 Tool Registry 和 tools.py 中，这里只负责还原链路。
const extractToolDataFromHistory = (history = []) => {
  const toolCalls = []
  const actualToolChain = []
  const actualSeen = new Set()

  for (const item of history) {
    if (!item) continue

    if (Array.isArray(item.tool_calls)) {
      for (const toolCall of item.tool_calls) {
        if (!toolCall?.name) continue
        toolCalls.push(toolCall)
        pushUniqueToolName(actualToolChain, actualSeen, toolCall.name)
      }
    }

    pushUniqueToolName(actualToolChain, actualSeen, item.tool_name)
    pushUniqueToolName(actualToolChain, actualSeen, item.name)
    pushUniqueToolName(actualToolChain, actualSeen, item?.tool_call?.name)
  }

  return { toolCalls, actualToolChain }
}

/** 偏诊断性用途  从 runState.tools / steps / events 中尝试提取工具名
 *  运行过程中可以看到当前 run 可能经过了哪些步骤。
 * */
// 这个函数在轮询 `getAgentRun` 后被调用。
// 输入是 Run 当前状态对象；输出是 Run 视角下观察到的工具链。
// getAgentRun 更适合看“任务是否还在跑、当前有哪些步骤”，
// 但最终自然语言内容通常不在这里，所以它只是诊断信息来源之一。
const extractToolDataFromRunState = (runState) => {
  const actualToolChain = []
  const actualSeen = new Set()
  const candidates = []

  if (Array.isArray(runState?.tools)) candidates.push(...runState.tools)
  if (Array.isArray(runState?.steps)) candidates.push(...runState.steps)
  if (Array.isArray(runState?.events)) candidates.push(...runState.events)

  for (const item of candidates) {
    if (!item) continue
    pushUniqueToolName(actualToolChain, actualSeen, item.tool_name)
    pushUniqueToolName(actualToolChain, actualSeen, item.name)
    pushUniqueToolName(actualToolChain, actualSeen, item?.tool?.name)
  }

  return actualToolChain
}

/** 决定页面最终展示哪条消息
 * */
// 这个函数在每次轮询 history 后被调用。
// 输入是 history；输出是最适合页面渲染的最终消息。
// 它在链路中的位置是“从真实历史消息里选出最后该展示哪条内容”。
// 优先 assistant、回退 tool，是因为最终建议应尽量来自智能体整合后的回答，
// 但若最后只落了 tool 文本，工作台仍需要把真实结果展示出来。
const extractFinalRenderableMessage = (history = []) => {
  // 优先取 assistant 最终消息；如果模型最后只吐出了 tool 消息，再回退到 tool。
  const aiMessages = history.filter((item) => ['ai', 'assistant'].includes(item?.type))
  for (let index = aiMessages.length - 1; index >= 0; index -= 1) {
    const message = aiMessages[index]
    if (extractMessageContent(message)) {
      return { message, source: 'assistant' }
    }
  }

  const toolMessages = history.filter((item) => item?.type === 'tool')
  for (let index = toolMessages.length - 1; index >= 0; index -= 1) {
    const message = toolMessages[index]
    if (extractMessageContent(message)) {
      return { message, source: 'tool' }
    }
  }

  return { message: null, source: '' }
}

// 这个函数在每轮轮询后被调用。
// 输入是 threadId、runId、runState、history 和计时信息；输出是前端统一快照。
// 它处于“前端状态整合”这一步，把 Run 状态、history 最终消息、工具链和诊断字段放在一起，整理成页面可展示结果。
// 这里不生成业务结论，只是把后端真实结果整理成页面需要的数据形状。
export const buildRunSnapshot = ({
  // 函数的输入来自轮询
  threadId,
  runId,
  requestId = '', // 当前前端提交的ID
  runState,
  history, // getAgentHistory(threadId) 返回的消息历史
  startedAt, // 开始时间
  pollingCount, // 轮询次数
  softTimeoutReached = false,
  hardTimeoutReached = false
}) => {
  // 按 requestId 过滤 history，避免旧结果混用
  const scopedHistory = filterHistoryByRequestId(history, requestId)
  // Run 状态只告诉前端“任务还在不在跑”，真正可展示的自然语言内容通常在 history 里。
  // 因此这里把 runState 和 history 汇总成一个快照，最适合页面展示的最终文本消息供页面统一渲染。
  const finalRenderable = extractFinalRenderableMessage(scopedHistory)
  // 提取 frontendPayload（结构化字段）
  // 尝试从不同位置的 message 取结构化数据，兼容 YuXi history 里不同类型的消息结构
  const frontendPayload = extractFrontendPayloadFromHistory(scopedHistory)
  // 提取工具调用链
  const historyToolData = extractToolDataFromHistory(scopedHistory)
  const runStateToolChain = extractToolDataFromRunState(runState)
  const mergedToolChain = []
  const mergedSeen = new Set()
  const rawStatus = String(runState?.status || '').trim()
  // 决定 markdown 展示内容  优先级：frontendPayload.answer_markdown、assistant / tool 最终消息文本
  const markdown =
    frontendPayload?.answer_markdown || extractMessageContent(finalRenderable.message) || ''
  // 判断是否已有可展示结果：只要有 frontendPayload，就认为已有完成结果 / markdown 里包含“分析流程已完成”，也认为有完成结果。
  const hasRenderableOutput = Boolean(markdown)
  const hasCompletedResult = hasCompletedResultContent({
    frontendPayload,
    markdown
  })
  // 修正软超时和硬超时：如果已经有 markdown，就不再认为软超时/硬超时有效。
  const effectiveSoftTimeoutReached =
    softTimeoutReached && !TERMINAL_RUN_STATUSES.has(rawStatus) && !hasRenderableOutput
  const effectiveHardTimeoutReached =
    hardTimeoutReached && !TERMINAL_RUN_STATUSES.has(rawStatus) && !hasRenderableOutput
  // 修正 status
  const status =
    hasCompletedResult && !TERMINAL_RUN_STATUSES.has(rawStatus) ? 'completed' : rawStatus

  for (const item of [...runStateToolChain, ...historyToolData.actualToolChain]) {
    pushUniqueToolName(mergedToolChain, mergedSeen, item.name, item.inferred)
  }

  const lastHistoryMessage =
    scopedHistory.length > 0 ? scopedHistory[scopedHistory.length - 1] : null

  // 输出是页面可直接使用的 snapshot，即 Vue 页面里 syncResultFromPayload(snapshot) 接收的对象
  return {
    threadId,
    runId,
    requestId,
    status,
    runState,
    history: scopedHistory,
    finalMessage: finalRenderable.message,
    finalMessageSource: finalRenderable.source,
    toolCalls: historyToolData.toolCalls,
    toolChain: mergedToolChain,
    visibleToolChain: mergedToolChain.filter((item) => USER_VISIBLE_TOOL_NAMES.has(item.name)),
    frontendPayload,
    markdown,
    diagnostics: {
      threadId,
      runId,
      requestId,
      runStatus: status,
      elapsedSeconds: Math.floor((Date.now() - startedAt) / 1000),
      pollingCount,
      lastHistoryMessageRole: lastHistoryMessage?.type || '',
      parsedToolCalls: mergedToolChain.map((item) => item.name),
      softTimeoutReached: effectiveSoftTimeoutReached,
      hardTimeoutReached: effectiveHardTimeoutReached
    }
  }
}

// 这个函数在 createAgentRun 之前被调用，用来构造发给 Agent 的 query。
// 输入是性状、用户问题和多组学上下文；输出是一段带执行要求的工作台提示词。
// 这一步属于“前端把任务合同发给 Agent”，不是前端自己做生信分析。
// 其中关于 DOI、引用原句、边界声明的约束，是为了要求 Agent 只能基于 Tool 返回结果组织答案。
/**
 * 作用可以概括为：任务说明构造器
 * trait / question / context
 * → 组装成一段任务说明 query
 * → 传给 agentApi.createAgentRun()
 * 真正让后端走 direct route 的关键是 createAgentRun 的 meta.source / meta.preferred_tool*/
export const buildBreedingWorkbenchQuery = ({ trait, question, context = {} }) => {
  // 整理性状输入，如果用户没输入，就默认使用“黄酮相关”
  const trimmedTrait = (trait || '黄酮相关').trim() || '黄酮相关'
  // 整理用户问题，用户未输入时默认“给出一些育种建议”。
  const trimmedQuestion = (question || '给出一些育种建议').trim() || '给出一些育种建议'
  const dataDir =
    context.data_dir || '/mnt/yuxi-breeding-data/smoke_test_minimal/Si9g037800_smoke_test_minimal'

  const transcriptomeResultPath =
    context.transcriptome_result_path || `${dataDir}/significant_de_genes.tsv`
  const outputDir = context.output_dir || '/tmp/yuxi_runs/omics_breeding_analysis'

  // 返回值拼接成 Agent Query，把多个字符串拼成一段完整提示词
  return [
    `用户问题：${trimmedQuestion}`,
    '',
    `目标性状：${trimmedTrait}`,
    '',
    '请执行正式多组学育种分析流程。',
    '',
    `必须优先调用 ${FORMAL_OMICS_BREEDING_TOOL} 工具。`, // 这句话更多是给普通 Agent 链路看的“提示词约束”。现在真正让后端直达工具的关键是 createAgentRun() 里的 meta
    '',
    '调用工具时请使用以下参数：', // 这段 query 只是文本说明,后端 direct route 真正构造工具 payload 的地方在 chat_service.py
    `- trait=${trimmedTrait}`,
    `- question=${trimmedQuestion}`,
    `- transcriptome_result_path=${transcriptomeResultPath}`,
    '- literature_evidence_path 仅在用户明确提供已验证文献证据表时填写；否则留空。',
    `- evidence_pack_output_path=${outputDir}/omics_evidence_pack.json`,
    `- output_dir=${outputDir}`,
    '- use_llamaindex=false',
    '',
    '输出要求：',
    '- 使用工具返回的 answer_markdown 作为主要回答。',
    '- 请根据 trait 和候选组学结果构造文献检索；如文献工具不可用，不得编造 DOI 或 quoted_sentence。',
    '- frontend_payload 中的 citation、文献卡片、逐句来源追溯和 Guard 结果仅保留为结构化输出，不要重复写入正文。',
    '- 不要把 smoke_flavonoid_breeding_advice 作为正式多组学育种分析主线。',
    '- 不要编造 DOI。',
    '- 不要编造 quoted_sentence。',
    '- 不要声称已完成群体验证、湿实验或最终 KASP/CAPS 开发。'
  ].join('\n')
}

// legacy 兼容：新版 breeding-workbench 不再自动触发 repair。
/**
 * 作用是：当一次智能体回答不满足要求时，构造一段“让模型重新修正回答”的提示词。
 * 即不是第一次正式提交用的 query，而是以前用于“二次修复”的 query
 * 如果上一次回答缺字段 / 不合规
 * → 构造 repair query
 * → 要求模型基于已有 frontend_payload / guard_result / citations 重新组织答案
 * // legacy repair 兼容逻辑。
 * // 旧版本中，当前端检测到回答缺少 DOI / 群体验证建议 / 边界说明等内容时，
 * // 可能会构造 repair query 让模型基于已有 frontend_payload / guard_result / citations 重写答案。
 * // 新版 breeding-workbench 已经把正式结果生成收敛到 omics_breeding_analysis_run 内部，
 * // 因此该函数不再作为主链路自动触发，只保留兼容和调试用途。*/
export const buildRepairQuery = (missingLabels = []) => {
  // missingLabels 表示上一轮回答缺失的项目标签
  const suffix = missingLabels.length ? `当前缺失项：${missingLabels.join('、')}。` : ''

  return [
    '你刚才的回答未满足多组学育种分析工作台输出要求。',
    `请优先基于 ${FORMAL_OMICS_BREEDING_TOOL} 工具返回的 frontend_payload、guard_result 和 citations 重新组织最终回答。`,
    '不要写死固定基因、固定性状或固定术语；目标基因和目标性状必须来自工具返回的 Evidence Pack / frontend_payload。',
    '如果 guard_result 中存在 errors，请根据 errors 修正回答。',
    '如果 frontend_payload 中存在 literature_panel.cards，请使用其中的 DOI 和 quoted_sentence，不要自行编造 DOI 或引用原句。',
    '不得声称完成群体验证、湿实验验证或最终 KASP/CAPS 标记开发。',
    '请直接输出最终多组学育种分析结果，不要输出内部推理。',
    suffix
  ]
    .filter(Boolean) // 去掉空字符串
    .join('\n') // 把数组拼成多行文本
}

// 这个函数在用户点击“提交给智能体”或前端触发 repair 时被调用。
// 输入是 Agent 标识、性状、问题、上下文以及轮询回调；输出是最终运行快照。
// 它在整条链路中处于“工作台驱动 YuXi Agent Run”的核心步骤。
//
// 关键概念：
// - Thread 是对话容器：同一次工作台任务的历史消息、工具调用和最终回答都挂在这里。
// - Run 是这个 Thread 上的一次异步执行：每次 createAgentRun 都会产生新的 run_id。
// - getAgentRun 看“这次执行现在跑到哪了”，getAgentHistory 看“这条线程里已经落了哪些真实消息”。
//
// 为什么要轮询：
// 1. Agent Run 是异步的，可能持续较长时间；
// 2. 工具链和最终消息会逐步写入后端；
// 3. 页面需要持续刷新状态，而不是一次性等待。
export const runBreedingWorkbench = async ({
  agentId, // 当前默认智能体 ID。来自 BreedingWorkbenchView.vue 的 selectedAgentId。
  agentConfigId, // 当前默认智能体配置 ID。来自 selectedAgentConfigId。
  trait, // 页面性状输入，例如 黄酮相关、抗旱相关
  question, // 用户问题，例如 给出一些育种建议
  context = {}, // 左侧组学输入上下文，例如 genome.fa、metabolome_raw_3372.tsv、data_dir 等
  title = '育种工作台', // 创建 Thread 时使用的标题。
  normalWaitMs = NORMAL_WAIT_MS, // 软超时时间。超过这个时间还没有结果，就触发 onSoftTimeout。
  hardTimeoutMs = HARD_TIMEOUT_MS, // 硬超时时间。超过这个时间仍没有结果，就抛出超时错误。
  threadId: existingThreadId = '', // 如果外部传入已有 thread，就复用；否则新建。
  queryOverride = '', // 允许外部直接覆盖发送给 Agent 的 query。一般不用
  meta = {}, // 允许额外补充 metadata。
  onProgress = null, // 每次轮询拿到 snapshot 后，回调给页面。
  onSoftTimeout = null // 软超时时，回调给页面，让用户选择继续等待或停止。
}) => {
  // 校验 agentId / agentConfigId
  if (!agentId) {
    throw new Error('缺少可用智能体，请先在系统中配置默认智能体。')
  }
  if (!agentConfigId) {
    throw new Error('缺少可用智能体配置，请先为默认智能体设置可用配置。')
  }

  // 创建或复用 Thread，即一次对话/任务的容器，后续所有内容都会挂到这个 thread 上
  let threadId = existingThreadId
  if (!threadId) {
    // createThread 的作用：先为本次工作台任务创建一个 YuXi 对话线程。
    // 后续的 Run、历史消息、工具调用链和最终回答都会挂到这个 thread 上。
    const thread = await threadApi.createThread(agentId, title, {
      source: 'breeding-workbench',
      trait,
      agent_config_id: agentConfigId
    })
    threadId = thread?.id
  }
  // 创建失败直接抛错，回到 handleSubmit() 的 catch，页面显示错误
  if (!threadId) {
    throw new Error('创建育种工作台线程失败。')
  }

  /**
   * 告诉后端：这次育种工作台任务允许使用哪些工具。
   * */
  // 其中：const FORMAL_OMICS_BREEDING_TOOL = 'omics_breeding_analysis_run'
  const allowedTools = [FORMAL_OMICS_BREEDING_TOOL]
  const requestId = meta?.request_id || `breeding-workbench-${Date.now()}`

  // createAgentRun 的作用：告诉后端“在指定 thread 上启动一次异步 Agent Run”。
  // 这一步只负责创建任务，不会同步返回最终育种建议。
  // 其中：Run 是在 Thread 上启动的一次异步 Agent 执行。query 是给大模型/Agent 的任务说明。meta 是给后端保存的任务上下文和工具约束。
  const run = await agentApi.createAgentRun({
    // query 会构造一段发给 Agent 的任务说明
    query: queryOverride || buildBreedingWorkbenchQuery({ trait, question, context }),
    agent_config_id: agentConfigId,
    thread_id: threadId,
    // 前端创建 YuXi Agent Run，并在 meta 中声明这是 breeding-workbench 任务和首选正式工具：
    // 后端识别该 meta 后走固定业务入口，直接执行 omics_breeding_analysis_run。
    meta: {
      request_id: requestId,
      source: 'breeding-workbench',
      trait,
      question,
      breeding_context: context,
      // FIXME: allowedTools	Tool Registry / tools.py	允许哪些工具参与  但实际调用链要以后端 history / tool_calls 为准。
      // preferred_tool 指向当前正式多组学育种分析工具；后端 direct route 会据此进入固定业务入口。
      allowed_tools: allowedTools,
      preferred_tool: FORMAL_OMICS_BREEDING_TOOL,
      ...meta
    }
  })
  // createAgentRun() 成功后，后端会返回一个 run_id,前端之后就靠这个去查询目前执行的状态
  const runId = run?.run_id
  if (!runId) {
    throw new Error('创建育种工作台运行失败。')
  }

  // 初始化轮询状态
  let runState = null
  let history = []
  let pollingCount = 0
  let softTimeoutReached = false
  const startedAt = Date.now()

  // 这里使用轮询而不是一次性等待：
  // 1. Agent Run 是异步任务，可能持续数十秒到数分钟；
  // 2. 前端需要持续刷新工具调用链、运行状态和最终消息；
  // 3. getAgentRun 看任务状态，getAgentHistory 看真实输出内容，两者缺一不可。
  while (Date.now() - startedAt < hardTimeoutMs) {
    pollingCount += 1
    // getAgentRun 的作用：读取后端 Run 当前状态，例如 running / completed / failed。
    runState = await agentApi.getAgentRun(runId)
    // getAgentHistory 的作用：读取 thread 上已经落库的消息历史，最终展示内容以这里为准。
    const historyResponse = await agentApi.getAgentHistory(threadId)
    history = normalizeHistoryResponse(historyResponse)
    const status = String(runState?.status || '').trim()

    // 构建 snapshot：前端结果整理函数，把后端返回的信息整合成页面可以直接渲染的对象
    /**
     * 这就是上一层 BreedingWorkbenchView.vue 里：
     * syncResultFromPayload(snapshot, { submissionId })接收到的东西。
     * 所以 API 层和页面层之间的接口就是：snapshot
     * 完整关系是：
     * runBreedingWorkbench()
     *   每轮构建 snapshot
     *     ↓
     * onProgress(snapshot)
     *     ↓
     * BreedingWorkbenchView.vue
     *   syncResultFromPayload(snapshot)
     *     ↓
     * 页面更新状态 / 工具链 / 诊断信息 / markdown*/
    const snapshot = buildRunSnapshot({
      threadId,
      runId,
      requestId,
      runState,
      history,
      startedAt,
      pollingCount,
      softTimeoutReached,
      hardTimeoutReached: false
    })
    // 通过 onProgress 回传给页面
    if (typeof onProgress === 'function') {
      await onProgress(snapshot)
    }

    // 终态判断
    const normalizedSnapshotStatus = String(snapshot.status || '').trim().toLowerCase()
    if (TERMINAL_RUN_STATUSES.has(normalizedSnapshotStatus)) {
      // 最终结果来自 history，而不是前端自己拼接 markdown。
      // 这样可以保证页面展示的是后端真实落库的消息内容。
      return snapshot
    }

    // 软超时逻辑
    /**
     * 如果已经超过 normalWaitMs
     * 而且还没有 markdown
     * 也没有 frontendPayload
     * 而且还没触发过软超时
     * 就让页面弹出“继续等待 / 停止本次运行”
     * */
    if (
      Date.now() - startedAt >= normalWaitMs &&
      !softTimeoutReached &&
      !snapshot.markdown &&
      !snapshot.frontendPayload
    ) {
      softTimeoutReached = true
      if (typeof onSoftTimeout === 'function') {
        // 软超时：任务运行偏久，但仍允许用户继续等待或主动停止。
        // 硬超时：超过总时长上限，前端直接结束等待并报错。
        const decision = await onSoftTimeout(
          buildRunSnapshot({
            threadId,
            runId,
            requestId,
            runState,
            history,
            startedAt,
            pollingCount,
            softTimeoutReached: true,
            hardTimeoutReached: false
          })
        )
        if (decision === 'stop') {
          try {
            await agentApi.cancelAgentRun(runId)
          } catch {
            // ignore cancel failure and surface a stop message to the UI
          }
          throw new Error('已停止本次运行。')
        }
      }
    }

    await sleep(POLL_INTERVAL_MS)
  }

  // 硬超时逻辑：
  /**
   * 即使硬超时到了，如果 history 里已经有 markdown 或 frontendPayload，
   * 前端仍然接受这个结果，不再强行判失败。
   * 只有在：
   * 没有 markdown
   * 也没有 frontendPayload
   * 时才抛出“智能体执行时间过长”。
   * */
  const finalSnapshot = buildRunSnapshot({
    threadId,
    runId,
    requestId,
    runState,
    history,
    startedAt,
    pollingCount,
    softTimeoutReached,
    hardTimeoutReached: true
  })

  if (typeof onProgress === 'function') {
    await onProgress(finalSnapshot)
  }
  if (finalSnapshot.markdown || finalSnapshot.frontendPayload) {
    return finalSnapshot
  }
  // 硬超时只意味着前端停止等待，不代表后端 Run 一定已经异常结束。
  throw new Error('智能体执行时间过长，请检查后端 run 状态或重试。')
}

export const breedingWorkbenchApi = {
  runBreedingWorkbench,
  buildBreedingWorkbenchQuery,
  buildRepairQuery,
  NORMAL_WAIT_MS,
  HARD_TIMEOUT_MS
}

export default breedingWorkbenchApi
