<template>
  <section v-if="visible" class="kg-detail-card">
    <header
      class="detail-header"
      :class="{
        'detail-header--node': isNodeDetail,
        'detail-header--relation': isRelationDetail,
        [headerTitleDensityClass]: isNodeDetail,
        [headerRelationLineCountClass]: isRelationDetail,
        'detail-header--relation-line-overflow': isRelationDetail && headerRelationHiddenCount > 0
      }"
    >
      <div class="detail-header__backdrop"></div>
      <div class="detail-header__rail"></div>
      <div class="detail-header__dots"></div>
      <div class="detail-header__actions">
        <button
          class="detail-header__close"
          type="button"
          @click.stop="emit('close')"
          aria-label="关闭详情面板"
        >
          <X class="detail-header__close-icon" />
        </button>
      </div>

      <div class="detail-header__top">
        <div class="detail-header__brand">
          <div class="detail-header__icon" :class="{ 'is-relation': isRelationDetail }">
            <Link2 v-if="isRelationDetail" class="detail-header__icon-svg" />
            <span v-else class="detail-header__icon-text">{{ avatarText }}</span>
          </div>

          <div class="detail-header__title-group">
            <div class="detail-header__eyebrow">{{ headerKindLabel }}</div>
            <h3
              v-if="isNodeDetail"
              ref="headerTitleRef"
              class="detail-header__title"
              :title="headerTitle"
            >
              {{ headerTitle }}
            </h3>
            <div v-if="isNodeDetail && headerTypeText" class="detail-header__chip-row">
              <span class="detail-header__chip">{{ headerTypeText }}</span>
            </div>
            <div v-else class="detail-header__relation-lines">
              <div
                v-for="line in headerRelationLines"
                :key="line"
                class="detail-header__relation-line"
                :title="line"
              >
                {{ line }}
              </div>
              <div
                v-if="headerRelationHiddenCount > 0"
                class="detail-header__relation-more"
                :title="`还有 ${headerRelationHiddenCount} 条关系类型`"
              >
                +{{ headerRelationHiddenCount }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </header>

    <nav class="detail-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        type="button"
        class="tab-btn"
        :class="{ active: activeTab === tab.key }"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
      </button>
    </nav>

    <main class="detail-body">
      <section v-show="activeTab === 'overview'" class="detail-section">
        <h4 class="section-title">{{ overviewTitle }}</h4>

        <div class="info-list">
          <div v-for="row in overviewRows" :key="row.key" class="info-row">
            <div class="info-key">{{ row.label }}</div>
            <div
              class="info-value"
              :title="Array.isArray(row.value) ? row.value.join(' / ') : row.value"
            >
              <template v-if="row.displayType === 'chips' && Array.isArray(row.value)">
                <div class="chip-list">
                  <span v-for="item in row.value" :key="`${row.key}-${item}`" class="mini-pill">
                    {{ item }}
                  </span>
                </div>
              </template>
              <template v-else-if="Array.isArray(row.value)">
                <div class="detail-row__text detail-row__text--multiline">
                  {{ row.value.join('\n') }}
                </div>
              </template>
              <template v-else>
                <div class="detail-row__text">{{ row.value }}</div>
              </template>
            </div>
          </div>
        </div>
      </section>

      <section v-show="activeTab === 'nodes'" class="detail-section">
        <div class="section-head">
          <h4 class="section-title no-margin">关联节点</h4>
          <span class="section-count">{{ relatedNodes.length }}</span>
        </div>

        <div class="node-list">
          <div
            v-for="node in relatedNodes"
            :key="node.id"
            class="node-card"
            role="button"
            tabindex="0"
            @click="handleFocusNode(node)"
            @keydown.enter="handleFocusNode(node)"
          >
            <span class="mini-node-icon">{{ getNodeInitial(node) }}</span>
            <span class="node-main">
              <strong :title="getNodeTitle(node)">{{ getNodeTitle(node) }}</strong>
              <em>{{ getNodeType(node) }}</em>
            </span>
            <span class="jump-icon">定位</span>
          </div>
        </div>

        <div v-if="relatedNodes.length === 0" class="empty-block">暂无关联节点</div>
      </section>

      <section v-show="activeTab === 'edges'" class="detail-section">
        <div class="section-head">
          <h4 class="section-title no-margin">关联关系</h4>
          <span class="section-count">{{ relatedEdges.length }}</span>
        </div>

        <div class="edge-list">
          <div
            v-for="edge in relatedEdges"
            :key="getEdgeStableKey(edge)"
            class="edge-card"
            role="button"
            tabindex="0"
            @click="handleFocusEdge(edge)"
            @keydown.enter="handleFocusEdge(edge)"
          >
            <span class="edge-dot"></span>
            <span class="edge-main">
              <strong :title="getEdgeTitle(edge)">{{ getEdgeTitle(edge) }}</strong>
              <em :title="getEdgeEndpointText(edge)">{{ getEdgeEndpointText(edge) }}</em>
            </span>
            <span class="jump-icon">高亮</span>
          </div>
        </div>

        <div v-if="relatedEdges.length === 0" class="empty-block">暂无关联关系</div>
      </section>
    </main>

    <footer class="detail-actions">
      <button class="secondary-action" type="button" @click="copyCurrentId">复制节点 ID</button>
      <button class="primary-action" type="button" @click="exportCurrentDetail">
        导出节点信息
      </button>
    </footer>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { Link2, X } from 'lucide-vue-next'
import {
  getNodeDisplayType,
  getRelationSourceTypes,
  getSourceDisplayValue
} from '@/utils/graphDisplay'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  item: {
    type: Object,
    default: null
  },
  type: {
    type: String,
    default: 'node'
  },
  nodes: {
    type: Array,
    default: () => []
  },
  edges: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['close', 'focus-node', 'focus-edge'])

const activeTab = ref('overview')

const tabs = [
  { key: 'overview', label: '概览' },
  { key: 'nodes', label: '关联节点' },
  { key: 'edges', label: '关联关系' }
]

const itemData = computed(() => props.item || {})

const itemPayload = computed(() => itemData.value?.data || itemData.value || {})

const original = computed(() => {
  const payload = itemPayload.value
  const raw = payload?.original || payload?.data?.original || payload || {}
  if (!raw || typeof raw !== 'object') return raw || {}

  const merged = { ...raw }
  let cursor = raw

  for (let i = 0; i < 3 && cursor?.properties && typeof cursor.properties === 'object'; i++) {
    cursor = cursor.properties
    for (const [key, value] of Object.entries(cursor)) {
      if (value !== null && value !== undefined && typeof value !== 'object') {
        merged[key] = value
      }
    }
  }

  return merged
})

const currentId = computed(() => {
  return String(itemData.value?.id || original.value?.id || itemPayload.value?.id || '')
})

const displayTitle = computed(() => {
  const data = original.value
  return (
    data.name ||
    data.title ||
    data.label ||
    itemPayload.value?.label ||
    itemData.value?.id ||
    '未命名节点'
  )
})

const displayType = computed(() => {
  if (props.type === 'edge') {
    return relationSourceTypes.value.join(' / ')
  }

  return nodeDisplayType.value
})

const isNodeDetail = computed(() => props.type !== 'edge')
const isRelationDetail = computed(() => props.type === 'edge')
const overviewTitle = computed(() => (isRelationDetail.value ? '关系摘要' : '节点摘要'))

const relationSourceTypes = computed(() => getRelationSourceTypes(itemPayload.value))
const nodeDisplayType = computed(() => getNodeDisplayType(original.value))

const avatarText = computed(() => {
  return 'N'
})

const headerKindLabel = computed(() => (isRelationDetail.value ? '关系详情' : '节点详情'))

const headerTitle = computed(() => displayTitle.value)
const detailSignature = computed(() => `${props.type}::${currentId.value}::${headerTitle.value}`)

const headerTypeText = computed(() => {
  if (!isNodeDetail.value) return ''
  return nodeDisplayType.value || ''
})

function stripRelationCountSuffix(text) {
  return String(text || '')
    .replace(/\s*\+\d+\s*$/, '')
    .trim()
}

const headerRelationTypes = computed(() => {
  if (!isRelationDetail.value) return []
  return toUniqueStrings(relationSourceTypes.value)
})

const headerRelationLines = computed(() => {
  const lines = toUniqueStrings(
    headerRelationTypes.value.map((item) => stripRelationCountSuffix(item))
  ).filter(Boolean)

  if (lines.length > 0) {
    return lines.slice(0, 4)
  }

  return ['原始数据未提供']
})

const headerRelationHiddenCount = computed(() => {
  return Math.max(0, headerRelationTypes.value.length - headerRelationLines.value.length)
})

const headerRelationLineCountClass = computed(() => {
  const count = Math.min(Math.max(headerRelationLines.value.length, 1), 4)
  return `detail-header--relation-line-count-${count}`
})

const headerTitleRef = ref(null)
const headerTitleDensityClass = ref('detail-header--multi-line-title')
let headerTitleFrameId = 0

function toUniqueStrings(values) {
  return Array.from(
    new Set(
      values
        .filter(Boolean)
        .map((value) => String(value).trim())
        .filter(Boolean)
    )
  )
}

async function syncHeaderTitleDensity() {
  if (!isNodeDetail.value) {
    headerTitleDensityClass.value = 'detail-header--multi-line-title'
    return
  }

  if (headerTitleFrameId) {
    cancelAnimationFrame(headerTitleFrameId)
    headerTitleFrameId = 0
  }

  await nextTick()

  headerTitleFrameId = requestAnimationFrame(() => {
    const el = headerTitleRef.value
    if (!el) {
      headerTitleDensityClass.value = 'detail-header--multi-line-title'
      return
    }

    const lineHeight = Number.parseFloat(getComputedStyle(el).lineHeight)
    const height = el.scrollHeight || el.getBoundingClientRect().height
    const lines =
      Number.isFinite(lineHeight) && lineHeight > 0 ? Math.round(height / lineHeight) : 2
    const nextClass =
      lines <= 1 ? 'detail-header--single-line-title' : 'detail-header--multi-line-title'

    if (headerTitleDensityClass.value !== nextClass) {
      headerTitleDensityClass.value = nextClass
    }
  })
}

function getNodeTitle(node) {
  const payload = node?.data?.original || node?.original || node
  return (
    payload?.name ||
    payload?.title ||
    payload?.label ||
    node?.data?.label ||
    node?.id ||
    '未命名节点'
  )
}

function getNodeType(node) {
  const payload = node?.data?.original || node?.original || node
  const displayType = getNodeDisplayType(payload)
  if (displayType) return displayType
  return '原始数据未提供'
}

function getNodeInitial(node) {
  return String(getNodeTitle(node)).slice(0, 1).toUpperCase()
}

function findNodeById(nodeId) {
  return props.nodes.find((node) => String(node.id) === String(nodeId))
}

function getNodeDisplayById(nodeId) {
  const matched = findNodeById(nodeId)
  return matched ? getNodeTitle(matched) : String(nodeId || '未知节点')
}

function toOverviewRow(key, label, value, displayType = 'text') {
  if (value === undefined || value === null) return null
  if (Array.isArray(value)) {
    const items = value.map((item) => String(item).trim()).filter(Boolean)
    if (items.length === 0) return null
    return { key, label, value: items, displayType }
  }
  const text = String(value).trim()
  if (!text) return null
  return { key, label, value: text, displayType }
}

function getNodeTypeOverviewRow() {
  return toOverviewRow('node_type', '节点类型', nodeDisplayType.value)
}

function getRelationSourceText(edge) {
  return (
    getSourceDisplayValue(edge) ||
    (edge?.originals || []).map((item) => getSourceDisplayValue(item)).find(Boolean) ||
    getSourceDisplayValue(itemData.value) ||
    getSourceDisplayValue(original.value)
  )
}

function getDescriptionText() {
  return (
    original.value?.description ||
    original.value?.summary ||
    original.value?.abstract ||
    original.value?.content ||
    ''
  )
}

function collectRelationDescriptions(source, values = [], seen = new Set()) {
  if (!source || typeof source !== 'object' || seen.has(source)) return values

  seen.add(source)
  values.push(
    source.description,
    source.properties?.description,
    source.raw?.r?.description,
    source.r?.description
  )

  const relatedSources = [
    source.original,
    source.raw,
    source.data?.original,
    source.data?.originals,
    source.originals,
    source.relationships
  ]

  for (const relatedSource of relatedSources) {
    if (Array.isArray(relatedSource)) {
      relatedSource.forEach((item) => collectRelationDescriptions(item, values, seen))
    } else {
      collectRelationDescriptions(relatedSource, values, seen)
    }
  }

  return values
}

function getRelationDescriptions(edge) {
  return toUniqueStrings(collectRelationDescriptions(edge))
}

const rawRelatedEdges = computed(() => {
  if (props.type === 'edge') {
    return [itemData.value].filter(Boolean)
  }

  const nodeId = currentId.value
  if (!nodeId) return []

  return props.edges.filter((edge) => {
    const source = String(edge.source_id || edge.source || '')
    const target = String(edge.target_id || edge.target || '')
    return source === nodeId || target === nodeId
  })
})

const relatedEdges = computed(() => {
  if (props.type === 'edge') {
    const source = String(itemData.value?.source || itemData.value?.source_id || '')
    const target = String(itemData.value?.target || itemData.value?.target_id || '')
    return [
      {
        id: itemData.value?.id || 'selected-edge',
        source,
        target,
        relationTypes: relationSourceTypes.value,
        relationCount:
          itemPayload.value?.relationCount || itemPayload.value?.originals?.length || 1,
        originals: itemPayload.value?.originals || []
      }
    ]
  }

  const edgeMap = new Map()

  for (const edge of rawRelatedEdges.value) {
    const source = String(edge.source_id || edge.source || '')
    const target = String(edge.target_id || edge.target || '')

    if (!source || !target) continue

    const key = [source, target].sort().join('__')
    const relationTypes = getRelationSourceTypes(edge)

    if (!edgeMap.has(key)) {
      edgeMap.set(key, {
        id: edge.id || `visual-edge-${edgeMap.size}`,
        source,
        target,
        relationTypes: [],
        relationCount: 0,
        originals: []
      })
    }

    const merged = edgeMap.get(key)

    relationTypes.forEach((relationType) => {
      if (!merged.relationTypes.includes(relationType)) {
        merged.relationTypes.push(relationType)
      }
    })

    merged.relationCount += 1
    merged.originals.push(edge)
  }

  return Array.from(edgeMap.values())
})

const relatedNodes = computed(() => {
  if (props.type === 'edge') {
    const sourceId = String(itemData.value?.source || itemData.value?.source_id || '')
    const targetId = String(itemData.value?.target || itemData.value?.target_id || '')
    return [sourceId, targetId].filter(Boolean).map((nodeId) => {
      const found = findNodeById(nodeId)
      return (
        found || {
          id: nodeId,
          name: nodeId,
          display_type: 'Entity'
        }
      )
    })
  }

  const nodeId = currentId.value
  const nodeMap = new Map()

  for (const edge of rawRelatedEdges.value) {
    const source = String(edge.source_id || edge.source || '')
    const target = String(edge.target_id || edge.target || '')
    const otherId = source === nodeId ? target : source

    if (!otherId || otherId === nodeId || nodeMap.has(otherId)) continue

    const found = findNodeById(otherId)

    if (found) {
      nodeMap.set(otherId, found)
    } else {
      nodeMap.set(otherId, {
        id: otherId,
        name: otherId,
        display_type: 'Entity'
      })
    }
  }

  return Array.from(nodeMap.values())
})

const overviewRows = computed(() => {
  if (props.type === 'edge') {
    const edge = relatedEdges.value[0]
    return [
      toOverviewRow(
        'count',
        '关系记录',
        edge?.relationCount || edge?.originals?.length || itemPayload.value?.relationCount
      ),
      toOverviewRow('type', '关系类型', edge?.relationTypes || relationSourceTypes.value, 'chips'),
      toOverviewRow('description', '关系描述', getRelationDescriptions(edge)),
      toOverviewRow('source', '起点节点', getNodeDisplayById(edge?.source)),
      toOverviewRow('target', '终点节点', getNodeDisplayById(edge?.target))
    ].filter(Boolean)
  }

  return [
    toOverviewRow('name', '节点名称', displayTitle.value),
    getNodeTypeOverviewRow(),
    toOverviewRow('description', '简短描述', getDescriptionText())
  ].filter(Boolean)
})

const normalizedDetail = computed(() => {
  return {
    type: props.type,
    id: currentId.value,
    title: displayTitle.value,
    displayType: displayType.value,
    labels: [],
    overview: overviewRows.value,
    sourceFile: props.type === 'edge' ? getRelationSourceText(relatedEdges.value[0]) : '',
    properties: original.value,
    relatedNodes: relatedNodes.value,
    relatedEdges: relatedEdges.value
  }
})

function getEdgeStableKey(edge) {
  return String(edge.id || `${edge.source}-${edge.target}-${getEdgeTitle(edge)}`)
}

function getEdgeTitle(edge) {
  const relationTypes = edge?.relationTypes || edge?.data?.relationTypes || []
  if (relationTypes.length === 0) {
    return getRelationSourceTypes(edge)[0] || '原始数据未提供'
  }

  if (relationTypes.length === 1) return relationTypes[0]

  return `${relationTypes[0]} +${relationTypes.length - 1}`
}

function getEdgeEndpointText(edge) {
  const source = edge?.source_id || edge?.source || ''
  const target = edge?.target_id || edge?.target || ''
  const count = edge?.relationCount || edge?.originals?.length || 1

  if (!source && !target) return '暂无端点信息'

  return `${getNodeDisplayById(source)} → ${getNodeDisplayById(target)}${count > 1 ? `｜原始边 ${count} 条` : ''}`
}

function handleFocusEdge(edge) {
  emit('focus-edge', {
    id: edge.id,
    source: edge.source_id || edge.source,
    target: edge.target_id || edge.target,
    type: getEdgeTitle(edge)
  })
}

function handleFocusNode(node) {
  emit('focus-node', {
    id: node?.id,
    name: node?.name,
    title: node?.title,
    label: node?.label,
    originalId: node?.original?.id,
    raw: node
  })
}

async function copyText(text, successMessage) {
  const value = String(text || '')
  if (!value) {
    message.warning('没有可复制的内容')
    return
  }

  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(value)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = value
      textarea.setAttribute('readonly', '')
      textarea.style.position = 'fixed'
      textarea.style.top = '-9999px'
      textarea.style.left = '-9999px'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
    }

    message.success(successMessage)
  } catch (error) {
    console.error(error)
    message.error('复制失败，请手动复制')
  }
}

function copyCurrentId() {
  copyText(currentId.value, '节点 ID 已复制')
}

function exportCurrentDetail() {
  copyText(JSON.stringify(normalizedDetail.value, null, 2), '节点详情已复制到剪贴板')
}

watch(
  [detailSignature, () => props.visible],
  async () => {
    activeTab.value = 'overview'
    await syncHeaderTitleDensity()
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  if (headerTitleFrameId) {
    cancelAnimationFrame(headerTitleFrameId)
    headerTitleFrameId = 0
  }
})
</script>

<style lang="less" scoped>
.kg-detail-card {
  width: 100%;
  height: 100%;
  min-height: 0;
  background: #ffffff;
  border: 1px solid var(--kg-primary-border-light, var(--main-200, #ddd6fe));
  border-radius: 18px;
  box-shadow: 0 18px 48px rgba(15, 23, 42, 0.16);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  contain: layout paint;
  user-select: text;
  --detail-primary: var(--kg-primary);
  --detail-primary-hover: var(--kg-primary-hover);
  --detail-primary-strong: var(--kg-primary-strong);
  --detail-primary-stronger: var(--kg-primary-stronger);
  --detail-primary-soft: var(--kg-primary-soft);
  --detail-primary-soft-2: var(--kg-primary-soft-2);
  --detail-primary-border: var(--kg-primary-border);
  --detail-primary-border-light: var(--kg-primary-border-light);
  --detail-text: var(--main-0, #fff);
  --detail-text-soft: rgba(255, 255, 255, 0.86);
  --detail-text-body: var(--color-text, #0f172a);
  --detail-text-secondary: var(--color-text-secondary, #475569);
  --detail-text-tertiary: var(--gray-500, #94a3b8);
  --detail-gradient: var(--app-primary-action-gradient);
  --detail-ring: var(--kg-primary-ring, rgba(139, 92, 246, 0.18));
}

.kg-detail-card * {
  user-select: text;
}

button,
.close-btn,
.tab-btn,
.primary-action,
.secondary-action {
  user-select: none;
}

.entity-title,
.info-key,
.info-value,
.node-main strong,
.node-main em,
.edge-main strong,
.edge-main em,
.pill,
.entity-tag {
  user-select: text;
}

.detail-header {
  background: var(--detail-gradient);
  color: var(--detail-text);
  position: relative;
  overflow: hidden;
  padding: 16px 16px 14px;
}

.detail-header--node {
  background:
    radial-gradient(circle at 14% 8%, rgba(255, 255, 255, 0.32), transparent 30%),
    var(--detail-gradient);
}

.detail-header--relation {
  background:
    radial-gradient(circle at 18% 10%, rgba(255, 255, 255, 0.28), transparent 28%),
    radial-gradient(circle at 82% 8%, rgba(255, 255, 255, 0.16), transparent 24%),
    var(--detail-gradient);
}

.detail-header__backdrop,
.detail-header__rail,
.detail-header__dots {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.detail-header__backdrop {
  background:
    radial-gradient(circle at 18% 24%, rgba(255, 255, 255, 0.18), transparent 15%),
    radial-gradient(circle at 72% 38%, rgba(255, 255, 255, 0.12), transparent 13%);
  opacity: 0.72;
}

.detail-header__rail {
  background-image:
    linear-gradient(
      140deg,
      transparent 0 45%,
      rgba(255, 255, 255, 0.12) 45% 46%,
      transparent 46% 100%
    ),
    linear-gradient(
      120deg,
      transparent 0 60%,
      rgba(255, 255, 255, 0.08) 60% 61%,
      transparent 61% 100%
    );
  opacity: 0.7;
}

.detail-header__dots {
  background-image:
    radial-gradient(circle, rgba(255, 255, 255, 0.2) 0 1.5px, transparent 1.6px),
    radial-gradient(circle, rgba(255, 255, 255, 0.14) 0 1px, transparent 1.1px);
  background-size:
    26px 26px,
    40px 40px;
  background-position:
    10px 12px,
    24px 30px;
  opacity: 0.35;
}

.detail-header__top {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-height: 100px;
  padding-right: 72px;
}

.detail-header__brand {
  min-width: 0;
  flex: 1;
  display: flex;
  align-items: center;
  gap: 12px;
}

.detail-header--node.detail-header--single-line-title .detail-header__top {
  align-items: center;
}

.detail-header--node.detail-header--single-line-title .detail-header__brand {
  align-items: center;
}

.detail-header--node.detail-header--single-line-title .detail-header__title-group {
  padding-top: 0;
  padding-bottom: 2px;
}

.detail-header--node.detail-header--single-line-title .detail-header__eyebrow {
  margin-bottom: 8px;
}

.detail-header--node.detail-header--single-line-title .detail-header__title {
  font-size: 22px;
  line-height: 1.15;
  margin-bottom: 10px;
}

.detail-header--node.detail-header--single-line-title .detail-header__chip-row {
  margin-top: 0;
}

.detail-header--node.detail-header--multi-line-title .detail-header__title {
  font-size: 17px;
  line-height: 1.16;
  margin-bottom: 0;
}

.detail-header__icon {
  width: 48px;
  height: 48px;
  border-radius: 999px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  background: rgba(255, 255, 255, 0.76);
  color: var(--detail-primary-stronger);
  box-shadow: 0 10px 24px var(--detail-ring);
  border: 1px solid rgba(255, 255, 255, 0.82);
}

.detail-header__icon.is-relation {
  background: rgba(255, 255, 255, 0.86);
  color: var(--detail-primary-stronger);
  backdrop-filter: blur(8px);
}

.detail-header__icon-text {
  font-size: 22px;
  font-weight: 800;
  line-height: 1;
}

.detail-header__icon-svg {
  width: 22px;
  height: 22px;
  stroke-width: 2.2;
}

.detail-header__title-group {
  min-width: 0;
  flex: 1;
  padding-top: 1px;
  padding-right: 8px;
}

.detail-header--relation .detail-header__title-group {
  padding-top: 0;
  padding-bottom: 2px;
}

.detail-header__eyebrow {
  font-size: 16px;
  font-weight: 800;
  line-height: 1.15;
  letter-spacing: 0.01em;
  color: var(--detail-text);
  margin-bottom: 6px;
  text-shadow: none;
}

.detail-header__title {
  margin: 0;
  font-size: 17px;
  line-height: 1.24;
  font-weight: 700;
  color: var(--detail-text);
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  white-space: normal;
  word-break: keep-all;
  overflow-wrap: break-word;
  hyphens: none;
  padding-bottom: 2px;
}

.detail-header__chip-row {
  margin-top: 9px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.detail-header__relation-lines {
  max-width: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-top: 6px;
}

.detail-header--relation-line-count-1 .detail-header__relation-lines {
  gap: 4px;
  margin-top: 8px;
}

.detail-header--relation-line-count-2 .detail-header__relation-lines {
  gap: 4px;
  margin-top: 7px;
}

.detail-header--relation-line-count-3 .detail-header__relation-lines {
  gap: 3px;
  margin-top: 6px;
}

.detail-header--relation-line-count-4 .detail-header__relation-lines {
  gap: 3px;
  margin-top: 6px;
}

.detail-header__relation-line {
  min-width: 0;
  color: var(--detail-text);
  font-size: 17px;
  font-weight: 800;
  line-height: 1.28;
  letter-spacing: 0.01em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding-bottom: 2px;
}

.detail-header--relation-line-count-1 .detail-header__relation-line {
  font-size: 20px;
  line-height: 1.28;
}

.detail-header--relation-line-count-2 .detail-header__relation-line {
  font-size: 18px;
  line-height: 1.26;
}

.detail-header--relation-line-count-3 .detail-header__relation-line,
.detail-header--relation-line-count-4 .detail-header__relation-line {
  font-size: 16px;
  line-height: 1.24;
}

.detail-header__relation-more {
  color: var(--detail-text-soft);
  font-size: 13px;
  font-weight: 700;
  line-height: 1.2;
  padding-top: 1px;
}

.detail-header__actions {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
}

.detail-header__close {
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 999px;
  display: inline-grid;
  place-items: center;
  flex-shrink: 0;
  color: var(--main-0, #fff);
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.82);
  cursor: pointer;
  backdrop-filter: blur(8px);
  transition:
    transform 0.18s ease,
    background 0.18s ease,
    border-color 0.18s ease;
}

.detail-header__close:hover {
  transform: translateY(-1px);
  background: rgba(255, 255, 255, 0.16);
  border-color: rgba(255, 255, 255, 0.9);
}

.detail-header__close-icon {
  width: 16px;
  height: 16px;
  stroke-width: 2.6;
}

.detail-tabs {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 0 14px;
  height: 46px;
  border-bottom: 1px solid var(--detail-primary-border-light);
  background: #ffffff;
}

.tab-btn {
  height: 46px;
  padding: 0 8px;
  border: none;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--color-text-secondary, var(--gray-600, rgba(0, 0, 0, 0.62)));
  opacity: 1;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  transition:
    color 0.18s ease,
    border-color 0.18s ease;
}

.tab-btn:hover {
  color: var(--detail-primary);
}

.tab-btn.active {
  color: var(--detail-primary-strong);
  border-bottom-color: var(--detail-primary-strong);
}

.detail-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  scrollbar-gutter: stable;
  overscroll-behavior: contain;
  padding: 16px 18px 20px;
  background: linear-gradient(180deg, #ffffff 0%, var(--detail-primary-soft) 100%);
}

.detail-section {
  min-height: 0;
}

.section-title {
  margin: 0 0 10px;
  color: var(--detail-text-body);
  font-size: 14px;
  font-weight: 800;
}

.section-title.compact {
  margin-top: 18px;
}

.section-title.no-margin {
  margin: 0;
}

.section-head {
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.section-count {
  min-width: 24px;
  height: 22px;
  border-radius: 999px;
  display: inline-grid;
  place-items: center;
  padding: 0 7px;
  font-size: 12px;
  color: var(--detail-primary-strong);
  background: var(--detail-primary-soft);
  border: 1px solid var(--detail-primary-border);
}

.info-list {
  border: 1px solid var(--detail-primary-border-light);
  border-radius: 14px;
  overflow: hidden;
  background: #ffffff;
}

.info-row {
  display: grid;
  grid-template-columns: 94px minmax(0, 1fr);
  border-bottom: 1px solid var(--detail-primary-border-light);
}

.info-row:last-child {
  border-bottom: none;
}

.info-key {
  padding: 10px;
  background: var(--detail-primary-soft);
  color: var(--detail-text-secondary);
  font-size: 12px;
  font-weight: 700;
  border-right: 1px solid var(--detail-primary-border-light);
}

.info-value {
  padding: 10px;
  color: var(--detail-text-body);
  font-size: 12px;
  line-height: 1.5;
  word-break: break-word;
  overflow-wrap: anywhere;
  white-space: normal;
}

.detail-row__text {
  color: var(--detail-text-body);
  line-height: 1.55;
  white-space: normal;
  word-break: break-word;
  overflow-wrap: anywhere;
}

.detail-row__text--multiline {
  white-space: pre-wrap;
}

.tag-cloud {
  min-height: 42px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  max-width: 100%;
  padding: 6px 12px;
  line-height: 1;
  border-radius: 999px;
  white-space: nowrap;
  color: var(--detail-primary);
  border: 1px solid var(--detail-primary-border);
  background: var(--detail-primary-soft);
  font-size: 12px;
  font-weight: 600;
}

.mini-pill {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid var(--detail-primary-border);
  background: var(--detail-primary-soft-2);
  color: var(--detail-primary);
  font-size: 11px;
  font-weight: 600;
  line-height: 1.2;
}

.empty-text.unclassified {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 11px;
  color: var(--detail-text-tertiary);
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
}

.node-list,
.edge-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.node-card,
.edge-card {
  width: 100%;
  border: 1px solid var(--detail-primary-border-light);
  background: #ffffff;
  border-radius: 14px;
  padding: 10px;
  display: flex;
  align-items: center;
  gap: 9px;
  text-align: left;
  cursor: pointer;
}

.node-card:hover,
.edge-card:hover {
  border-color: var(--detail-primary-border);
  background: var(--detail-primary-soft-2);
}

.mini-node-icon {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  border-radius: 999px;
  display: grid;
  place-items: center;
  background: var(--detail-primary-soft);
  border: 1px solid var(--detail-primary-border);
  color: var(--detail-primary);
  font-size: 12px;
  font-weight: 800;
}

.node-main,
.edge-main {
  flex: 1;
  min-width: 0;
}

.node-main strong,
.edge-main strong {
  display: block;
  color: var(--detail-text-body);
  font-size: 13px;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-main em,
.edge-main em {
  display: block;
  margin-top: 3px;
  color: var(--detail-text-secondary);
  font-size: 11px;
  font-style: normal;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.jump-icon {
  flex-shrink: 0;
  color: var(--detail-primary);
  font-size: 12px;
  font-weight: 700;
}

.edge-dot {
  width: 9px;
  height: 9px;
  border-radius: 999px;
  background: var(--detail-primary);
  box-shadow: 0 0 0 4px var(--detail-primary-soft);
  flex-shrink: 0;
}

.empty-block {
  padding: 28px 12px;
  border: 1px dashed #cbd5e1;
  border-radius: 14px;
  background: rgba(248, 250, 252, 0.7);
  color: var(--detail-text-tertiary);
  text-align: center;
}

.empty-text {
  color: var(--detail-text-tertiary);
  font-size: 12px;
}

.detail-actions {
  flex-shrink: 0;
  padding: 12px 16px 16px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  border-top: 1px solid var(--detail-primary-border-light);
  background: #ffffff;
}

.primary-action,
.secondary-action {
  height: 36px;
  border-radius: 10px;
  cursor: pointer;
  font-weight: 700;
  font-size: 13px;
}

.primary-action {
  border: none;
  color: var(--app-primary-action-text);
  background: var(--app-primary-action-gradient);
  box-shadow: var(--app-primary-action-shadow);
}

.secondary-action {
  color: var(--detail-primary-strong);
  border: 1px solid var(--detail-primary-border);
  background: #ffffff;
}

.primary-action:hover,
.secondary-action:hover {
  transform: translateY(-1px);
}

.primary-action:hover {
  background: var(--app-primary-action-gradient-hover);
  color: var(--app-primary-action-text);
  box-shadow: var(--app-primary-action-shadow-hover);
}

.secondary-action:hover {
  background: var(--detail-primary-soft-2);
  border-color: var(--detail-primary-strong);
  color: var(--detail-primary-strong);
}

@media (max-width: 640px) {
  .hero-top {
    flex-direction: column;
  }

  .hero-actions {
    width: 100%;
    justify-content: space-between;
  }
}
</style>
