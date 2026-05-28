<template>
  <div class="database-empty" v-if="!state.showPage">
    <a-empty>
      <template #description>
        <span> 点击右上角用户头像中的"系统设置"来启用知识图谱。 </span>
      </template>
    </a-empty>
  </div>
  <div class="graph-container layout-container" v-else>
    <PageHeader
      title="知识库"
      :active-key="knowledgeActiveView"
      :tabs="knowledgeViewItems"
      aria-label="知识库视图切换"
      :show-border="true"
    >
      <template #actions>
        <div class="db-selector">
          <div class="status-wrapper">
            <div class="status-indicator" :class="graphStatusClass"></div>
            <span class="status-text">{{ graphStatusText }}</span>
          </div>
          <span class="label">知识库: </span>
          <a-select
            v-model:value="state.selectedDbId"
            style="width: 200px"
            :options="state.dbOptions"
            @change="handleDbChange"
            :loading="state.loadingDatabases"
            mode="combobox"
            placeholder="选择或输入KB ID"
          />
        </div>
      </template>
    </PageHeader>

    <div class="graph-shoulder">
      <div class="graph-shoulder-left">
        <a-input
          v-model:value="state.searchInput"
          placeholder="输入要查询的实体 (*为全部)"
          style="width: 300px"
          @keydown.enter="onSearch"
          allow-clear
        >
          <template #suffix>
            <component
              :is="state.searchLoading ? LoadingOutlined : SearchOutlined"
              @click="onSearch"
            />
          </template>
        </a-input>
        <a-input
          v-model:value="sampleNodeCount"
          placeholder="查询数量"
          style="width: 100px"
          @keydown.enter="loadSampleNodes"
          :loading="graph.fetching"
        >
          <template #suffix>
            <component
              :is="graph.fetching ? LoadingOutlined : ReloadOutlined"
              @click="loadSampleNodes"
            />
          </template>
        </a-input>
      </div>
      <div class="graph-shoulder-right">
        <a-button v-if="isNeo4j" type="primary" @click="state.showModal = true">
          <UploadOutlined /> 上传文件
        </a-button>
        <a-button v-else type="primary" @click="state.showUploadTipModal = true">
          <UploadOutlined /> 上传文件
        </a-button>
        <a-button
          v-if="unindexedCount > 0"
          type="primary"
          @click="indexNodes"
          :loading="state.indexing"
        >
          <SyncOutlined v-if="!state.indexing" /> 为{{ unindexedCount }}个节点添加索引
        </a-button>
      </div>
    </div>

    <div class="container-outter">
      <div class="graph-workspace" :class="{ 'detail-open': isDetailDrawerOpen }">
        <div class="graph-canvas-wrap">
          <GraphCanvas
            ref="graphRef"
            :graph-data="graph.graphData"
            :graph-info="formattedGraphInfo"
            :highlight-keywords="[state.searchInput]"
            @node-click="handleGraphNodeClick"
            @edge-click="handleGraphEdgeClick"
            @canvas-click="closeGraphDetailDrawer"
            class="graph-canvas"
          >
            <template #content>
              <a-empty v-show="graph.graphData.nodes.length === 0" style="padding: 4rem 0" />
            </template>
          </GraphCanvas>
        </div>

        <Transition
          name="kg-detail-layout"
          @after-enter="handleDetailDrawerAfterEnter"
          @after-leave="handleDetailDrawerAfterLeave"
        >
          <aside v-if="isDetailDrawerOpen" class="graph-detail-pane">
            <GraphDetailPanel
              class="graph-detail-drawer"
              :visible="true"
              :item="graph.selectedItem"
              :type="graph.selectedItemType"
              :nodes="graph.graphData.nodes"
              :edges="graph.graphData.edges"
              @close="closeGraphDetailDrawer"
              @focus-node="handleDetailFocusNode"
              @focus-edge="handleDetailFocusEdge"
            />
          </aside>
        </Transition>
      </div>
    </div>

    <a-modal
      :open="state.showModal"
      title="上传文件"
      @ok="addDocumentByFile"
      @cancel="handleModalCancel"
      ok-text="添加到图数据库"
      cancel-text="取消"
      :confirm-loading="state.processing"
      :ok-button-props="{ disabled: !hasValidFile }"
    >
      <div class="upload">
        <div class="note">
          <p>上传的文件内容参考 test/data/A_Dream_of_Red_Mansions_tiny.jsonl 中的格式：</p>
        </div>
        <div class="upload-config">
          <div class="config-row">
            <label class="config-label">嵌入模型</label>
            <div class="config-field">
              <EmbeddingModelSelector
                v-model:value="state.embedModelName"
                :disabled="!embedModelConfigurable"
                :style="{ width: '100%' }"
              />
            </div>
          </div>
          <div v-if="!embedModelConfigurable" class="config-hint-row">
            * 图数据库已有数据或已设定模型，不可更改
          </div>
          <div class="config-row">
            <label class="config-label">批处理大小</label>
            <div class="config-field">
              <a-input-number
                v-model:value="state.batchSize"
                :min="1"
                :max="1000"
                style="width: 100%"
              />
            </div>
          </div>
          <div class="config-hint-row">默认值: 40，范围: 1-1000</div>
        </div>
        <a-upload-dragger
          class="upload-dragger"
          v-model:fileList="fileList"
          name="file"
          :fileList="fileList"
          :max-count="1"
          accept=".jsonl"
          action="/api/knowledge/files/upload?allow_jsonl=true"
          :headers="getAuthHeaders()"
          @change="handleFileUpload"
          @drop="handleDrop"
        >
          <p class="ant-upload-text">点击或者把文件拖拽到这里上传</p>
          <p class="ant-upload-hint">目前仅支持上传 jsonl 文件。</p>
        </a-upload-dragger>
      </div>
    </a-modal>

    <!-- 上传提示弹窗 -->
    <a-modal
      :open="state.showUploadTipModal"
      title="文件上传说明"
      @cancel="() => (state.showUploadTipModal = false)"
      :footer="null"
      width="500px"
    >
      <div class="upload-tip-content">
        <a-alert
          :message="getUploadTipMessage()"
          type="info"
          show-icon
          style="margin-bottom: 16px"
        />
        <div v-if="!isNeo4j" class="upload-tip-actions">
          <p>如需上传文档到当前选中的知识库，请前往对应的知识库详情页面进行操作：</p>
          <div class="action-buttons">
            <a-button type="primary" @click="goToDatabasePage">
              <DatabaseOutlined /> 前往知识库详情页
            </a-button>
          </div>
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { useConfigStore } from '@/stores/config'
import {
  UploadOutlined,
  SyncOutlined,
  SearchOutlined,
  ReloadOutlined,
  LoadingOutlined
} from '@ant-design/icons-vue'
import PageHeader from '@/components/shared/PageHeader.vue'
import { neo4jApi, unifiedApi } from '@/apis/graph_api'
import { useUserStore } from '@/stores/user'
import GraphCanvas from '@/components/GraphCanvas.vue'
import GraphDetailPanel from '@/components/GraphDetailPanel.vue'
import EmbeddingModelSelector from '@/components/EmbeddingModelSelector.vue'
import { useGraph } from '@/composables/useGraph'
import { isSameEmbeddingModelSpec } from '@/utils/kb_utils'

const handleExportDetail = async (detail) => {
  try {
    await navigator.clipboard.writeText(JSON.stringify(detail, null, 2))
    message.success('节点详情已复制到剪贴板')
  } catch {
    message.error('导出失败，请手动复制')
  }
}

const configStore = useConfigStore()
const cur_embed_model = computed(() => configStore.config?.embed_model)
const knowledgeActiveView = 'graph'
const knowledgeViewItems = [
  // { key: 'documents', label: '文档知识库', path: '/database' },
  { key: 'graph', label: '知识图谱', path: '/graph' }
]
const modelMatched = computed(
  () =>
    !graphInfo?.value?.embed_model_name ||
    isSameEmbeddingModelSpec(graphInfo.value.embed_model_name, cur_embed_model.value)
)

const router = useRouter()
const graphRef = ref(null)
const graphInfo = ref(null)
const fileList = ref([])
const sampleNodeCount = ref(100)

const graph = reactive(useGraph(graphRef))

// 控制侧边详情抽屉的打开状态：当 graph.showDetailDrawer 为 true 且有选中项时才显示
const isDetailDrawerOpen = computed(() => {
  return Boolean(graph.showDetailDrawer && graph.selectedItem)
})

const graphCenterTimer = ref(null)
const pendingCenterTarget = ref(null)
const pendingCloseReset = ref(false)

const closeGraphDetailDrawer = () => {
  pendingCloseReset.value = true
  pendingCenterTarget.value = null

  // 只先关闭详情面板，不要立刻 resize / fitCenter
  graph.handleCanvasClick()
}

function getGraphItemId(item) {
  return String(item?.id || item?.data?.id || item?.data?.original?.id || item?.original?.id || '')
}

function getGraphEdgePayload(edgeData) {
  return {
    id: edgeData?.id,
    source: edgeData?.source_id || edgeData?.source,
    target: edgeData?.target_id || edgeData?.target,
    type: edgeData?.type || edgeData?.label || edgeData?.name || edgeData?.data?.label
  }
}

function setPendingCenter(target) {
  pendingCenterTarget.value = target
}

function scheduleCenterToPending(delay = 0) {
  clearTimeout(graphCenterTimer.value)

  graphCenterTimer.value = setTimeout(async () => {
    const target = pendingCenterTarget.value
    if (!target) return

    // 关键：先让 GraphCanvas 重新读取抽屉展开后的真实画布尺寸
    await graphRef.value?.resizeToContainer?.()

    // 再居中，而不是用抽屉展开前的旧画布尺寸
    if (target.type === 'node') {
      await graphRef.value?.centerNodeInCanvas?.(target.id)
    } else if (target.type === 'edge') {
      await graphRef.value?.centerEdgeInCanvas?.(target.payload)
    }
  }, delay)
}

function requestCenterEdge(edgePayload, delay = 320) {
  clearTimeout(graphCenterTimer.value)

  graphCenterTimer.value = setTimeout(() => {
    if (!edgePayload) return
    graphRef.value?.centerEdgeInCanvas?.(edgePayload)
  }, delay)
}

function handleGraphNodeClick(nodeData) {
  const drawerAlreadyOpen = isDetailDrawerOpen.value
  graph.handleNodeClick(nodeData)

  const nodeId = getGraphItemId(nodeData)
  setPendingCenter({
    type: 'node',
    id: nodeId
  })

  // 如果抽屉已经展开，直接按当前区域居中
  // 如果抽屉刚打开，则等 after-enter 统一处理
  if (drawerAlreadyOpen) {
    scheduleCenterToPending(80)
  }
}

function handleGraphEdgeClick(edgeData) {
  const drawerAlreadyOpen = isDetailDrawerOpen.value
  graph.handleEdgeClick(edgeData)

  const edgePayload = getGraphEdgePayload(edgeData)
  setPendingCenter({
    type: 'edge',
    payload: edgePayload
  })

  if (drawerAlreadyOpen) {
    scheduleCenterToPending(80)
  }
}

function resolveGraphNodeId(payload) {
  const candidateIds = [
    payload?.id,
    payload?.originalId,
    payload?.raw?.id,
    payload?.raw?.original?.id,
    payload?.name,
    payload?.title,
    payload?.label
  ]
    .filter(Boolean)
    .map(String)

  const matched = graph.graphData.nodes.find((node) => {
    const values = [
      node?.id,
      node?.name,
      node?.title,
      node?.label,
      node?.original?.id,
      node?.original?.name,
      node?.original?.title
    ]
      .filter(Boolean)
      .map(String)

    return candidateIds.some((id) => values.includes(id))
  })

  return matched ? String(matched.id) : String(payload?.id || '')
}

function handleDetailFocusNode(payload) {
  const nodeId = resolveGraphNodeId(payload)
  if (!nodeId) return

  const matchedNode = graph.graphData.nodes.find((node) => String(node.id) === nodeId)

  if (matchedNode) {
    graph.handleNodeClick(matchedNode)
  }

  graphRef.value?.focusNodeFromDetail?.(nodeId)
}

function handleDetailFocusEdge(edgePayload) {
  graphRef.value?.focusEdgeFromDetail?.(edgePayload)

  setPendingCenter({
    type: 'edge',
    payload: edgePayload
  })

  scheduleCenterToPending(80)
}

function handleDetailDrawerAfterEnter() {
  // 抽屉动画完成后，再按缩小后的画布区域居中
  scheduleCenterToPending(60)
}

async function handleDetailDrawerAfterLeave() {
  clearTimeout(graphCenterTimer.value)
  pendingCenterTarget.value = null

  if (!pendingCloseReset.value) return

  pendingCloseReset.value = false

  await nextTick()

  // 关键：抽屉完全收起之后，再恢复图谱状态和重新居中
  setTimeout(async () => {
    await graphRef.value?.clearGraphSelection?.()
    await graphRef.value?.resizeToContainer?.()
    await graphRef.value?.fitGraphToCurrentCanvas?.()
  }, 60)
}

watch(isDetailDrawerOpen, async (open, oldOpen) => {
  await nextTick()

  // 打开抽屉时，给一个兜底居中
  if (open && !oldOpen) {
    scheduleCenterToPending(380)
  }

  // 关闭抽屉时，不在这里做任何 fitCenter / resize
  // 统一交给 handleDetailDrawerAfterLeave
})

const state = reactive({
  loadingGraphInfo: false,
  loadingDatabases: false,
  searchInput: '',
  searchLoading: false,
  showModal: false,
  showInfoModal: false,
  showUploadTipModal: false,
  processing: false,
  indexing: false,
  showPage: true,
  selectedDbId: 'neo4j',
  dbOptions: [],
  lightragStats: null,
  embedModelName: '',
  batchSize: 40
})

const isNeo4j = computed(() => {
  return state.selectedDbId === 'neo4j'
})

const embedModelConfigurable = computed(() => {
  return graphInfo.value?.embed_model_configurable ?? true
})

// 检查是否有有效的已上传文件
const hasValidFile = computed(() => {
  return fileList.value.some((file) => file.status === 'done' && file.response?.file_path)
})

// 计算未索引节点数量
const unindexedCount = computed(() => {
  return graphInfo.value?.unindexed_node_count || 0
})

const formattedGraphInfo = computed(() => {
  if (isNeo4j.value) {
    return {
      node_count: graphInfo.value?.entity_count || 0,
      edge_count: graphInfo.value?.relationship_count || 0
    }
  } else {
    return {
      node_count: state.lightragStats?.total_nodes || 0,
      edge_count: state.lightragStats?.total_edges || 0
    }
  }
})

const loadDatabases = async () => {
  state.loadingDatabases = true
  try {
    const res = await unifiedApi.getGraphs()
    if (res.success && res.data) {
      state.dbOptions = res.data.map((db) => ({
        label: `${db.name} (${db.type})`,
        value: db.id,
        type: db.type
      }))

      // If no selection or invalid selection, select first
      if (!state.selectedDbId || !state.dbOptions.find((o) => o.value === state.selectedDbId)) {
        if (state.dbOptions.length > 0) {
          state.selectedDbId = state.dbOptions[0].value
        }
      }
    }
  } catch (error) {
    console.error('Failed to load databases:', error)
  } finally {
    state.loadingDatabases = false
  }
}

const handleDbChange = () => {
  // Clear current data
  graph.clearGraph()
  state.searchInput = ''
  state.lightragStats = null

  if (isNeo4j.value) {
    loadGraphInfo()
  } else {
    // Also load stats for LightRAG or KB
    loadLightRAGStats()
  }
  loadSampleNodes()
}

const loadLightRAGStats = () => {
  unifiedApi
    .getStats(state.selectedDbId)
    .then((res) => {
      if (res.success) {
        state.lightragStats = res.data
      }
    })
    .catch((e) => console.error(e))
}

const loadGraphInfo = () => {
  state.loadingGraphInfo = true
  neo4jApi
    .getInfo()
    .then((data) => {
      console.log(data)
      graphInfo.value = data.data
      if (graphInfo.value?.embed_model_name) {
        state.embedModelName = graphInfo.value.embed_model_name
      } else {
        // Default if not set (though backend usually sends default)
        state.embedModelName = cur_embed_model.value
      }
      state.loadingGraphInfo = false
    })
    .catch((error) => {
      console.error(error)
      message.error(error.message || '加载图数据库信息失败')
      state.loadingGraphInfo = false
    })
}

const addDocumentByFile = () => {
  // 使用计算属性验证文件
  if (!hasValidFile.value) {
    message.error('请先等待文件上传完成')
    return
  }

  if (!state.embedModelName) {
    message.error('请选择嵌入模型')
    return
  }

  state.processing = true

  // 获取已上传的文件路径
  const uploadedFile = fileList.value.find(
    (file) => file.status === 'done' && file.response?.file_path
  )
  const filePath = uploadedFile?.response?.file_path

  // 再次验证文件路径
  if (!filePath) {
    message.error('文件路径获取失败，请重新上传文件')
    state.processing = false
    return
  }

  neo4jApi
    .addEntities(filePath, 'neo4j', state.embedModelName, state.batchSize)
    .then((data) => {
      if (data.status === 'success') {
        message.success(data.message)
        state.showModal = false
        // 清空文件列表
        fileList.value = []
        // 刷新图谱数据
        setTimeout(() => {
          loadGraphInfo()
          loadSampleNodes()
        }, 500)
      } else {
        throw new Error(data.message)
      }
    })
    .catch((error) => {
      console.error(error)
      message.error(error.message || '添加文件失败')
    })
    .finally(() => (state.processing = false))
}

const loadSampleNodes = () => {
  graph.fetching = true

  unifiedApi
    .getSubgraph({
      db_id: state.selectedDbId,
      node_label: '*',
      max_nodes: sampleNodeCount.value
    })
    .then((data) => {
      // Normalize data structure if needed
      const result = data.data
      graph.updateGraphData(result.nodes, result.edges)
      console.log(graph.graphData)
    })
    .catch((error) => {
      console.error(error)
      message.error(error.message || '加载节点失败')
    })
    .finally(() => (graph.fetching = false))
}

const onSearch = () => {
  if (state.searchLoading) {
    message.error('请稍后再试')
    return
  }

  if (isNeo4j.value && graphInfo?.value?.embed_model_name !== cur_embed_model.value) {
    // 可选：提示模型不一致
  }

  state.searchLoading = true

  unifiedApi
    .getSubgraph({
      db_id: state.selectedDbId,
      node_label: state.searchInput || '*',
      max_nodes: sampleNodeCount.value
    })
    .then((data) => {
      const result = data.data
      if (!result || !result.nodes || !result.edges) {
        throw new Error('返回数据格式不正确')
      }
      graph.updateGraphData(result.nodes, result.edges)
      if (graph.graphData.nodes.length === 0) {
        message.info('未找到相关实体')
      }
      console.log(data)
      console.log(graph.graphData)
    })
    .catch((error) => {
      console.error('查询错误:', error)
      message.error(`查询出错：${error.message || '未知错误'}`)
    })
    .finally(() => (state.searchLoading = false))
}

onMounted(async () => {
  await loadDatabases()
  loadGraphInfo() // Load default (Neo4j) info
  loadSampleNodes()
})

const handleFileUpload = ({ file, fileList: newFileList }) => {
  // 更新文件列表
  fileList.value = newFileList

  // 如果上传失败，显示错误信息
  if (file.status === 'error') {
    message.error(`文件上传失败: ${file.name}`)
  }

  // 如果上传成功，显示成功信息
  if (file.status === 'done' && file.response?.file_path) {
    message.success(`文件上传成功: ${file.name}`)
  }

  console.log('File upload status:', file.status, file.name)
  console.log('File list:', fileList.value)
}

const handleDrop = (event) => {
  console.log(event)
  console.log(fileList.value)
}

const handleModalCancel = () => {
  state.showModal = false
  // 重置文件列表
  fileList.value = []
}

const graphStatusClass = computed(() => {
  if (state.loadingGraphInfo) return 'loading'
  return graphInfo.value?.status === 'open' ? 'open' : 'closed'
})

const graphStatusText = computed(() => {
  if (state.loadingGraphInfo) return '加载中'
  return graphInfo.value?.status === 'open' ? '已连接' : '已关闭'
})

// 为未索引节点添加索引
const indexNodes = () => {
  // 判断 embed_model_name 是否相同
  if (!modelMatched.value) {
    message.error(
      `向量模型不匹配，无法添加索引，当前向量模型为 ${cur_embed_model.value}，图数据库向量模型为 ${graphInfo.value?.embed_model_name}`
    )
    return
  }

  if (state.processing) {
    message.error('后台正在处理，请稍后再试')
    return
  }

  state.indexing = true
  neo4jApi
    .indexEntities('neo4j')
    .then((data) => {
      message.success(data.message || '索引添加成功')
      // 刷新图谱信息
      loadGraphInfo()
    })
    .catch((error) => {
      console.error(error)
      message.error(error.message || '添加索引失败')
    })
    .finally(() => {
      state.indexing = false
    })
}

const getAuthHeaders = () => {
  const userStore = useUserStore()
  return userStore.getAuthHeaders()
}

const getDatabaseName = () => {
  const selectedDb = state.dbOptions.find((db) => db.value === state.selectedDbId)
  return selectedDb ? selectedDb.label : state.selectedDbId
}

const getUploadTipMessage = () => {
  if (isNeo4j.value) {
    return 'Neo4j 图数据库支持通过上传 JSONL 格式文件直接导入实体和关系数据。'
  } else {
    const selectedDb = state.dbOptions.find((db) => db.value === state.selectedDbId)
    const dbType = selectedDb?.type || '未知'
    const dbName = selectedDb?.label || getDatabaseName()
    return `当前选择的是 ${dbType.toUpperCase()} 类型的知识库"${dbName}"，该类型知识库需要在文档知识库页面上传文档，系统会自动从中提取知识图谱。`
  }
}

const goToDatabasePage = () => {
  state.showUploadTipModal = false

  // 如果不是 Neo4j，需要找到对应的知识库 ID 并跳转
  if (!isNeo4j.value) {
    const selectedDb = state.dbOptions.find((db) => db.value === state.selectedDbId)
    if (selectedDb && selectedDb.type !== 'neo4j') {
      // 跳转到对应的知识库详情页面
      router.push(`/database/${state.selectedDbId}`)
    } else {
      // 如果找不到对应的数据库，跳转到数据库列表页面
      router.push('/database')
    }
  }
}
</script>

<style lang="less" scoped>
@graph-header-height: 50px;

.graph-container {
  --kg-primary: var(--main-500);
  --kg-primary-hover: var(--main-400);
  --kg-primary-strong: var(--main-600);
  --kg-primary-stronger: var(--main-700);
  --kg-primary-soft: color-mix(in srgb, var(--main-50) 78%, white);
  --kg-primary-soft-2: color-mix(in srgb, var(--main-100) 70%, white);
  --kg-primary-border: color-mix(in srgb, var(--main-300) 78%, white);
  --kg-primary-border-light: color-mix(in srgb, var(--main-200) 82%, white);
  --kg-primary-ring: color-mix(in srgb, var(--main-500) 18%, transparent);
  --kg-gradient: linear-gradient(
    135deg,
    var(--kg-primary-stronger) 0%,
    var(--kg-primary-strong) 45%,
    var(--kg-primary) 100%
  );
  --kg-button-gradient: var(--app-primary-action-gradient);
  --kg-button-gradient-hover: var(--app-primary-action-gradient-hover);
  --kg-button-text: var(--app-primary-action-text);

  padding: 0;
  background-color: var(--main-30);
}

:global(.app-layout .app-sidebar .nav-item.primary-action) {
  background: var(--app-primary-action-gradient) !important;
  color: var(--app-primary-action-text) !important;
  box-shadow: var(--app-primary-action-shadow) !important;
}

:global(.app-layout .app-sidebar .nav-item.primary-action:hover) {
  background: var(--app-primary-action-gradient-hover) !important;
  color: var(--app-primary-action-text) !important;
  box-shadow: var(--app-primary-action-shadow-hover) !important;
}

.db-selector {
  display: flex;
  align-items: center;

  .label {
    font-size: 14px;
    margin-right: 8px;
  }
}

.status-wrapper {
  display: flex;
  align-items: center;
  margin-right: 16px;
  font-size: 14px;
  color: var(--color-text-secondary);
}

.status-text {
  margin-left: 8px;
}

.status-indicator {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  display: inline-block;

  &.loading {
    background-color: var(--color-warning-500);
    animation: pulse 1.5s infinite ease-in-out;
  }

  &.open {
    background-color: var(--color-success-500);
  }

  &.closed {
    background-color: var(--color-error-500);
  }
}

@keyframes pulse {
  0% {
    transform: scale(0.8);
    opacity: 0.5;
  }
  50% {
    transform: scale(1.2);
    opacity: 1;
  }
  100% {
    transform: scale(0.8);
    opacity: 0.5;
  }
}

.upload {
  margin-bottom: 20px;

  .upload-dragger {
    margin: 0px;
  }

  .upload-config {
    margin: 24px 0;
    padding: 16px;
    background-color: var(--gray-0);
    border-radius: 4px;

    .config-row {
      display: flex;
      align-items: center;
      margin-bottom: 16px;

      &:last-of-type {
        margin-bottom: 0;
      }

      .config-label {
        width: 100px;
        flex-shrink: 0;
        font-size: 14px;
        color: var(--color-text);
        text-align: right;
        margin-right: 16px;
      }

      .config-field {
        flex: 1;
        min-width: 0;
      }
    }

    .config-hint-row {
      margin-bottom: 16px;
      padding-left: 116px;
      font-size: 12px;
      color: var(--color-text-secondary);
      line-height: 1.5;

      &:last-child {
        margin-bottom: 0;
      }
    }
  }
}

.container-outter {
  width: 100%;
  height: calc(100vh - @graph-header-height - 60px);
  overflow: hidden;
  background: var(--gray-10);
  padding: 16px var(--page-padding);

  .graph-workspace {
    --detail-drawer-width: clamp(320px, 28%, 460px);
    --detail-drawer-gap: clamp(10px, 1.2vw, 16px);

    width: 100%;
    height: 100%;
    display: flex;
    align-items: stretch;
    overflow: hidden;
  }

  .graph-canvas-wrap {
    flex: 1 1 auto;
    min-width: 0;
    height: 100%;
    overflow: hidden;
    border: 1px solid var(--main-border-light);
    box-shadow: 0 16px 40px color-mix(in srgb, var(--kg-primary) 12%, transparent);
    border-radius: 12px;
    background: #ffffff;
    transition:
      flex-basis 0.28s ease,
      width 0.28s ease;
  }

  .graph-canvas {
    width: 100%;
    height: 100%;
  }

  .graph-detail-pane {
    flex: 0 0 var(--detail-drawer-width);
    width: var(--detail-drawer-width);
    height: 100%;
    margin-left: var(--detail-drawer-gap);
    overflow: hidden;
    z-index: 1200;
    border-radius: 18px;
  }

  .graph-detail-drawer {
    width: 100%;
    height: 100%;
  }

  .kg-detail-layout-enter-active,
  .kg-detail-layout-leave-active {
    transition:
      width 0.28s ease,
      flex-basis 0.28s ease,
      margin-left 0.28s ease,
      transform 0.28s ease,
      opacity 0.22s ease;
  }

  .kg-detail-layout-enter-from,
  .kg-detail-layout-leave-to {
    flex-basis: 0;
    width: 0;
    margin-left: 0;
    transform: translateX(2rem);
    opacity: 0;
  }

  .kg-detail-layout-enter-to,
  .kg-detail-layout-leave-from {
    flex-basis: var(--detail-drawer-width);
    width: var(--detail-drawer-width);
    margin-left: var(--detail-drawer-gap);
    transform: translateX(0);
    opacity: 1;
  }
}

.graph-shoulder {
  :deep(.ant-btn-primary) {
    border-color: transparent;
    background: var(--kg-button-gradient);
    color: var(--kg-button-text);
    box-shadow: var(--app-primary-action-shadow);
  }

  :deep(.ant-btn-primary:hover),
  :deep(.ant-btn-primary:focus) {
    border-color: transparent;
    background: var(--kg-button-gradient-hover);
    color: var(--kg-button-text);
    box-shadow: var(--app-primary-action-shadow-hover);
  }
}

.graph-container {
  :deep(.ant-input-affix-wrapper:hover),
  :deep(.ant-input-number:hover),
  :deep(.ant-select:hover .ant-select-selector) {
    border-color: var(--kg-primary-border);
  }

  :deep(.ant-input-affix-wrapper-focused),
  :deep(.ant-input-number-focused),
  :deep(.ant-select-focused .ant-select-selector) {
    border-color: var(--kg-primary-border);
    box-shadow: 0 0 0 2px var(--kg-primary-ring);
  }

  :deep(.ant-select-selector),
  :deep(.ant-input-number),
  :deep(.ant-input-affix-wrapper) {
    transition:
      border-color 0.2s ease,
      box-shadow 0.2s ease;
  }
}

@media (max-width: 1280px) {
  .container-outter {
    .graph-workspace {
      --detail-drawer-width: clamp(20rem, 31vw, 27rem);
    }
  }
}

@media (max-width: 960px) {
  .container-outter {
    .graph-workspace {
      position: relative;
      --detail-drawer-width: min(86vw, 28rem);
    }

    .graph-detail-pane {
      position: absolute;
      top: 0;
      right: 0;
      bottom: 0;
      margin-left: 0;
      box-shadow: -18px 0 40px rgba(15, 23, 42, 0.12);
    }
  }
}

.graph-shoulder {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px var(--page-padding) 0;

  &-left,
  &-right {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  :deep(.ant-input) {
    padding: 2px 0px;
  }

  button {
    box-shadow: none;
  }
}

.upload-tip-content {
  .upload-tip-actions {
    p {
      margin-bottom: 16px;
      color: var(--color-text-secondary);
    }
  }

  .action-buttons {
    display: flex;
    justify-content: center;
    margin-top: 20px;
  }
}
</style>
