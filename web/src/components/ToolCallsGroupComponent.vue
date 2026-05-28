<template>
  <div v-if="normalizedToolCalls.length > 0" class="tool-calls-container">
    <button
      v-if="shouldCollapseToolCalls"
      type="button"
      class="tool-calls-summary"
      :class="{ 'is-expanded': areToolCallsExpanded }"
      :aria-expanded="areToolCallsExpanded"
      @click="toggleToolCallsExpanded"
    >
      <span class="summary-leading">
        <Wrench size="14" />
      </span>
      <span class="summary-content">
        <span class="summary-title">{{ toolCallsSummaryTitle }}</span>
        <span class="summary-separator" v-if="normalizedToolCalls.length > 1 && toolCallsNamesMeta">
          ·
        </span>
        <span class="summary-meta" v-if="normalizedToolCalls.length > 1 && toolCallsNamesMeta">
          {{ toolCallsNamesMeta }}
        </span>
        <span class="summary-status-tag" :class="statusTagClass" v-if="statusSummary">{{ statusSummary }}</span>
      </span>
      <span class="summary-trailing">
        <component :is="areToolCallsExpanded ? ChevronDown : ChevronRight" size="14" />
      </span>
    </button>

    <div
      v-show="!shouldCollapseToolCalls || areToolCallsExpanded"
      class="tool-calls-panel"
    >
      <div
        v-for="(toolCall, index) in normalizedToolCalls"
        :key="getStableToolCallRenderKey(toolCall, index)"
        class="tool-call-container"
      >
        <ToolCallRenderer
          :tool-call="toolCall"
          appearance="card"
          :default-expanded="areToolCallsExpanded"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ChevronDown, ChevronRight, Wrench } from 'lucide-vue-next'
import { ToolCallRenderer } from '@/components/ToolCallingResult'
import { getToolCallId, HIDDEN_TOOL_CALL_IDS } from '@/components/ToolCallingResult/toolRegistry'

const props = defineProps({
  toolCalls: {
    type: Array,
    default: () => []
  },
  isActive: {
    type: Boolean,
    default: false
  },
  groupKey: {
    type: String,
    default: ''
  }
})

const EXPANDED_STATE_CACHE_KEY = '__YUXI_TOOL_CALLS_GROUP_EXPANDED_STATE__'

const getExpandedStateCache = () => {
  if (typeof globalThis === 'undefined') {
    return new Map()
  }

  if (!globalThis[EXPANDED_STATE_CACHE_KEY]) {
    globalThis[EXPANDED_STATE_CACHE_KEY] = new Map()
  }

  return globalThis[EXPANDED_STATE_CACHE_KEY]
}

const expandedStateCache = getExpandedStateCache()

const normalizedToolCalls = computed(() => {
  return (props.toolCalls || []).filter((toolCall) => {
    const toolId = getToolCallId(toolCall)

    return (
      toolCall &&
      !HIDDEN_TOOL_CALL_IDS.includes(toolId) &&
      (toolCall.id || toolCall.name || toolCall.function?.name) &&
      (toolCall.args !== undefined ||
        toolCall.function?.arguments !== undefined ||
        toolCall.tool_call_result !== undefined)
    )
  })
})

const shouldCollapseToolCalls = computed(() => normalizedToolCalls.value.length > 0)

const groupStateKey = computed(() => {
  if (props.groupKey) return props.groupKey

  const names = normalizedToolCalls.value
    .map((toolCall, index) => getToolCallStableName(toolCall, index))
    .filter(Boolean)
    .join('|')

  return names ? `tool-group-${names}` : 'tool-group'
})

const getToolCallStableName = (toolCall, index) => {
  return (
    toolCall?.name ||
    toolCall?.function?.name ||
    getToolCallId(toolCall) ||
    `tool-${index}`
  )
}

// 关键点：这里不要优先用 toolCall.id。
// 因为 id 可能在 delta -> full tool_call -> tool_result 阶段变化。
// 用 groupStateKey + index + name 可以保证同一轮里渲染 key 更稳定。
const getStableToolCallRenderKey = (toolCall, index) => {
  return `${groupStateKey.value}:tool-${index}:${getToolCallStableName(toolCall, index)}`
}

const readCachedExpanded = () => {
  const key = groupStateKey.value

  if (expandedStateCache.has(key)) {
    return Boolean(expandedStateCache.get(key))
  }

  return Boolean(props.isActive)
}

const writeCachedExpanded = (expanded) => {
  expandedStateCache.set(groupStateKey.value, Boolean(expanded))
}

const areToolCallsExpanded = ref(readCachedExpanded())

watch(
  groupStateKey,
  () => {
    areToolCallsExpanded.value = readCachedExpanded()
  },
  { immediate: true }
)

watch(
  () => props.isActive,
  (isActive) => {
    // active 时可以自动展开；inactive 时绝不自动收起。
    if (isActive && !areToolCallsExpanded.value) {
      areToolCallsExpanded.value = true
      writeCachedExpanded(true)
    }
  },
  { immediate: true }
)

watch(
  () => normalizedToolCalls.value.length,
  (length) => {
    if (length === 0) return

    // 工具数量变化时，不重置用户展开状态。
    if (props.isActive && !areToolCallsExpanded.value) {
      areToolCallsExpanded.value = true
      writeCachedExpanded(true)
    }
  }
)

const getToolCallLabel = (toolCall) => {
  const rawName = getToolCallId(toolCall)
  const name = typeof rawName === 'string' ? rawName.replaceAll('_', ' ') : 'tool'
  return name.charAt(0).toUpperCase() + name.slice(1)
}

const toolCallsSummaryTitle = computed(() => {
  if (normalizedToolCalls.value.length === 1) {
    return `使用了工具: ${getToolCallLabel(normalizedToolCalls.value[0])}`
  }
  return `已调用 ${normalizedToolCalls.value.length} 个工具`
})

const toolCallsNamesMeta = computed(() => {
  const names = normalizedToolCalls.value.map(getToolCallLabel).filter(Boolean)
  const uniqueNames = [...new Set(names)]
  const visibleNames = uniqueNames.slice(0, 3)

  if (visibleNames.length === 0) return ''

  return `${visibleNames.join(' · ')}${
    uniqueNames.length > visibleNames.length ? ` +${uniqueNames.length - visibleNames.length}` : ''
  }`
})

const statusSummary = computed(() => {
  const successCount = normalizedToolCalls.value.filter(
    (toolCall) => toolCall.status === 'success' || toolCall.tool_call_result
  ).length
  const runningCount = normalizedToolCalls.value.filter(
    (toolCall) =>
      toolCall.status !== 'success' && toolCall.status !== 'error' && !toolCall.tool_call_result
  ).length
  const errorCount = normalizedToolCalls.value.filter(
    (toolCall) => toolCall.status === 'error'
  ).length

  const parts = []
  if (successCount > 0 && successCount === normalizedToolCalls.value.length) {
    return '已完成'
  }
  if (errorCount > 0) parts.push(`${errorCount} 失败`)
  if (runningCount > 0) parts.push(`${runningCount} 进行中`)

  return parts.join(' · ')
})

const statusTagClass = computed(() => {
  const successCount = normalizedToolCalls.value.filter(
    (toolCall) => toolCall.status === 'success' || toolCall.tool_call_result
  ).length
  const runningCount = normalizedToolCalls.value.filter(
    (toolCall) =>
      toolCall.status !== 'success' && toolCall.status !== 'error' && !toolCall.tool_call_result
  ).length
  const errorCount = normalizedToolCalls.value.filter(
    (toolCall) => toolCall.status === 'error'
  ).length

  if (errorCount > 0) return 'status-error'
  if (runningCount > 0) return 'status-running'
  if (successCount > 0 && successCount === normalizedToolCalls.value.length) return 'status-success'
  return ''
})

const toggleToolCallsExpanded = () => {
  if (!shouldCollapseToolCalls.value) return

  areToolCallsExpanded.value = !areToolCallsExpanded.value
  writeCachedExpanded(areToolCallsExpanded.value)
}
</script>

<style lang="less" scoped>
.tool-calls-container {
  width: 100%;
  margin: 0;
  padding: 0;

  .tool-calls-summary {
    appearance: none;
    width: 100%;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 12px;
    border: 1px solid var(--gray-200);
    border-radius: 8px;
    background: #fff;
    color: var(--gray-600);
    text-align: left;
    cursor: pointer;
    outline: none;
    transition: all 0.2s ease;
    user-select: none;

    &:hover {
      background: #fafafa;
      border-color: var(--gray-300);
    }

    &.is-expanded {
      background: #fff;
      border-color: var(--gray-300);
      margin-bottom: 4px;
    }

    .summary-leading {
      display: inline-flex;
      align-items: center;
      color: var(--gray-600);
      flex-shrink: 0;
    }

    .summary-content {
      min-width: 0;
      display: flex;
      align-items: center;
      gap: 6px;
      flex: 1;
      font-size: 13px;
    }

    .summary-title {
      font-weight: 500;
      white-space: nowrap;
    }

    .summary-separator {
      color: var(--gray-400);
      flex-shrink: 0;
    }

    .summary-meta {
      color: var(--gray-500);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .summary-status-tag {
      margin-left: auto;
      font-size: 11px;
      padding: 2px 6px;
      border-radius: 4px;
      white-space: nowrap;
      font-weight: normal;
    }

    .summary-trailing {
      display: inline-flex;
      align-items: center;
      color: var(--gray-400);
      flex-shrink: 0;
    }
  }

  .tool-calls-panel {
    padding: 8px 12px;
    background: #00000008;
    border: 1px solid var(--gray-200);
    border-radius: 8px;
    margin-left: 0;
    margin-top: 4px;
    margin-bottom: 8px;
  }

  .tool-call-container {
    margin-bottom: 4px;

    &:last-child {
      margin-bottom: 0;
    }
  }
}

.status-success {
  background: var(--main-50);
  color: var(--main-700);
}

.status-running {
  background: var(--color-info-50);
  color: var(--color-info-700);
}

.status-error {
  background: var(--color-error-50);
  color: var(--color-error-700);
}
</style>