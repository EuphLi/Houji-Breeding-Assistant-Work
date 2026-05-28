<template>
  <div class="refs" v-if="showRefs">
    <div class="tags">

      <!-- 模型名称 -->
      <span v-if="showKey('model') && getModelName(msg)" class="item" @click="console.log(msg)">
        <Bot size="12" /> {{ getModelName(msg) }}
      </span>

      <!-- 复制 -->
      <span v-if="showKey('copy')" class="item btn" @click="copyText(msg.content)" title="复制">
        <Check v-if="isCopied" size="12" />
        <Copy v-else size="12" />
      </span>

      <!-- 重试 -->
      <span
        v-if="showKey('regenerate')"
        class="item btn"
        @click="regenerateMessage()"
        title="重新生成"
      >
        <RotateCcw size="12" />
      </span>

      <!-- 来源按钮区域 -->
      <div v-if="hasSources && showKey('sources')" class="sources-spacer"></div>

      <!-- 网络来源：只有 tavily_search 结果 > 0 时展示 -->
      <span
        v-if="webSources.length > 0 && showKey('sources')"
        class="item btn source-type-btn"
        :class="{ expanded: activeSourceType === 'web' }"
        @click="toggleSourceType('web')"
        :title="activeSourceType === 'web' ? '收起网络来源' : '查看网络来源'"
      >
        <Globe size="12" />
        <span class="sources-label">网络来源 {{ webSources.length }}</span>
        <ChevronDown
          :size="12"
          class="expand-icon"
          :class="{ rotated: activeSourceType === 'web' }"
        />
      </span>

      <!-- 文献来源：只有 pubmed_search 结果 > 0 时展示 -->
      <span
        v-if="literatureSources.length > 0 && showKey('sources')"
        class="item btn source-type-btn"
        :class="{ expanded: activeSourceType === 'literature' }"
        @click="toggleSourceType('literature')"
        :title="activeSourceType === 'literature' ? '收起文献来源' : '查看文献来源'"
      >
        <FileText size="12" />
        <span class="sources-label">文献来源 {{ literatureSources.length }}</span>
        <ChevronDown
          :size="12"
          class="expand-icon"
          :class="{ rotated: activeSourceType === 'literature' }"
        />
      </span>

      <!-- 图谱来源：只有 query_knowledge_graph 结果 > 0 时展示 -->
      <span
        v-if="graphSources.length > 0 && showKey('sources')"
        class="item btn source-type-btn"
        :class="{ expanded: activeSourceType === 'graph' }"
        @click="toggleSourceType('graph')"
        :title="activeSourceType === 'graph' ? '收起图谱来源' : '查看图谱来源'"
      >
        <Network size="12" />
        <span class="sources-label">图谱来源 {{ graphSources.length }}</span>
        <ChevronDown
          :size="12"
          class="expand-icon"
          :class="{ rotated: activeSourceType === 'graph' }"
        />
      </span>
    </div>

    <!-- 来源详情面板 -->
    <div v-if="activeSourceType" class="sources-panel-body">
      <WebSearchSourceSection
        v-if="activeSourceType === 'web'"
        :sources="webSources"
      />

      <LiteratureSourceSection
        v-else-if="activeSourceType === 'literature'"
        :sources="literatureSources"
      />

      <GraphSourceSection
        v-else-if="activeSourceType === 'graph'"
        :sources="graphSources"
      />
    </div>

    <!-- 来源调试信息：确认没问题后通过 :show-source-debug="false" 关闭 -->
    <div v-if="showSourceDebug" class="source-debug-panel">
      <div class="debug-title">来源调试信息</div>
      <pre>{{ debugText }}</pre>
    </div>
  </div>

  <!-- Dislike reason modal -->
  <a-modal
    v-model:open="dislikeModalVisible"
    title="请告诉我们不满意的原因"
    @ok="submitDislikeFeedback"
    @cancel="cancelDislike"
    :confirmLoading="submittingFeedback"
    okText="提交"
    cancelText="取消"
  >
    <a-textarea
      v-model:value="dislikeReason"
      :rows="4"
      placeholder="您的反馈将帮助我们改进服务（可选）"
      :maxlength="500"
      show-count
    />
  </a-modal>
</template>

<script setup>
import { ref, computed, reactive, watch } from 'vue'
import { useClipboard } from '@vueuse/core'
import { message as antMessage } from 'ant-design-vue'
import {
  ThumbsUp,
  ThumbsDown,
  Bot,
  Copy,
  Check,
  RotateCcw,
  ChevronDown,
  Globe,
  FileText,
  Network
} from 'lucide-vue-next'
import { agentApi } from '@/apis'

// 如果你的 SourceSection 组件已经移动到 src/components/sources，
// 把这三个 import 改成 '@/components/sources/xxx.vue'
import WebSearchSourceSection from '@/components/WebSearchSourceSection.vue'
import LiteratureSourceSection from '@/components/LiteratureSourceSection.vue'
import GraphSourceSection from '@/components/GraphSourceSection.vue'

const emit = defineEmits(['retry', 'openRefs'])

const props = defineProps({
  message: Object,
  showRefs: {
    type: [Array, Boolean],
    default: () => false
  },
  isLatestMessage: {
    type: Boolean,
    default: false
  },
  sources: {
    type: Object,
    default: () => ({})
  },
  toolCalls: {
    type: Array,
    default: () => []
  },
  showSourceDebug: {
    type: Boolean,
    default: true
  }
})

const msg = ref(props.message)

// =====================
// 来源状态
// =====================
const activeSourceType = ref(null)

const toggleSourceType = (type) => {
  activeSourceType.value = activeSourceType.value === type ? null : type
}

// =====================
// 工具调用结果解析
// =====================
const parseToolContent = (content) => {
  if (!content) return {}

  if (typeof content === 'string') {
    try {
      return JSON.parse(content)
    } catch {
      return {
        rawText: content
      }
    }
  }

  return content
}

const safeStringify = (value) => {
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

const getToolResultData = (toolCall) => {
  return parseToolContent(
    toolCall?.tool_call_result?.content ||
      toolCall?.toolCallResult?.content ||
      toolCall?.result?.content ||
      toolCall?.result ||
      toolCall?.output ||
      toolCall?.content
  )
}

const getToolName = (toolCall) => {
  const candidates = [
    toolCall?.name,
    toolCall?.tool_name,
    toolCall?.toolName,
    toolCall?.function?.name,
    toolCall?.function_call?.name,
    toolCall?.tool?.name,
    toolCall?.tool_call?.name,
    toolCall?.metadata?.tool_name,
    toolCall?.metadata?.name,
    toolCall?.tool_call_result?.name,
    toolCall?.tool_call_result?.tool_name,
    toolCall?.toolCallResult?.name,
    toolCall?.toolCallResult?.tool_name,

    // 某些结构里 id/type/tool_call_id 可能包含工具名
    toolCall?.id,
    toolCall?.type,
    toolCall?.tool_call_id,
    toolCall?.toolCallId,
    toolCall?.call_id
  ]

  const directMatched = candidates.find((item) => {
    if (typeof item !== 'string') return false

    const value = item.toLowerCase()

    return (
      value === 'tavily_search' ||
      value === 'pubmed_search' ||
      value === 'query_knowledge_graph' ||
      value.includes('tavily') ||
      value.includes('pubmed') ||
      value.includes('knowledge_graph') ||
      value.includes('query_knowledge_graph')
    )
  })

  if (directMatched) {
    return directMatched.toLowerCase()
  }

  // 工具名字段丢失时，根据结果内容兜底判断
  const data = getToolResultData(toolCall)
  const results = Array.isArray(data?.results)
    ? data.results
    : Array.isArray(data?.items)
      ? data.items
      : []

  const looksLikePubMed = results.some((item) => {
    const url = String(item?.url || item?.link || item?.href || item?.metadata?.url || '')
    const source = String(item?.source || item?.metadata?.source || '').toLowerCase()

    return (
      item?.pmid ||
      item?.PMID ||
      item?.metadata?.pmid ||
      item?.metadata?.PMID ||
      url.toLowerCase().includes('pubmed') ||
      source.includes('pubmed')
    )
  })

  if (looksLikePubMed) {
    return 'pubmed_search'
  }

  const looksLikeTavily = results.some((item) => {
    return item?.url || item?.link || item?.href || item?.metadata?.url
  })

  if (looksLikeTavily) {
    return 'tavily_search'
  }

  return (
    toolCall?.name ||
    toolCall?.tool_name ||
    toolCall?.toolName ||
    toolCall?.function?.name ||
    toolCall?.function_call?.name ||
    toolCall?.tool?.name ||
    toolCall?.metadata?.tool_name ||
    toolCall?.metadata?.name ||
    ''
  ).toLowerCase()
}

// =====================
// 工具调用去重
// =====================
const getToolCallDedupeKey = (toolCall, index) => {
  const toolName = getToolName(toolCall)
  const data = getToolResultData(toolCall)

  const content =
    toolCall?.tool_call_result?.content ||
    toolCall?.toolCallResult?.content ||
    toolCall?.result?.content ||
    toolCall?.result ||
    toolCall?.output ||
    toolCall?.content ||
    data

  return (
    [
      toolName,
      safeStringify(content).slice(0, 1000),
      toolCall?.tool_call_id || toolCall?.toolCallId || toolCall?.call_id || ''
    ].join('::') || `${index}`
  )
}

const dedupeToolCalls = (toolCalls = []) => {
  const seen = new Set()

  return toolCalls.filter((toolCall, index) => {
    const key = getToolCallDedupeKey(toolCall, index)

    if (seen.has(key)) {
      return false
    }

    seen.add(key)
    return true
  })
}

const normalizeToolCalls = computed(() => {
  const message = msg.value || {}

  // 关键：父组件已经显式传入 toolCalls 时，只使用 props.toolCalls
  // 不再合并 message / sources 里的同一批工具调用，避免重复 2-3 倍
  if (Array.isArray(props.toolCalls) && props.toolCalls.length > 0) {
    return dedupeToolCalls(props.toolCalls)
  }

  const candidates = [
    message.tool_calls,
    message.toolCalls,
    message.tool_call_results,
    message.toolCallResults,
    message.response_metadata?.tool_calls,
    message.response_metadata?.toolCalls,
    message.response_metadata?.tool_call_results,
    message.response_metadata?.toolCallResults,
    message.metadata?.tool_calls,
    message.metadata?.toolCalls,
    message.metadata?.tool_call_results,
    message.metadata?.toolCallResults,
    message.meta?.tool_calls,
    message.meta?.toolCalls,
    props.sources?.tool_calls,
    props.sources?.toolCalls,
    props.sources?.tool_call_results,
    props.sources?.toolCallResults
  ]

  // 没有 props.toolCalls 时，只取第一个非空候选，不再全部 merge
  const firstNonEmpty = candidates.find((candidate) => {
    return Array.isArray(candidate) && candidate.length > 0
  })

  return dedupeToolCalls(firstNonEmpty || [])
})

const pickArray = (...values) => {
  let firstArray = []

  for (const value of values) {
    if (Array.isArray(value)) {
      if (value.length > 0) {
        return value
      }

      if (firstArray.length === 0) {
        firstArray = value
      }
    }
  }

  return firstArray
}

const normalizeTriple = (item, index) => {
  if (Array.isArray(item) && item.length >= 3) {
    return {
      id: `triple-${index}`,
      head: item[0],
      relation: item[1],
      tail: item[2],
      content: `${item[0]} → ${item[1]} → ${item[2]}`
    }
  }

  return item
}

const isTavilyTool = (toolName) => {
  return toolName === 'tavily_search' || toolName.includes('tavily')
}

const isPubmedTool = (toolName) => {
  return toolName === 'pubmed_search' || toolName.includes('pubmed')
}

const isKnowledgeGraphTool = (toolName) => {
  return (
    toolName === 'query_knowledge_graph' ||
    toolName.includes('query_knowledge_graph') ||
    toolName.includes('knowledge_graph') ||
    toolName.includes('graph') ||
    toolName.includes('kg') ||
    toolName.includes('triple') ||
    toolName.includes('图谱') ||
    toolName.includes('知识图谱')
  )
}

const isTripleResult = (data) => {
  return Array.isArray(data?.triples)
}

const getResultItems = (data, fields) => {
  if (Array.isArray(data)) {
    return data
  }

  const values = fields.map((field) => data?.[field])
  return pickArray(...values)
}

// =====================
// 来源结果去重
// =====================
const getSourceItemKey = (item, index) => {
  if (Array.isArray(item)) {
    return item.join('::')
  }

  return (
    item?.id ||
    item?.pmid ||
    item?.PMID ||
    item?.doi ||
    item?.url ||
    item?.link ||
    item?.href ||
    item?.title ||
    item?.name ||
    item?.metadata?.pmid ||
    item?.metadata?.PMID ||
    item?.metadata?.doi ||
    item?.metadata?.url ||
    `${safeStringify(item).slice(0, 500)}-${index}`
  )
}

const dedupeSourceItems = (items = []) => {
  const seen = new Set()

  return items.filter((item, index) => {
    const key = getSourceItemKey(item, index)

    if (seen.has(key)) {
      return false
    }

    seen.add(key)
    return true
  })
}

// =====================
// 从工具调用结果提取：网络来源
// 严格规则：只有 tavily_search -> 网络来源
// =====================
const webSourcesFromTools = computed(() => {
  const result = []

  normalizeToolCalls.value.forEach((toolCall) => {
    const toolName = getToolName(toolCall)
    const data = getToolResultData(toolCall)

    if (!isTavilyTool(toolName)) {
      return
    }

    const items = getResultItems(data, [
      'results',
      'webSources',
      'web_sources',
      'web_search_sources',
      'search_results',
      'items'
    ])

    result.push(...items)
  })

  return dedupeSourceItems(result)
})

// =====================
// 从工具调用结果提取：文献来源
// 严格规则：只有 pubmed_search -> 文献来源
// =====================
const literatureSourcesFromTools = computed(() => {
  const result = []

  normalizeToolCalls.value.forEach((toolCall) => {
    const toolName = getToolName(toolCall)
    const data = getToolResultData(toolCall)

    if (!isPubmedTool(toolName)) {
      return
    }

    const items = getResultItems(data, [
      'results',
      'items',
      'literatureSources',
      'literature_sources',
      'literature',
      'papers',
      'articles',
      'publications',
      'documents',
      'docs',
      'documentSources',
      'document_sources',
      'knowledgeChunks',
      'knowledge_chunks',
      'chunks',
      'references',
      'citations'
    ])

    result.push(...items)
  })

  return dedupeSourceItems(result)
})

// =====================
// 从工具调用结果提取：图谱来源
// query_knowledge_graph -> 图谱来源
// =====================
const graphSourcesFromTools = computed(() => {
  const result = []

  normalizeToolCalls.value.forEach((toolCall) => {
    const toolName = getToolName(toolCall)
    const data = getToolResultData(toolCall)

    if (!isKnowledgeGraphTool(toolName) && !isTripleResult(data)) {
      return
    }

    const items = getResultItems(data, [
      'triples',
      'relations',
      'edges',
      'graphSources',
      'graph_sources',
      'graphResults',
      'graph_results',
      'kgSources',
      'kg_sources',
      'kgResults',
      'kg_results',
      'results',
      'items'
    ])

    result.push(...items.map((item, index) => normalizeTriple(item, index)))
  })

  return dedupeSourceItems(result)
})

const hasSourceToolCalls = computed(() => {
  return normalizeToolCalls.value.some((toolCall) => {
    const toolName = getToolName(toolCall)
    const data = getToolResultData(toolCall)

    return (
      isTavilyTool(toolName) ||
      isPubmedTool(toolName) ||
      isKnowledgeGraphTool(toolName) ||
      isTripleResult(data)
    )
  })
})

// =====================
// props.sources 来源兜底
// 注意：只有没有工具调用结果时才使用 props.sources
// =====================
const webSourcesFromProps = computed(() => {
  return dedupeSourceItems(
    pickArray(
      props.sources?.webSources,
      props.sources?.web_sources,
      props.sources?.web_search_sources,
      props.sources?.webSearchSources,
      props.sources?.web,
      props.sources?.searchResults,
      props.sources?.webSearchResults
    )
  )
})

const literatureSourcesFromProps = computed(() => {
  return dedupeSourceItems(
    pickArray(
      props.sources?.literatureSources,
      props.sources?.literature_sources,
      props.sources?.literature,
      props.sources?.papers,
      props.sources?.articles,
      props.sources?.publications,
      props.sources?.documents,
      props.sources?.docs,
      props.sources?.documentSources,
      props.sources?.document_sources,
      props.sources?.knowledgeChunks,
      props.sources?.knowledge_chunks,
      props.sources?.chunks,
      props.sources?.references,
      props.sources?.citations
    )
  )
})

const graphSourcesFromProps = computed(() => {
  return dedupeSourceItems(
    pickArray(
      props.sources?.graphSources,
      props.sources?.graph_sources,
      props.sources?.graph,
      props.sources?.graphResults,
      props.sources?.graph_results,
      props.sources?.kgSources,
      props.sources?.kg_sources,
      props.sources?.kg,
      props.sources?.kgResults,
      props.sources?.kg_results,
      props.sources?.knowledgeGraphSources,
      props.sources?.knowledge_graph_sources,
      props.sources?.triples,
      props.sources?.relations,
      props.sources?.entities
    ).map((item, index) => normalizeTriple(item, index))
  )
})

// =====================
// 最终来源数据
// 有工具调用时：严格使用 toolCalls 分类结果
// 没有工具调用时：才使用 props.sources 兜底
// =====================
const webSources = computed(() => {
  if (hasSourceToolCalls.value) {
    return webSourcesFromTools.value
  }

  return webSourcesFromProps.value
})

const literatureSources = computed(() => {
  if (hasSourceToolCalls.value) {
    return literatureSourcesFromTools.value
  }

  return literatureSourcesFromProps.value
})

const graphSources = computed(() => {
  if (hasSourceToolCalls.value) {
    return graphSourcesFromTools.value
  }

  return graphSourcesFromProps.value
})

const hasSources = computed(() => {
  return (
    webSources.value.length > 0 ||
    literatureSources.value.length > 0 ||
    graphSources.value.length > 0
  )
})

watch(
  [webSources, literatureSources, graphSources],
  () => {
    if (activeSourceType.value === 'web' && webSources.value.length === 0) {
      activeSourceType.value = null
    }

    if (activeSourceType.value === 'literature' && literatureSources.value.length === 0) {
      activeSourceType.value = null
    }

    if (activeSourceType.value === 'graph' && graphSources.value.length === 0) {
      activeSourceType.value = null
    }
  },
  {
    immediate: true
  }
)

// =====================
// 调试信息
// =====================
const getDebugResultPreview = (data) => {
  if (!data || typeof data !== 'object') {
    return data
  }

  return {
    keys: Object.keys(data),
    resultsCount: Array.isArray(data.results) ? data.results.length : undefined,
    itemsCount: Array.isArray(data.items) ? data.items.length : undefined,
    triplesCount: Array.isArray(data.triples) ? data.triples.length : undefined,
    sampleResult: Array.isArray(data.results) ? data.results[0] : undefined,
    sampleItem: Array.isArray(data.items) ? data.items[0] : undefined,
    sampleTriple: Array.isArray(data.triples) ? data.triples[0] : undefined,
    rawText: data.rawText ? String(data.rawText).slice(0, 300) : undefined
  }
}

const sourceDebugInfo = computed(() => {
  return {
    sourceMode: hasSourceToolCalls.value ? 'toolCalls' : 'propsFallback',
    finalCounts: {
      web: webSources.value.length,
      literature: literatureSources.value.length,
      graph: graphSources.value.length
    },
    propsCounts: {
      web: webSourcesFromProps.value.length,
      literature: literatureSourcesFromProps.value.length,
      graph: graphSourcesFromProps.value.length
    },
    toolCounts: {
      web: webSourcesFromTools.value.length,
      literature: literatureSourcesFromTools.value.length,
      graph: graphSourcesFromTools.value.length
    },
    toolCallsCount: normalizeToolCalls.value.length,
    toolCalls: normalizeToolCalls.value.map((toolCall) => {
      const name = getToolName(toolCall)
      const data = getToolResultData(toolCall)

      return {
        name,
        classifiedAs: isTavilyTool(name)
          ? 'web'
          : isPubmedTool(name)
            ? 'literature'
            : isKnowledgeGraphTool(name) || isTripleResult(data)
              ? 'graph'
              : 'unknown',
        toolCallKeys: Object.keys(toolCall || {}),
        resultPreview: getDebugResultPreview(data)
      }
    })
  }
})

const debugText = computed(() => JSON.stringify(sourceDebugInfo.value, null, 2))

watch(
  sourceDebugInfo,
  (info) => {
    if (props.showSourceDebug) {
      console.log('[Source Debug]', info)
    }
  },
  {
    immediate: true,
    deep: true
  }
)

// =====================
// 反馈状态
// =====================
const feedbackState = reactive({
  hasSubmitted: false,
  rating: null,
  reason: null
})

const initFeedbackState = () => {
  if (msg.value?.feedback) {
    feedbackState.hasSubmitted = true
    feedbackState.rating = msg.value.feedback.rating
    feedbackState.reason = msg.value.feedback.reason
  } else {
    feedbackState.hasSubmitted = false
    feedbackState.rating = null
    feedbackState.reason = null
  }
}

watch(
  () => props.message,
  () => {
    msg.value = props.message
    activeSourceType.value = null
    initFeedbackState()
  },
  { immediate: true }
)

// Modal state for dislike
const dislikeModalVisible = ref(false)
const dislikeReason = ref('')
const submittingFeedback = ref(false)

// 使用 useClipboard 实现复制功能
const { copy, isSupported } = useClipboard()

const showKey = (key) => {
  if (props.showRefs === true) {
    return true
  }

  if (Array.isArray(props.showRefs)) {
    return props.showRefs.includes(key)
  }

  return false
}

// 复制状态
const isCopied = ref(false)

const copyText = async (text) => {
  if (isSupported) {
    try {
      await copy(text)
      antMessage.success('文本已复制到剪贴板')
      isCopied.value = true

      setTimeout(() => {
        isCopied.value = false
      }, 2000)
    } catch (error) {
      console.error('复制失败:', error)
      antMessage.error('复制失败，请手动复制')
    }
  } else {
    console.warn('浏览器不支持自动复制')
    antMessage.warning('浏览器不支持自动复制，请手动复制')
  }
}

const showRefs = computed(() => {
  if (props.showRefs && Array.isArray(props.showRefs) && props.showRefs.includes('model')) {
    return true
  }

  return (
    (msg.value?.role === 'received' || msg.value?.role === 'assistant') &&
    msg.value?.status === 'finished'
  )
})

const regenerateMessage = () => {
  emit('retry')
}

const getModelName = (msg) => {
  if (msg?.response_metadata?.model_name) {
    return msg.response_metadata.model_name
  }

  if (msg?.meta?.server_model_name) {
    return msg.meta.server_model_name
  }

  return null
}

const likeThisResponse = async (msg) => {
  if (feedbackState.hasSubmitted) {
    antMessage.info('您已经提交过反馈了')
    return
  }

  if (!msg?.id) {
    antMessage.error('无法提交反馈：消息ID不存在')
    console.error('Message object:', msg)
    return
  }

  try {
    submittingFeedback.value = true
    await agentApi.submitMessageFeedback(msg.id, 'like', null)

    feedbackState.hasSubmitted = true
    feedbackState.rating = 'like'

    antMessage.success('感谢您的反馈！')
  } catch (error) {
    console.error('Failed to submit like feedback:', error)

    if (error.message?.includes('already submitted')) {
      antMessage.info('您已经提交过反馈了')
      feedbackState.hasSubmitted = true
    } else {
      antMessage.error('提交反馈失败，请稍后重试')
    }
  } finally {
    submittingFeedback.value = false
  }
}

const dislikeThisResponse = async (msg) => {
  if (feedbackState.hasSubmitted) {
    antMessage.info('您已经提交过反馈了')
    return
  }

  if (!msg?.id) {
    antMessage.error('无法提交反馈：消息ID不存在')
    console.error('Message object:', msg)
    return
  }

  dislikeModalVisible.value = true
}

const submitDislikeFeedback = async () => {
  try {
    submittingFeedback.value = true
    await agentApi.submitMessageFeedback(msg.value.id, 'dislike', dislikeReason.value || null)

    feedbackState.hasSubmitted = true
    feedbackState.rating = 'dislike'
    feedbackState.reason = dislikeReason.value

    dislikeModalVisible.value = false
    dislikeReason.value = ''

    antMessage.success('感谢您的反馈！')
  } catch (error) {
    console.error('Failed to submit dislike feedback:', error)

    if (error.message?.includes('already submitted')) {
      antMessage.info('您已经提交过反馈了')
      feedbackState.hasSubmitted = true
      dislikeModalVisible.value = false
    } else {
      antMessage.error('提交反馈失败，请稍后重试')
    }
  } finally {
    submittingFeedback.value = false
  }
}

const cancelDislike = () => {
  dislikeModalVisible.value = false
  dislikeReason.value = ''
}
</script>

<style lang="less" scoped>
.refs {
  display: flex;
  flex-direction: column;
  margin-bottom: 20px;
  margin-top: 10px;
  color: var(--gray-500);
  font-size: 13px;
  gap: 12px;

  .item {
    background: var(--gray-50);
    color: var(--gray-700);
    padding: 6px 8px;
    border-radius: 8px;
    font-size: 13px;
    user-select: none;
    transition: all 0.2s ease;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
    line-height: 1;

    &.btn {
      cursor: pointer;

      &:hover {
        background: var(--gray-100);
      }

      &:active {
        background: var(--gray-200);
      }

      &.disabled {
        &:hover {
          background: var(--gray-50);
        }
      }
    }
  }

  .tags {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
    width: 100%;

    .sources-spacer {
      flex-grow: 1;
    }

    .source-type-btn {
      background: var(--gray-50);
      border: 1px solid transparent;
      padding: 6px 10px;

      &:hover {
        background: var(--gray-100);
      }

      &.expanded {
        background: var(--main-50);
        color: var(--main-700);
        border-color: var(--main-100);
      }

      .sources-label {
        font-weight: 500;
        margin-left: 2px;
      }

      .expand-icon {
        margin-left: 4px;
        transition: transform 0.2s ease;

        &.rotated {
          transform: rotate(180deg);
        }
      }
    }
  }

  .sources-panel-body {
    background: var(--gray-25);
    border: 1px solid var(--gray-150);
    border-radius: 8px;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    animation: slideDown 0.2s ease-out;
  }

  .source-debug-panel {
    background: var(--gray-25);
    border: 1px dashed var(--gray-200);
    border-radius: 8px;
    padding: 10px;

    .debug-title {
      font-size: 12px;
      font-weight: 600;
      color: var(--gray-700);
      margin-bottom: 6px;
    }

    pre {
      margin: 0;
      max-height: 360px;
      overflow: auto;
      font-size: 11px;
      line-height: 1.5;
      color: var(--gray-800);
      white-space: pre-wrap;
      word-break: break-word;
    }
  }
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-8px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>