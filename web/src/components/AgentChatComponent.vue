<template>
  <div class="chat-container">
    <div class="chat">
      <div class="chat-header">
        <div class="header__left">
          <slot name="header-left"></slot>
          <div
            v-if="currentThread?.title && currentThread.title !== '新的对话'"
            class="conversation-title"
          >
            {{ currentThread.title }}
          </div>
        </div>
        <div class="header__right">
          <UserInfoComponent v-if="!userStore.isAdmin" />
          <!-- AgentState 显示按钮已移动到输入框底部 -->
          <slot name="header-right"></slot>
        </div>
      </div>

      <div class="chat-content-container">
        <!-- Main Chat Area -->
        <div class="chat-main" :class="{ 'has-conversations': conversations.length > 0 }" ref="chatMainRef">
          <div v-if="!conversations.length" class="start-hero">
            <div class="start-hero-card">
              <img class="start-hero-logo" src="/favicon.svg" alt="logo" />
              <div class="start-hero-text">
                <h1>{{ randomGreeting }}</h1>
                <p>我可以围绕杂粮育种问题，整合文献、知识图谱与检索证据，生成可追溯的育种分析报告</p>
              </div>
            </div>
          </div>
          <div v-if="!conversations.length" class="start-showcase">
            <section class="showcase-column">
              <div class="section-title">
                <span class="section-dot"></span>
                <span>育种应用场景</span>
              </div>

              <div class="task-grid" aria-label="杂粮育种应用场景">
                <article
                  v-for="task in breedingTasks"
                  :key="task.title"
                  class="task-card"
                >
                  <div class="task-icon">{{ task.icon }}</div>
                  <div class="task-content">
                    <div class="task-title">{{ task.title }}</div>
                    <div class="task-desc">{{ task.desc }}</div>
                  </div>
                </article>
              </div>
            </section>

            <section class="showcase-column showcase-column-right">
              <div class="section-title">
                <span class="section-dot"></span>
                <span>模型支持能力</span>
              </div>

              <div class="model-card">
                <div class="model-card-main">
                  <div>
                    <div class="model-kicker">杂粮育种报告生成</div>
                    <p>
                      面向杂粮育种科学问题，整合育种知识图谱、文献检索、网络检索与知识蒸馏能力，支持候选基因识别、机制证据整合、验证路径设计和可追溯育种报告生成
                    </p>
                  </div>

                  <div class="crop-tags">
                    <span v-for="crop in breedingCropTags" :key="crop">{{ crop }}</span>
                  </div>
                </div>

                <div class="capability-tags">
                  <span v-for="tag in breedingCapabilityTags" :key="tag">{{ tag }}</span>
                </div>
              </div>

              <div class="workflow-card">
                <div class="workflow-line"></div>

                <div
                  v-for="(step, index) in breedingWorkflowSteps"
                  :key="step"
                  class="workflow-step"
                >
                  <span class="workflow-index">{{ index + 1 }}</span>
                  <span>{{ step }}</span>
                </div>
              </div>
            </section>
          </div>
          <!-- 示例问题 - 跟随滚动（移动端 inline 版本） -->
          <div
            v-if="!conversations.length && exampleQuestions.length > 0"
            class="example-questions example-questions--inline"
          >
            <div class="example-chips">
              <div class="example-row">
                <div
                  v-for="question in exampleQuestions.slice(0, 3)"
                  :key="question.id"
                  class="example-chip"
                  :title="question.text"
                  @click="handleExampleClick(question.text)"
                >
                  {{ question.text }}
                </div>
              </div>

              <div class="example-row" v-if="exampleQuestions.length > 3">
                <div
                  v-for="question in exampleQuestions.slice(3, 5)"
                  :key="question.id"
                  class="example-chip"
                  :title="question.text"
                  @click="handleExampleClick(question.text)"
                >
                  {{ question.text }}
                </div>
              </div>
            </div>
          </div>
          <div class="chat-box">
            <template v-for="row in conversationRows" :key="row.key">
              <div v-if="row.type === 'conversation'" class="conv-box">
                <template
                  v-for="(displayItem, itemIndex) in row.displayItems"
                  :key="displayItem.key"
                >
                  <AgentMessageComponent
                    v-if="displayItem.type === 'message'"
                    :message="displayItem.message"
                    :is-processing="isDisplayMessageProcessing(row.conv, displayItem)"
                    :show-refs="showMsgRefs(displayItem.message)"
                    :hide-tool-calls="true"
                    @retry="retryMessage(displayItem.message)"
                  >
                  </AgentMessageComponent>
                  <ToolCallsGroupComponent
                    v-else
                    :group-key="displayItem.key"
                    :tool-calls="displayItem.toolCalls"
                    :is-active="isToolGroupActive(row.conv, itemIndex, row.displayItems)"
                  />
                </template>
                <!-- 显示对话最后一个消息使用的模型 -->
                <RefsComponent
                  v-if="shouldShowRefs(row.conv)"
                  :message="getLastMessage(row.conv)"
                  :show-refs="['model', 'copy', 'sources']"
                  :is-latest-message="false"
                  :sources="getConversationSources(row.conv)"
                  :tool-calls="getRefsConversationToolCalls(row.conv)"
                  :show-source-debug="false"
                />
              </div>
              <div v-else class="chat-inline-notice">
                <span>{{ row.notice.message }}</span>
              </div>
            </template>

            <!-- 生成中的加载状态 - 增强条件支持主聊天和resume流程 -->
            <div class="generating-status" v-if="isReplyLoading && conversations.length > 0">
              <div class="generating-indicator">
                <div class="loading-dots">
                  <div></div>
                  <div></div>
                  <div></div>
                </div>
                <span class="generating-text">正在生成回复...</span>
              </div>
            </div>
          </div>
          <div class="bottom" :class="{ 'start-screen': !conversations.length }">
            <!-- 人工审批弹窗 - 放在输入框上方 -->
            <HumanApprovalModal
              :visible="approvalState.showModal"
              :questions="approvalState.questions"
              @submit="handleQuestionSubmit"
              @cancel="handleQuestionCancel"
            />

            <div class="message-input-wrapper">
              <!-- 加载状态：加载消息 -->
              <div v-if="isLoadingMessages" class="chat-loading">
                <div class="loading-spinner"></div>
                <span>正在加载消息...</span>
              </div>

              <div v-if="showStartAgentSegment" class="agent-segment-wrapper">
                <a-segmented
                  :value="currentAgentId"
                  :options="agentSegmentOptions"
                  @change="handleStartAgentChange"
                />
              </div>

              <div v-else-if="showStartAgentDropdown" class="agent-switcher-wrapper">
                <a-dropdown :trigger="['click']" placement="bottomCenter">
                  <button type="button" class="agent-switcher-btn">
                    <component :is="currentAgentIcon" size="16" class="agent-switcher-icon" />
                    <span class="agent-switcher-text">{{ currentAgentName }}</span>
                    <ChevronDown size="16" class="agent-switcher-chevron" />
                  </button>
                  <template #overlay>
                    <a-menu class="agent-switcher-menu">
                      <a-menu-item
                        v-for="agent in startAgents"
                        :key="agent.id"
                        @click="handleStartAgentChange(agent.id)"
                      >
                        <div class="agent-switcher-menu-item">
                          <component
                            :is="getAgentIconComponent(agent.id)"
                            size="16"
                            class="agent-switcher-menu-icon"
                          />
                          <span class="agent-switcher-menu-text">{{
                            agent.name || 'Unknown'
                          }}</span>
                          <span
                            v-if="agent.id === currentAgentId"
                            class="agent-switcher-menu-badge"
                          >
                            当前
                          </span>
                        </div>
                      </a-menu-item>
                    </a-menu>
                  </template>
                </a-dropdown>
              </div>

              <AgentArtifactsCard
                :artifacts="currentArtifacts"
                :thread-id="currentChatId"
                :agent-id="currentThread?.agent_id || currentAgentId"
                :agent-config-id="selectedAgentConfigId"
                @saved="handleArtifactSaved"
              />

              <div
                class="example-questions example-questions--fixed"
                v-if="!conversations.length && exampleQuestions.length > 0"
              >
                <div class="example-chips">
                  <div class="example-row">
                    <div
                      v-for="question in exampleQuestions.slice(0, 3)"
                      :key="question.id"
                      class="example-chip"
                      :title="question.text"
                      @click="handleExampleClick(question.text)"
                    >
                      {{ question.text }}
                    </div>
                  </div>

                  <div class="example-row" v-if="exampleQuestions.length > 3">
                    <div
                      v-for="question in exampleQuestions.slice(3, 5)"
                      :key="question.id"
                      class="example-chip"
                      :title="question.text"
                      @click="handleExampleClick(question.text)"
                    >
                      {{ question.text }}
                    </div>
                  </div>
                </div>
              </div>

              <AgentInputArea
                v-model="userInput"
                :is-loading="isProcessing"
                :disabled="!currentAgent"
                :send-button-disabled="isSendButtonDisabled"
                :mention="mentionConfig"
                :supports-file-upload="supportsFileUpload"
                :is-panel-open="isAgentPanelOpen"
                :has-active-thread="!!currentChatId"
                :todos="currentTodos"
                @send="handleSendOrStop"
                @upload-attachment="handleAttachmentUpload"
                @toggle-panel="toggleAgentPanel"
              >
                <template #actions-left-extra>
                  <slot name="input-actions-left"></slot>
                </template>
              </AgentInputArea>

              <div class="bottom-actions" v-if="conversations.length > 0">
                <p class="note">当前智能体：{{ currentThreadAgentName }}；请注意辨别内容的可靠性</p>
              </div>
            </div>
          </div>
        </div>

        <!-- Agent Panel Area -->

        <div
          class="agent-panel-wrapper"
          ref="panelWrapperRef"
          :class="{
            'is-visible': isAgentPanelOpen,
            'no-transition': isResizing,
            'is-expanded': isAgentPanelExpanded
          }"
          :style="{
            flexBasis: isAgentPanelOpen ? `${panelRatio * 100}%` : '0px'
          }"
        >
          <AgentPanel
            v-if="isAgentPanelOpen"
            :agent-state="currentAgentState"
            :thread-files="currentThreadFiles"
            :thread-id="currentChatId"
            :agent-id="currentThread?.agent_id || currentAgentId"
            :agent-config-id="selectedAgentConfigId"
            :panel-ratio="panelRatio"
            :is-expanded="isAgentPanelExpanded"
            @refresh="handleAgentStateRefresh"
            @close="toggleAgentPanel"
            @toggle-expand="togglePanelExpanded"
            @resize="handlePanelResize"
            @resizing="handleResizingChange"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import {
  ref,
  reactive,
  onMounted,
  watch,
  nextTick,
  computed,
  onUnmounted,
  onActivated,
  onDeactivated,
  h
} from 'vue'
import { message } from 'ant-design-vue'
import AgentInputArea from '@/components/AgentInputArea.vue'
import AgentMessageComponent from '@/components/AgentMessageComponent.vue'
import RefsComponent from '@/components/RefsComponent.vue'
import ToolCallsGroupComponent from '@/components/ToolCallsGroupComponent.vue'
import { Bot, Telescope, ChevronDown } from 'lucide-vue-next'
import { handleChatError, handleValidationError } from '@/utils/errorHandler'
import { ScrollController } from '@/utils/scrollController'
import { AgentValidator } from '@/utils/agentValidator'
import { useAgentStore } from '@/stores/agent'
import { useChatThreadsStore } from '@/stores/chatThreads'
import { useChatUIStore } from '@/stores/chatUI'
import { useUserStore } from '@/stores/user'
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'
import { MessageProcessor } from '@/utils/messageProcessor'
import { agentApi, threadApi } from '@/apis'
import { getWorkspaceTree } from '@/apis/workspace_api'
import HumanApprovalModal from '@/components/HumanApprovalModal.vue'
import { useApproval } from '@/composables/useApproval'
import { useAgentThreadState } from '@/composables/useAgentThreadState'
import { useAgentRunStream } from '@/composables/useAgentRunStream'
import { useAgentStreamHandler } from '@/composables/useAgentStreamHandler'
import { useStreamSmoother } from '@/composables/useStreamSmoother'
import { useAgentMentionConfig } from '@/composables/useAgentMentionConfig'
import { shouldAutoOpenAgentPanel } from '@/utils/agentPanelAutoOpen'
import AgentArtifactsCard from '@/components/AgentArtifactsCard.vue'
import AgentPanel from '@/components/AgentPanel.vue'
import UserInfoComponent from '@/components/UserInfoComponent.vue'
import {
  getMessageToolCalls as getRefsMessageToolCalls,
  getConversationToolCalls as getRefsConversationToolCalls
} from '@/utils/toolCalls'

// ==================== PROPS & EMITS ====================
const props = defineProps({
  agentId: { type: String, default: '' },
  singleMode: { type: Boolean, default: true }
})
const emit = defineEmits(['thread-change'])

// ==================== STORE MANAGEMENT ====================
const agentStore = useAgentStore()
const chatThreadsStore = useChatThreadsStore()
const chatUIStore = useChatUIStore()
const userStore = useUserStore()
const configStore = useConfigStore()
const {
  agents,
  selectedAgentId,
  defaultAgentId,
  selectedAgentConfigId,
  agentConfig,
  configurableItems,
  availableKnowledgeBases,
  availableMcps,
  availableSkills
} = storeToRefs(agentStore)
const { threads, currentThreadId, currentThread } = storeToRefs(chatThreadsStore)

// ==================== LOCAL CHAT & UI STATE ====================
const userInput = ref('')
const sendCooldownActive = ref(false)
let sendCooldownTimer = null
const useRunsApi =
  import.meta.env.VITE_USE_RUNS_API === 'true' &&
  localStorage.getItem('force_legacy_stream') !== 'true'

// 网站 logo 路径：默认读取 public/logo.svg，可按项目实际路径替换
const siteLogo = '/logo.svg'

// 预设的打招呼文本
const greetingMessages = [
  '我是杂粮育种大模型，请描述您的育种问题'
]

// 随机选择一个打招呼文本
const randomGreeting = greetingMessages[Math.floor(Math.random() * greetingMessages.length)]

const breedingTasks = [
  {
    icon: '🌾',
    title: '候选基因与位点优先级分析',
    desc: '整合文献证据与知识图谱，筛选候选基因、QTL、分子标记和关键机制'
  },
  {
    icon: '🧬',
    title: '性状机制与证据整合',
    desc: '梳理基因-性状-环境-表型关系，形成可追溯的机制解释'
  },
  {
    icon: '📊',
    title: '验证路径与实验设计',
    desc: '设计 qRT-PCR、RNA-seq、GWAS、KASP、CRISPR 和田间验证路线'
  },
  {
    icon: '🌱',
    title: '育种报告生成与决策建议',
    desc: '生成结构化育种报告，输出关键结论、证据来源、风险判断和应用建议'
  }
]

const breedingCropTags = ['谷子', '高粱', '荞麦', '燕麦', '藜麦', '糜黍']

const breedingCapabilityTags = [
  '候选基因',
  '证据检索',
  '知识图谱',
  '可追溯推理',
  '验证路径',
]

const breedingWorkflowSteps = [
  '问题定义',
  '证据检索',
  '知识整合',
  '推理生成',
  '验证建议'
]

// 从智能体元数据获取示例问题
const exampleQuestions = computed(() => {
  const agentId = currentAgentId.value
  let examples = []
  if (agentId && agents.value && agents.value.length > 0) {
    const agent = agents.value.find((a) => a.id === agentId)
    examples = agent ? agent.metadata?.examples || [] : []
  }
  return examples.map((text, index) => ({
    id: index + 1,
    text: text
  }))
})

// 业务状态（保留在组件本地）
const chatState = reactive({
  currentThreadId: null,
  // 以threadId为键的线程状态
  threadStates: {}
})
const setCurrentThreadId = (threadId) => {
  chatState.currentThreadId = threadId || null
  chatThreadsStore.setCurrentThreadId(threadId || null)
}
const streamSmoother = useStreamSmoother({
  getThreadState: (threadId) => chatState.threadStates[threadId] || null
})
const { getThreadState, resetOnGoingConv, stopThreadStream } = useAgentThreadState({
  chatState,
  getCurrentThreadId: () => chatState.currentThreadId,
  onStopThread: (threadId) => streamSmoother.flushThread(threadId),
  onBeforeResetThread: (threadId) => streamSmoother.resetThread(threadId),
  onBeforeCleanupThread: (threadId) => streamSmoother.resetThread(threadId)
})

// 组件级别的消息、附件与提示状态
const threadMessages = ref({})
const threadFilesMap = ref({})
const threadAttachmentsMap = ref({})
const workspaceMentionFiles = ref([])
const threadConfigNoticeMap = ref({})
const threadPendingConfigNoticeMap = ref({})
const threadConfigSnapshotMap = ref({})
const configNoticeSyncDepth = ref(0)
const configNoticeScrollVersion = ref(0)

// 本地 UI 状态（仅在本组件使用）
const localUIState = reactive({
  chatMainWidth: typeof window !== 'undefined' ? window.innerWidth : 0
})

// Agent Panel State
const isAgentPanelOpen = ref(false)
const isAgentPanelExpanded = ref(false)
const isResizing = ref(false)
const panelRatio = ref(0.3) // 面板宽度比例 (0-1)
const panelWrapperRef = ref(null) // 直接操作 DOM

const getPanelRatioBounds = () => {
  const width = panelContainerWidth || (typeof window !== 'undefined' ? window.innerWidth : 1440)

  // 小屏下右侧面板使用 CSS 浮层，不再参与主聊天区 flex 宽度计算。
  if (width <= 900) {
    return { min: 1, max: 1 }
  }

  // 笔记本屏幕下限制面板最大宽度，避免把聊天区挤得过窄。
  if (width <= 1280) {
    return { min: 0.28, max: 0.48 }
  }

  return { min: 0.2, max: 0.62 }
}

let resizeStartX = 0
let resizeStartWidth = 0
let panelContainerWidth = 0

// ==================== COMPUTED PROPERTIES ====================
const currentAgentId = computed(() => {
  if (props.singleMode) {
    return props.agentId || defaultAgentId.value
  } else {
    return selectedAgentId.value
  }
})

const currentAgentName = computed(() => {
  const agent = currentAgent.value
  return agent ? agent.name : '智能体'
})

const currentAgent = computed(() => {
  if (!currentAgentId.value || !agents.value || !agents.value.length) return null
  return agents.value.find((a) => a.id === currentAgentId.value) || null
})
const startAgents = computed(() => agents.value || [])
const currentChatId = computed(() => currentThreadId.value)

const currentThreadAgentName = computed(() => {
  const threadAgentId = currentThread.value?.agent_id
  if (threadAgentId && agents.value?.length) {
    const threadAgent = agents.value.find((agent) => agent.id === threadAgentId)
    if (threadAgent?.name) {
      return threadAgent.name
    }
  }
  return currentAgentName.value
})
const currentAgentIcon = computed(() => getAgentIconComponent(currentAgentId.value))

// 检查当前智能体是否支持文件上传
const supportsFileUpload = computed(() => {
  if (!currentAgent.value) return false
  const capabilities = currentAgent.value.capabilities || []
  return capabilities.includes('file_upload')
})

const supportsFiles = computed(() => {
  if (!currentAgent.value) return false
  const capabilities = currentAgent.value.capabilities || []
  return capabilities.includes('files')
})

// AgentState 相关计算属性
const currentAgentState = computed(() => {
  return currentChatId.value ? getThreadState(currentChatId.value)?.agentState || null : null
})
const currentThreadFiles = computed(() => {
  if (!currentChatId.value) return []
  return threadFilesMap.value[currentChatId.value] || []
})
const currentThreadAttachments = computed(() => {
  if (!currentChatId.value) return []
  return threadAttachmentsMap.value[currentChatId.value] || []
})
const currentArtifacts = computed(() => {
  const artifacts = currentAgentState.value?.artifacts
  return Array.isArray(artifacts) ? artifacts : []
})
const currentTodos = computed(() => {
  const todos = currentAgentState.value?.todos
  return Array.isArray(todos) ? todos : []
})

const hasAgentStateContent = computed(() => {
  return shouldAutoOpenAgentPanel(currentThreadFiles.value)
})

// 监听 hasAgentStateContent 从 false → true 时，自动展开面板
watch(hasAgentStateContent, (newVal, oldVal) => {
  if (newVal && !oldVal) {
    // 从无状态变为有状态时，自动展开面板
    isAgentPanelOpen.value = true
  }
})
const { mentionConfig } = useAgentMentionConfig({
  currentAgentState,
  currentThreadFiles,
  currentThreadAttachments,
  workspaceMentionFiles,
  configurableItems,
  agentConfig,
  availableKnowledgeBases,
  availableMcps,
  availableSkills
})

const currentThreadMessages = computed(() => threadMessages.value[currentChatId.value] || [])
const currentThreadHasHistory = computed(() => currentThreadMessages.value.length > 0)
const currentThreadConfigNotice = computed(() => {
  if (!currentChatId.value) return null
  return threadConfigNoticeMap.value[currentChatId.value] || null
})

// 计算是否显示Refs组件的条件
const shouldShowRefs = computed(() => {
  return (conv) => {
    return (
      getLastMessage(conv) &&
      conv.status !== 'streaming' &&
      !approvalState.showModal &&
      !(
        approvalState.threadId &&
        chatState.currentThreadId === approvalState.threadId &&
        isProcessing.value
      )
    )
  }
})

// 当前线程状态的computed属性
const currentThreadState = computed(() => {
  return getThreadState(currentChatId.value)
})

const onGoingConvMessages = computed(() => {
  const threadState = currentThreadState.value

  if (!threadState || !threadState.onGoingConv) return []

  const msgs = Object.values(threadState.onGoingConv.msgChunks).map(
    MessageProcessor.mergeMessageChunk
  )

  return msgs.length > 0
    ? MessageProcessor.convertToolResultToMessages(msgs).filter((msg) => msg.type !== 'tool')
    : []
})

const historyConversations = computed(() => {
  return MessageProcessor.convertServerHistoryToMessages(currentThreadMessages.value)
})

const conversations = computed(() => {
  const historyConvs = historyConversations.value
  const mergedOngoingMessages = stripDuplicatedOngoingHumanMessage(
    historyConvs,
    onGoingConvMessages.value
  )

  // 如果有进行中的消息且线程状态显示正在流式处理，添加进行中的对话
  if (mergedOngoingMessages.length > 0) {
    const onGoingConv = {
      messages: mergedOngoingMessages,
      status: 'streaming'
    }
    return [...historyConvs, onGoingConv]
  }
  return historyConvs
})

const conversationRows = computed(() => {
  const rows = conversations.value.map((conv, index) => ({
    type: 'conversation',
    key: conv.status === 'streaming' ? 'ongoing-conversation' : `history-${index}`,
    conv,
    displayItems: getConversationDisplayItems(conv)
  }))

  if (currentThreadConfigNotice.value) {
    const insertAfterCount = Math.max(
      0,
      Math.min(
        Number(currentThreadConfigNotice.value.insertAfterConversationCount) || 0,
        rows.length
      )
    )
    rows.splice(insertAfterCount, 0, {
      type: 'notice',
      key: currentThreadConfigNotice.value.id,
      notice: currentThreadConfigNotice.value
    })
  }

  return rows
})

// 智能体图标映射
const agentIconMap = {
  ChatbotAgent: Bot,
  DeepAgent: Telescope
}

const getAgentIconComponent = (agentId) => {
  return agentIconMap[agentId] || Bot
}

const agentSegmentOptions = computed(() => {
  return startAgents.value.map((agent) => {
    const IconComponent = getAgentIconComponent(agent.id)
    return {
      label: () =>
        h('div', { class: 'agent-option-label' }, [
          h(IconComponent, { size: 16, class: 'agent-option-icon' }),
          h('span', null, agent.name || 'Unknown')
        ]),
      value: agent.id
    }
  })
})

const showStartAgentSelector = computed(() => {
  return !props.singleMode && !conversations.value.length && startAgents.value.length > 1
})

const showStartAgentDropdown = computed(() => {
  return (
    showStartAgentSelector.value &&
    (startAgents.value.length >= 4 || localUIState.chatMainWidth < 560)
  )
})

const showStartAgentSegment = computed(() => {
  return showStartAgentSelector.value && !showStartAgentDropdown.value
})

const handleStartAgentChange = async (agentId) => {
  if (!agentId || agentId === currentAgentId.value) return
  if (conversations.value.length > 0) return
  try {
    await agentStore.selectAgent(agentId)
  } catch (error) {
    handleChatError(error, 'load')
  }
}

const isLoadingMessages = computed(() => chatUIStore.isLoadingMessages)
const isStreaming = computed(() => {
  const threadState = currentThreadState.value
  return threadState ? threadState.isStreaming : false
})
const isProcessing = computed(() => isStreaming.value)
const isReplyLoading = computed(() => {
  const threadState = currentThreadState.value
  return Boolean(threadState?.replyLoadingVisible)
})
const isSendButtonDisabled = computed(() => {
  return (
    sendCooldownActive.value || ((!userInput.value || !currentAgent.value) && !isProcessing.value)
  )
})

const startSendCooldown = () => {
  sendCooldownActive.value = true
  if (sendCooldownTimer) {
    clearTimeout(sendCooldownTimer)
  }
  sendCooldownTimer = setTimeout(() => {
    sendCooldownActive.value = false
    sendCooldownTimer = null
  }, 2000)
}

const createClientRequestId = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `req-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

const buildOptimisticHumanMessage = ({ requestId, text, imageContent = null }) => {
  const message = {
    id: requestId,
    role: 'user',
    type: 'human',
    content: text,
    message_type: imageContent ? 'multimodal_image' : 'text',
    extra_metadata: {
      request_id: requestId
    }
  }

  if (imageContent) {
    message.image_content = imageContent
  }

  return message
}

const getMessageRequestId = (message) => {
  if (!message || typeof message !== 'object') return null

  const metadataRequestId = message.extra_metadata?.request_id
  if (typeof metadataRequestId === 'string' && metadataRequestId.trim()) {
    return metadataRequestId.trim()
  }

  if (message.type === 'human' && typeof message.id === 'string' && message.id.trim()) {
    return message.id.trim()
  }

  return null
}

// 历史消息已落库时，ongoing 里仍会保留当前轮的本地 user message；
// 切回线程后按 request_id 去掉这条重复消息，只保留仍在流式更新的部分。
const stripDuplicatedOngoingHumanMessage = (historyConvs, ongoingMessages) => {
  if (!Array.isArray(historyConvs) || !historyConvs.length || !Array.isArray(ongoingMessages)) {
    return ongoingMessages
  }

  const firstOngoingMessage = ongoingMessages[0]
  if (!firstOngoingMessage || firstOngoingMessage.type !== 'human') {
    return ongoingMessages
  }

  const lastHistoryConv = historyConvs[historyConvs.length - 1]
  const historyMessages = Array.isArray(lastHistoryConv?.messages) ? lastHistoryConv.messages : []
  const lastHistoryHuman = historyMessages.find((message) => message?.type === 'human')
  if (!lastHistoryHuman) {
    return ongoingMessages
  }

  const historyRequestId = getMessageRequestId(lastHistoryHuman)
  const ongoingRequestId = getMessageRequestId(firstOngoingMessage)
  if (!historyRequestId || !ongoingRequestId || historyRequestId !== ongoingRequestId) {
    return ongoingMessages
  }

  return ongoingMessages.slice(1)
}

// 发送 runs 前先在前端插入一条用户消息，避免等待 worker 轮询后消息才出现。
const ensureThreadMsgChunks = (threadState) => {
  if (!threadState.onGoingConv) {
    threadState.onGoingConv = { msgChunks: {} }
  }

  if (!threadState.onGoingConv.msgChunks) {
    threadState.onGoingConv.msgChunks = {}
  }

  return threadState.onGoingConv.msgChunks
}

const insertOptimisticHumanMessage = (threadState, { requestId, text, imageContent = null }) => {
  if (!threadState || !requestId) return

  threadState.pendingRequestId = requestId
  threadState.replyLoadingVisible = false

  const msgChunks = ensureThreadMsgChunks(threadState)
  msgChunks[requestId] = [
    buildOptimisticHumanMessage({ requestId, text, imageContent })
  ]
}

const CONFIG_CHANGE_NOTICE_MESSAGE =
  '在运行过程中切换或修改配置可能会影响最终效果，建议新建一个对话。'

const withConfigNoticeSync = async (task) => {
  configNoticeSyncDepth.value += 1
  try {
    return await task()
  } finally {
    configNoticeSyncDepth.value = Math.max(0, configNoticeSyncDepth.value - 1)
  }
}

const buildThreadConfigSnapshot = () => {
  return {
    agentId: currentAgentId.value || '',
    agentConfigId: selectedAgentConfigId.value ?? null,
    configJson: JSON.stringify(agentConfig.value || {})
  }
}

const syncThreadConfigSnapshot = (threadId, options = {}) => {
  if (!threadId) return

  const { overwrite = true } = options
  if (!overwrite && threadConfigSnapshotMap.value[threadId]) return
  if (threadPendingConfigNoticeMap.value[threadId]) return

  // 线程切换时先记录当前 UI 的配置快照，避免同步 thread 绑定配置时误报。
  threadConfigSnapshotMap.value = {
    ...threadConfigSnapshotMap.value,
    [threadId]: buildThreadConfigSnapshot()
  }
}

const upsertThreadConfigNotice = (threadId, insertAfterConversationCount) => {
  if (!threadId) return

  const existingNotice = threadConfigNoticeMap.value[threadId]
  const nextNotice = {
    id: existingNotice?.id || `config-change-notice-${threadId}`,
    message: existingNotice?.message || CONFIG_CHANGE_NOTICE_MESSAGE,
    insertAfterConversationCount
  }
  const shouldScroll =
    !existingNotice || existingNotice.insertAfterConversationCount !== insertAfterConversationCount

  threadConfigNoticeMap.value = {
    ...threadConfigNoticeMap.value,
    [threadId]: nextNotice
  }

  if (threadPendingConfigNoticeMap.value[threadId]) {
    const nextPendingNotices = { ...threadPendingConfigNoticeMap.value }
    delete nextPendingNotices[threadId]
    threadPendingConfigNoticeMap.value = nextPendingNotices
  }

  if (shouldScroll) {
    configNoticeScrollVersion.value += 1
  }
}

const queuePendingThreadConfigNotice = (threadId) => {
  if (!threadId) return
  threadPendingConfigNoticeMap.value = {
    ...threadPendingConfigNoticeMap.value,
    [threadId]: {
      id: `config-change-notice-${threadId}`,
      message: CONFIG_CHANGE_NOTICE_MESSAGE
    }
  }
}

const flushPendingThreadConfigNotice = (threadId) => {
  if (
    !threadId ||
    !currentThreadHasHistory.value ||
    !threadPendingConfigNoticeMap.value[threadId]
  ) {
    return
  }

  upsertThreadConfigNotice(threadId, conversations.value.length)
}

const maybeInsertThreadConfigNotice = () => {
  const threadId = currentChatId.value
  if (!threadId || configNoticeSyncDepth.value > 0) {
    return
  }

  const previousSnapshot = threadConfigSnapshotMap.value[threadId]
  const currentSnapshot = buildThreadConfigSnapshot()

  if (!previousSnapshot) {
    threadConfigSnapshotMap.value = {
      ...threadConfigSnapshotMap.value,
      [threadId]: currentSnapshot
    }
    return
  }

  if (
    previousSnapshot.agentId === currentSnapshot.agentId &&
    previousSnapshot.agentConfigId === currentSnapshot.agentConfigId &&
    previousSnapshot.configJson === currentSnapshot.configJson
  ) {
    return
  }

  if (currentThreadHasHistory.value) {
    upsertThreadConfigNotice(threadId, conversations.value.length)
  } else if (chatUIStore.isLoadingMessages) {
    // 历史线程仍在加载时先挂起提示，避免消息返回后把变更误当成新的基线。
    queuePendingThreadConfigNotice(threadId)
  } else {
    return
  }

  threadConfigSnapshotMap.value = {
    ...threadConfigSnapshotMap.value,
    [threadId]: currentSnapshot
  }
}

// ==================== SCROLL & RESIZE HANDLING ====================
const scrollController = new ScrollController('.chat-main')
const chatMainRef = ref(null)
let chatMainResizeObserver = null
// 初始化延迟标志，避免首次挂载时 ResizeObserver 立即触发导致侧边栏意外关闭
let isResizeObserverReady = false
let resizeObserverReadyTimer = null

const armResizeObserver = () => {
  if (resizeObserverReadyTimer) {
    clearTimeout(resizeObserverReadyTimer)
  }

  isResizeObserverReady = false
  // keep-alive 切页回来时等布局稳定后再恢复宽度判断，避免隐藏态宽度污染侧边栏状态。
  resizeObserverReadyTimer = setTimeout(() => {
    isResizeObserverReady = true
  }, 50)
}

const stopChatMainResizeObserver = () => {
  if (resizeObserverReadyTimer) {
    clearTimeout(resizeObserverReadyTimer)
    resizeObserverReadyTimer = null
  }

  isResizeObserverReady = false

  if (chatMainResizeObserver) {
    chatMainResizeObserver.disconnect()
    chatMainResizeObserver = null
  }
}

const startChatMainResizeObserver = () => {
  if (!window.ResizeObserver || !chatMainRef.value || chatMainResizeObserver) {
    return
  }

  localUIState.chatMainWidth = chatMainRef.value.clientWidth || window.innerWidth
  chatMainResizeObserver = new ResizeObserver((entries) => {
    // 初始化期间跳过检查，等待 layout 稳定
    if (!isResizeObserverReady) return

    for (const entry of entries) {
      const width = entry.contentRect.width
      if (!width) continue

      localUIState.chatMainWidth = width
    }
  })
  chatMainResizeObserver.observe(chatMainRef.value)
  armResizeObserver()
}

onMounted(() => {
  nextTick(() => {
    const chatMainContainer = document.querySelector('.chat-main')
    if (chatMainContainer) {
      chatMainContainer.addEventListener('scroll', scrollController.handleScroll, { passive: true })
    }

    startChatMainResizeObserver()
  })
})

let skipNextWorkspaceMentionActivation = true
onActivated(() => {
  if (skipNextWorkspaceMentionActivation) {
    skipNextWorkspaceMentionActivation = false
  } else {
    void fetchWorkspaceMentionFiles()
  }
  nextTick(() => {
    startChatMainResizeObserver()
  })
})

onDeactivated(() => {
  stopChatMainResizeObserver()
})

onUnmounted(() => {
  scrollController.cleanup()
  stopChatMainResizeObserver()
  if (sendCooldownTimer) {
    clearTimeout(sendCooldownTimer)
    sendCooldownTimer = null
  }
  // 清理所有线程状态
  resetOnGoingConv()
})

// ==================== 线程管理方法 ====================
const setThreadAgentConfigId = (threadId, agentConfigId) => {
  if (!threadId) return
  const thread = threads.value.find((item) => item.id === threadId)
  if (thread) {
    thread.metadata = {
      ...(thread.metadata || {}),
      agent_config_id: agentConfigId ?? null
    }
  }
}

const syncSelectedConfigForThread = async (thread) => {
  const threadAgentConfigId = thread?.metadata?.agent_config_id
  if (!threadAgentConfigId) return

  const targetAgentId = thread.agent_id || currentAgentId.value
  if (!targetAgentId) return

  const configList = agentStore.agentConfigs[targetAgentId] || []
  if (!configList.length) {
    await agentStore.fetchAgentConfigs(targetAgentId)
  }

  if (selectedAgentConfigId.value !== threadAgentConfigId) {
    await agentStore.selectAgentConfig(threadAgentConfigId)
  }
}

// 获取当前智能体的线程列表
const fetchThreads = async (agentId = null) => {
  const targetAgentId = props.singleMode ? agentId || currentAgentId.value : agentId
  if (props.singleMode && !targetAgentId) return

  await chatThreadsStore.loadThreads(targetAgentId)
}

// 创建新线程
const createThread = async (agentId, title = '新的对话') => {
  if (!agentId) return null

  try {
    const thread = await chatThreadsStore.createThread(agentId, title)
    if (thread) {
      threadMessages.value[thread.id] = []
      threadFilesMap.value[thread.id] = []
      threadAttachmentsMap.value[thread.id] = []
    }
    return thread
  } catch (error) {
    console.error('Failed to create thread:', error)
    handleChatError(error, 'create')
    throw error
  }
}

// 获取线程消息
const fetchThreadMessages = async ({ agentId, threadId, delay = 0 }) => {
  if (!threadId || !agentId) return

  // 如果指定了延迟，等待指定时间（用于确保后端数据库事务提交）
  if (delay > 0) {
    await new Promise((resolve) => setTimeout(resolve, delay))
  }

  try {
    const response = await agentApi.getAgentHistory(threadId)
    threadMessages.value[threadId] = response.history || []
  } catch (error) {
    handleChatError(error, 'load')
    throw error
  }
}

const fetchThreadFiles = async (threadId) => {
  if (!threadId) return
  try {
    const response = await threadApi.listThreadFiles(threadId, '/home/gem/user-data', true)
    const entries = Array.isArray(response?.files) ? response.files : []
    threadFilesMap.value[threadId] = entries
  } catch (error) {
    console.warn('Failed to fetch thread files:', error)
    threadFilesMap.value[threadId] = []
  }
}

const fetchThreadAttachments = async (threadId) => {
  if (!threadId) return
  try {
    const response = await threadApi.getThreadAttachments(threadId)
    threadAttachmentsMap.value[threadId] = Array.isArray(response?.attachments)
      ? response.attachments
      : []
  } catch (error) {
    console.warn('Failed to fetch thread attachments:', error)
    threadAttachmentsMap.value[threadId] = []
  }
}

const refreshThreadFilesAndAttachments = async (threadId) => {
  if (!threadId) return
  await Promise.all([fetchThreadFiles(threadId), fetchThreadAttachments(threadId)])
}

let workspaceMentionFilesRequest = null
const fetchWorkspaceMentionFiles = async () => {
  if (workspaceMentionFilesRequest) return workspaceMentionFilesRequest
  workspaceMentionFilesRequest = (async () => {
    try {
      const response = await getWorkspaceTree('/', true, true)
      workspaceMentionFiles.value = Array.isArray(response?.entries) ? response.entries : []
    } catch (error) {
      console.warn('Failed to fetch workspace mention files:', error)
      workspaceMentionFiles.value = []
    } finally {
      workspaceMentionFilesRequest = null
    }
  })()
  return workspaceMentionFilesRequest
}

const handleArtifactSaved = async () => {
  await fetchWorkspaceMentionFiles()
  if (!currentChatId.value) return
  await refreshThreadFilesAndAttachments(currentChatId.value)
}

const fetchAgentState = async (agentId, threadId) => {
  if (!threadId) return
  try {
    const res = await agentApi.getAgentState(threadId)
    const targetChatId = currentChatId.value || threadId
    const ts = getThreadState(targetChatId)
    if (ts) {
      ts.agentState = res.agent_state || null
    } else {
      const newTs = getThreadState(threadId)
      if (newTs) newTs.agentState = res.agent_state || null
    }
  } catch {
    // 忽略状态拉取失败，不阻塞主流程
  }
}

const ensureActiveThread = async (title = '新的对话') => {
  if (currentChatId.value) return currentChatId.value
  try {
    const newThread = await createThread(currentAgentId.value, title || '新的对话')
    if (newThread) {
      setCurrentThreadId(newThread.id)
      return newThread.id
    }
  } catch {
    // createThread 已处理错误提示
  }
  return null
}

const handleAttachmentUpload = async (files) => {
  if (!files?.length) return
  if (
    !AgentValidator.validateAgentIdWithError(
      currentAgentId.value,
      '上传附件',
      handleValidationError
    )
  )
    return

  const preferredTitle = files[0]?.name || '新的对话'
  let threadId = currentChatId.value

  if (!threadId) {
    threadId = await ensureActiveThread(preferredTitle)
  }

  if (!threadId) {
    message.error('创建对话失败，无法上传附件')
    return
  }

  try {
    message.loading({
      content: '正在上传附件...',
      key: 'upload-attachment',
      duration: 0
    })
    for (const file of files) {
      await threadApi.uploadThreadAttachment(threadId, file)
    }
    message.success({ content: '附件上传成功', key: 'upload-attachment', duration: 2 })
    await Promise.all([
      fetchAgentState(currentAgentId.value, threadId),
      refreshThreadFilesAndAttachments(threadId)
    ])
  } catch (error) {
    message.destroy('upload-attachment')
    handleChatError(error, 'upload')
  }
}

// ==================== 审批功能管理 ====================
const { approvalState, handleApproval, processApprovalInStream } = useApproval({
  getThreadState,
  resetOnGoingConv,
  fetchThreadMessages
})

const { handleAgentResponse, handleStreamChunk } = useAgentStreamHandler({
  getThreadState,
  processApprovalInStream,
  currentAgentId,
  supportsFiles,
  streamSmoother
})
const { startRunStream, resumeActiveRunForThread, stopRunStreamSubscription } = useAgentRunStream({
  getThreadState,
  useRunsApi,
  currentAgentId,
  handleStreamChunk,
  processApprovalInStream,
  fetchThreadMessages,
  fetchAgentState,
  resetOnGoingConv,
  onScrollToBottom: () => scrollController.scrollToBottom(),
  streamSmoother
})

// 发送消息并处理流式响应
const sendMessage = async ({
  agentId,
  threadId,
  text,
  signal = undefined,
  imageData = undefined
}) => {
  if (!agentId || !threadId || !text) {
    const error = new Error('Missing agent, thread, or message text')
    handleChatError(error, 'send')
    return Promise.reject(error)
  }

  if (!selectedAgentConfigId.value) {
    const error = new Error('Missing agent_config_id')
    handleChatError(error, 'send')
    return Promise.reject(error)
  }

  setThreadAgentConfigId(threadId, selectedAgentConfigId.value)

  const requestData = {
    query: text,
    thread_id: threadId,
    agent_config_id: selectedAgentConfigId.value
  }

  // 如果有图片，添加到请求中
  if (imageData && imageData.imageContent) {
    requestData.image_content = imageData.imageContent
  }

  try {
    return await agentApi.sendAgentMessage(requestData, signal ? { signal } : undefined)
  } catch (error) {
    handleChatError(error, 'send')
    throw error
  }
}

// ==================== CHAT ACTIONS ====================
// 获取第一个非置顶的对话
const getFirstNonPinnedChat = (chatList) => {
  if (!chatList || chatList.length === 0) return null
  return chatList.find((chat) => !chat.is_pinned) || chatList[0]
}

const selectChat = async (chatId) => {
  const targetChat = threads.value.find((chat) => chat.id === chatId) || null
  const targetAgentId = targetChat?.agent_id || currentAgentId.value
  const previousThreadId = chatState.currentThreadId

  if (!targetAgentId) {
    handleValidationError('选择对话失败：缺少智能体信息')
    return
  }

  if (!AgentValidator.validateAgentIdWithError(targetAgentId, '选择对话', handleValidationError))
    return

  // 中断之前线程的流式输出（如果存在）
  if (previousThreadId && previousThreadId !== chatId) {
    stopThreadStream(previousThreadId)
    // run 模式下仅断开 SSE 订阅，不取消后台运行任务
    stopRunStreamSubscription(previousThreadId)
  }

  if (previousThreadId !== chatId) {
    isAgentPanelOpen.value = false
  }

  try {
    await withConfigNoticeSync(async () => {
      // 先更新当前线程，确保底部智能体名称与选中项即时同步。
      setCurrentThreadId(chatId)

      if (
        !props.singleMode &&
        targetChat?.agent_id &&
        targetChat.agent_id !== currentAgentId.value
      ) {
        await agentStore.selectAgent(targetChat.agent_id)
      }

      await syncSelectedConfigForThread(targetChat)
      syncThreadConfigSnapshot(chatId)
    })
  } catch (error) {
    setCurrentThreadId(previousThreadId)
    handleChatError(error, 'load')
    return
  }

  chatUIStore.isLoadingMessages = true
  try {
    await fetchThreadMessages({ agentId: targetAgentId, threadId: chatId })
  } catch (error) {
    handleChatError(error, 'load')
  } finally {
    chatUIStore.isLoadingMessages = false
  }

  await nextTick()
  scrollController.scrollToBottomStaticForce()
  // await fetchAgentState(targetAgentId, chatId)
  await handleAgentStateRefresh(chatId)
  syncThreadConfigSnapshot(chatId, { overwrite: false })
  await resumeActiveRunForThread(chatId)
}

const selectThreadFromRoute = async (threadId) => {
  if (!agentStore.isInitialized) {
    await initAll()
  }

  if (!threadId) {
    const previousThreadId = chatState.currentThreadId
    if (previousThreadId) {
      stopThreadStream(previousThreadId)
      stopRunStreamSubscription(previousThreadId)
    }
    isAgentPanelOpen.value = false
    setCurrentThreadId(null)
    return true
  }

  if (chatState.currentThreadId === threadId) {
    return true
  }

  if (!threads.value.length || !threads.value.find((thread) => thread.id === threadId)) {
    await loadChatsList()
  }

  const targetThread = threads.value.find((thread) => thread.id === threadId)
  if (!targetThread) {
    return false
  }

  await selectChat(threadId)
  return true
}

const handleSendMessage = async ({ image } = {}) => {
  const text = userInput.value.trim()
  const imageContent = image?.imageContent || null
  if ((!text && !image) || !currentAgent.value || isProcessing.value || sendCooldownActive.value)
    return

  if (!selectedAgentConfigId.value) {
    message.error('请先选择智能体配置后再发送消息')
    return
  }

  // 发送后进入短暂冷却，防止连续触发停止
  startSendCooldown()

  let threadId = currentChatId.value
  if (!threadId) {
    threadId = await ensureActiveThread(text)
    if (!threadId) {
      message.error('创建对话失败，请重试')
      return
    }
  }

  userInput.value = ''

  await nextTick()
  scrollController.scrollToBottom(true)

  const threadState = getThreadState(threadId)
  if (!threadState) return

  if (useRunsApi) {
    if ((threadMessages.value[threadId] || []).length === 0) {
      const autoTitle = text.replace(/\s+/g, ' ').trim().slice(0, 2000)
      if (autoTitle) {
        void (async () => {
          try {
            const generatedTitle = await agentApi.generateTitle(
              autoTitle,
              configStore.config?.fast_model
            )
            if (generatedTitle) {
              const finalTitle = generatedTitle.slice(0, 30).replace(/\s+/g, ' ').trim()
              if (finalTitle) {
                void chatThreadsStore.updateThread(threadId, finalTitle).catch(() => {})
              }
            }
          } catch (e) {
            console.error('Title generation failed:', e)
            // 失败时使用原始文本作为标题
            void chatThreadsStore.updateThread(threadId, autoTitle.slice(0, 30)).catch(() => {})
          }
        })()
      }
    }

    resetOnGoingConv(threadId)
    const requestId = createClientRequestId()
    insertOptimisticHumanMessage(threadState, {
      requestId,
      text,
      imageContent
    })
    threadState.isStreaming = true
    try {
      const runResp = await agentApi.createAgentRun({
        query: text,
        agent_config_id: selectedAgentConfigId.value,
        thread_id: threadId,
        meta: {
          request_id: requestId
        },
        image_content: imageContent
      })
      const runId = runResp?.run_id
      if (!runId) {
        throw new Error('创建 run 失败：缺少 run_id')
      }
      await startRunStream(threadId, runId, 0)
    } catch (error) {
      threadState.isStreaming = false
      threadState.replyLoadingVisible = false
      threadState.pendingRequestId = null
      resetOnGoingConv(threadId)
      handleChatError(error, 'send')
    }
    return
  }

  // 如果是新对话，用 fast-model 异步生成标题（不阻塞消息发送）
  if ((threadMessages.value[threadId] || []).length === 0) {
    const autoTitle = text.replace(/\s+/g, ' ').trim().slice(0, 2000)
    if (autoTitle) {
      void (async () => {
        try {
          const generatedTitle = await agentApi.generateTitle(
            autoTitle,
            configStore.config?.fast_model
          )
          if (generatedTitle) {
            const finalTitle = generatedTitle.slice(0, 30).replace(/\s+/g, ' ').trim()
            if (finalTitle) {
              void chatThreadsStore.updateThread(threadId, finalTitle).catch(() => {})
            }
          }
        } catch (e) {
          console.error('Title generation failed:', e)
          // 失败时使用原始文本作为标题
          void chatThreadsStore.updateThread(threadId, autoTitle.slice(0, 30)).catch(() => {})
        }
      })()
    }
  }

  threadState.isStreaming = true
  resetOnGoingConv(threadId)
  threadState.streamAbortController = new AbortController()

  try {
    const response = await sendMessage({
      agentId: currentAgentId.value,
      threadId: threadId,
      text: text,
      signal: threadState.streamAbortController?.signal,
      imageData: image
    })

    await handleAgentResponse(response, threadId)
  } catch (error) {
    if (error.name !== 'AbortError') {
      console.error('Stream error:', error)
      handleChatError(error, 'send')
    } else {
      console.warn('[Interrupted] Catch')
    }
    threadState.isStreaming = false
  } finally {
    threadState.streamAbortController = null
    // 异步加载历史记录，保持当前消息显示直到历史记录加载完成
    fetchThreadMessages({ agentId: currentAgentId.value, threadId: threadId }).finally(() => {
      // 历史记录加载完成后，安全地清空当前进行中的对话
      resetOnGoingConv(threadId)
      handleAgentStateRefresh(threadId)
      scrollController.scrollToBottom()
    })
  }
}

// 发送或中断
const handleSendOrStop = async (payload) => {
  if (sendCooldownActive.value) {
    return
  }

  const threadId = currentChatId.value
  const threadState = getThreadState(threadId)
  if (isProcessing.value && threadState) {
    if (useRunsApi && threadState.activeRunId) {
      try {
        await agentApi.cancelAgentRun(threadState.activeRunId)
        message.info('已发送取消请求')
      } catch (error) {
        handleChatError(error, 'stop')
      }
      return
    }

    if (threadState.streamAbortController) {
      // 中断生成
      threadState.streamAbortController.abort()

      // 中断后刷新消息历史，确保显示最新的状态
      try {
        await fetchThreadMessages({ agentId: currentAgentId.value, threadId: threadId, delay: 500 })
        fetchAgentState(currentAgentId.value, threadId)
        message.info('已中断对话生成')
      } catch (error) {
        console.error('刷新消息历史失败:', error)
        message.info('已中断对话生成')
      }
      return
    }
  }
  await handleSendMessage(payload)
}

// ==================== 人工审批处理 ====================
const handleApprovalWithStream = async (answer) => {
  const threadId = approvalState.threadId
  if (!threadId) {
    message.error('无效的提问请求')
    approvalState.showModal = false
    return
  }

  const threadState = getThreadState(threadId)
  if (!threadState) {
    message.error('无法找到对应的对话线程')
    approvalState.showModal = false
    return
  }

  try {
    // 使用审批 composable 处理审批
    const response = await handleApproval(answer, currentAgentId.value, selectedAgentConfigId.value)

    if (!response) return // 如果 handleApproval 抛出错误，这里不会执行

    // 处理流式响应
    await handleAgentResponse(response, threadId)
  } catch (error) {
    if (error.name !== 'AbortError') {
      console.error('Resume approval error:', error)
    }
  } finally {
    if (threadState) {
      threadState.isStreaming = false
      threadState.streamAbortController = null
    }

    // 异步加载历史记录，保持当前消息显示直到历史记录加载完成
    fetchThreadMessages({ agentId: currentAgentId.value, threadId: threadId }).finally(() => {
      resetOnGoingConv(threadId)
      fetchAgentState(currentAgentId.value, threadId)
      scrollController.scrollToBottom()
    })
  }
}

const handleQuestionSubmit = (answer) => {
  handleApprovalWithStream(answer)
}

const handleQuestionCancel = () => {
  handleApprovalWithStream('reject')
}

// 处理示例问题点击
const handleExampleClick = (questionText) => {
  userInput.value = questionText
  nextTick(() => {
    handleSendMessage()
  })
}

const buildExportPayload = () => {
  const agentId = currentAgentId.value
  let agentDescription = ''
  if (agentId && agents.value && agents.value.length > 0) {
    const agent = agents.value.find((a) => a.id === agentId)
    agentDescription = agent ? agent.description || '' : ''
  }

  const payload = {
    chatTitle: currentThread.value?.title || '新对话',
    agentName: currentAgentName.value || currentAgent.value?.name || '智能助手',
    agentDescription: agentDescription || currentAgent.value?.description || '',
    messages: conversations.value ? JSON.parse(JSON.stringify(conversations.value)) : [],
    onGoingMessages: onGoingConvMessages.value
      ? JSON.parse(JSON.stringify(onGoingConvMessages.value))
      : []
  }

  return payload
}

defineExpose({
  getExportPayload: buildExportPayload,
  selectThreadFromRoute
})

const handleAgentStateRefresh = async (threadId = null) => {
  if (!currentAgentId.value) return
  const chatId = threadId || currentChatId.value
  if (!chatId) return
  await Promise.all([
    fetchAgentState(currentAgentId.value, chatId),
    refreshThreadFilesAndAttachments(chatId)
  ])
}

const toggleAgentPanel = async () => {
  const nextOpen = !isAgentPanelOpen.value
  isAgentPanelOpen.value = nextOpen

  if (!nextOpen) {
    isAgentPanelExpanded.value = false
  }

  if (nextOpen) {
    await handleAgentStateRefresh()
  }
}

const togglePanelExpanded = () => {
  if (!isAgentPanelOpen.value) return
  isAgentPanelExpanded.value = !isAgentPanelExpanded.value
}

// 处理面板宽度调整（使用比例）
// 向右拖动(deltaX > 0)让面板变窄，向左拖动(deltaX < 0)让面板变宽
const handlePanelResize = (clientX) => {
  if (!panelWrapperRef.value) return

  if (!panelContainerWidth) {
    const container = document.querySelector('.chat-content-container')
    panelContainerWidth = container ? container.clientWidth : window.innerWidth
  }

  const deltaX = clientX - resizeStartX
  const newWidth = resizeStartWidth - deltaX
  const newRatio = newWidth / panelContainerWidth
  const { min, max } = getPanelRatioBounds()
  const clampedRatio = Math.min(max, Math.max(min, newRatio))
  const clampedWidth = Math.round(panelContainerWidth * clampedRatio)

  panelWrapperRef.value.style.setProperty('flex', `0 0 ${clampedWidth}px`, 'important')
}

// 拖拽状态变化时，同步最终状态到 Vue 响应式数据
const handleResizingChange = (isResizingState, clientX = 0) => {
  isResizing.value = isResizingState

  if (isResizingState && panelWrapperRef.value) {
    resizeStartX = clientX
    resizeStartWidth = panelWrapperRef.value.offsetWidth
    if (!panelContainerWidth) {
      const container = document.querySelector('.chat-content-container')
      panelContainerWidth = container ? container.clientWidth : window.innerWidth
    }
    return
  }

  if (!isResizingState && panelWrapperRef.value && panelContainerWidth) {
    const finalWidth = panelWrapperRef.value.offsetWidth
    const { min, max } = getPanelRatioBounds()
    panelRatio.value = Math.min(max, Math.max(min, finalWidth / panelContainerWidth))
    panelWrapperRef.value.style.removeProperty('flex')
    resizeStartX = 0
    resizeStartWidth = 0
    panelContainerWidth = 0 // 重置，供下次使用
  }
}

// ==================== HELPER FUNCTIONS ====================
const extractAssistantMessageBody = (message) => {
  let content = typeof message?.content === 'string' ? message.content.trim() : ''
  let reasoningContent = message?.additional_kwargs?.reasoning_content || ''

  if (!reasoningContent && content) {
    const thinkRegex = /<think>(.*?)<\/think>|<think>(.*?)$/s
    const thinkMatch = content.match(thinkRegex)

    if (thinkMatch) {
      reasoningContent = (thinkMatch[1] || thinkMatch[2] || '').trim()
      content = content.replace(thinkMatch[0], '').trim()
    }
  }

  return { content, reasoningContent }
}

const hasVisibleAssistantBody = (message) => {
  if (!message || message.type !== 'ai') return true

  const { content, reasoningContent } = extractAssistantMessageBody(message)
  return Boolean(
    content ||
    reasoningContent ||
    message.error_type ||
    message.extra_metadata?.error_type ||
    message.isStoppedByUser
  )
}

const getMessageToolCalls = (message) => {
  if (!Array.isArray(message?.tool_calls)) return []

  return message.tool_calls.filter((toolCall) => {
    return (
      toolCall &&
      (toolCall.id || toolCall.name || toolCall.function?.name) &&
      (toolCall.args !== undefined ||
        toolCall.function?.arguments !== undefined ||
        toolCall.tool_call_result !== undefined)
    )
  })
}

const isFinalResponseMessage = (message) => {
  if (!message || message.type !== 'ai') return false

  const messageId = String(message.id || '')
  const streamStatus = message.extra_metadata?.stream_status

  return Boolean(
    message.extra_metadata?.is_final_response ||
      streamStatus === 'final_response' ||
      streamStatus === 'final_response_delta' ||
      messageId.includes(':zz-final-response') ||
      messageId.includes(':final-response')
  )
}

const normalizeStreamingDisplayItems = (items, conv) => {
  if (conv?.status !== 'streaming') return items

  const finalMessageIndex = items.findIndex((item) => {
    return item.type === 'message' && isFinalResponseMessage(item.message)
  })

  if (finalMessageIndex < 0) return items

  const beforeFinal = items.slice(0, finalMessageIndex)
  const fromFinal = items.slice(finalMessageIndex)

  const lateToolGroups = []
  const rest = []

  fromFinal.forEach((item) => {
    if (item.type === 'tool-group') {
      lateToolGroups.push(item)
    } else {
      rest.push(item)
    }
  })

  if (lateToolGroups.length === 0) return items

  return [...beforeFinal, ...lateToolGroups, ...rest]
}

const buildStableToolGroupKey = (message, index) => {
  const messageId =
    message?.id ||
    message?.extra_metadata?.request_id ||
    message?.additional_kwargs?.request_id ||
    index

  return `tool-group-${messageId}`
}

// 将 AI 消息拆成“工具块”和“正文块”，再跨消息合并相邻工具块。
// 关键点：工具组 key 只基于首个工具 AI message 的 message.id，不能基于 toolCalls 列表。
// 否则新增工具、工具结果返回、tool_call_delta -> tool_call 完整化时，key 会变化，组件会被强制重建。
const getConversationDisplayItems = (conv) => {
  if (!Array.isArray(conv?.messages) || conv.messages.length === 0) return []

  const items = []
  let pendingToolGroup = null

  const flushToolGroup = () => {
    if (pendingToolGroup && pendingToolGroup.toolCalls.length > 0) {
      items.push({
        type: 'tool-group',
        key: pendingToolGroup.key,
        toolCalls: pendingToolGroup.toolCalls
      })
    }

    pendingToolGroup = null
  }

  conv.messages.forEach((message, index) => {
    if (message.type !== 'ai') {
      flushToolGroup()

      items.push({
        type: 'message',
        key: message.id || `message-${index}`,
        message,
        sourceIndex: index
      })
      return
    }

    const toolCalls = getMessageToolCalls(message)

    if (toolCalls.length > 0) {
      if (!pendingToolGroup) {
        pendingToolGroup = {
          type: 'tool-group',
          key: buildStableToolGroupKey(message, index),
          toolCalls: []
        }
      }

      pendingToolGroup.toolCalls.push(...toolCalls)
    }

    if (hasVisibleAssistantBody(message)) {
      flushToolGroup()

      items.push({
        type: 'message',
        key: message.id || `message-${index}`,
        message,
        sourceIndex: index
      })
    }
  })

  flushToolGroup()
  return normalizeStreamingDisplayItems(items, conv)
}


const isDisplayMessageProcessing = (conv, displayItem) => {
  return (
    displayItem?.type === 'message' &&
    isReplyLoading.value &&
    conv?.status === 'streaming' &&
    displayItem.sourceIndex === conv.messages.length - 1
  )
}

const isToolGroupActive = (conv, itemIndex, displayItems) => {
  return (
    isReplyLoading.value && conv?.status === 'streaming' && itemIndex === displayItems.length - 1
  )
}

const getLastMessage = (conv) => {
  if (!conv?.messages?.length) return null
  for (let i = conv.messages.length - 1; i >= 0; i--) {
    if (conv.messages[i].type === 'ai') return conv.messages[i]
  }
  return null
}

const showMsgRefs = (msg) => {
  // 如果正在审批中，不显示 refs
  if (approvalState.showModal) {
    return false
  }

  // 如果当前线程ID与审批线程ID匹配，但审批框已关闭（说明刚刚处理完审批）
  // 且当前有新的流式处理正在进行，则不显示之前被中断的消息的 refs
  if (
    approvalState.threadId &&
    chatState.currentThreadId === approvalState.threadId &&
    !approvalState.showModal &&
    isProcessing
  ) {
    return false
  }

  // 只有真正完成的消息才显示 refs
  if (msg.isLast && msg.status === 'finished') {
    return ['copy', 'sources']
  }
  return false
}

const getConversationSources = (conv) => {
  return MessageProcessor.extractSourcesFromConversation(conv, availableKnowledgeBases.value)
}

// ==================== LIFECYCLE & WATCHERS ====================
const loadChatsList = async () => {
  const agentId = props.singleMode ? currentAgentId.value : null
  if (props.singleMode && !agentId) {
    console.warn('No agent selected, cannot load chats list')
    threads.value = []
    setCurrentThreadId(null)
    threadFilesMap.value = {}
    threadAttachmentsMap.value = {}
    return
  }

  try {
    await fetchThreads(agentId)
    if (props.singleMode && currentAgentId.value !== agentId) return

    // 如果当前线程不在线程列表中，清空当前线程
    if (
      chatState.currentThreadId &&
      !threads.value.find((t) => t.id === chatState.currentThreadId)
    ) {
      setCurrentThreadId(null)
    }

    // singleMode 保持旧行为：自动选择首个可用对话
    if (props.singleMode && threads.value.length > 0 && !chatState.currentThreadId) {
      await selectChat(getFirstNonPinnedChat(threads.value).id)
    }
  } catch (error) {
    handleChatError(error, 'load')
  }
}

const initAll = async () => {
  try {
    if (!agentStore.isInitialized) {
      await agentStore.initialize()
    }
  } catch (error) {
    handleChatError(error, 'load')
  }
}

onMounted(async () => {
  await Promise.all([initAll(), fetchWorkspaceMentionFiles()])
  scrollController.enableAutoScroll()
})

watch(
  currentAgentId,
  async (newAgentId, oldAgentId) => {
    if (!props.singleMode) {
      if (oldAgentId === undefined) {
        await loadChatsList()
      }
      return
    }

    if (newAgentId !== oldAgentId) {
      // 清理当前线程状态
      setCurrentThreadId(null)
      threadMessages.value = {}
      threadFilesMap.value = {}
      threadAttachmentsMap.value = {}
      // 清理所有线程状态
      resetOnGoingConv()

      if (newAgentId) {
        await loadChatsList()
      } else {
        threads.value = []
      }
    }
  },
  { immediate: true }
)

watch(
  currentThreadMessages,
  () => {
    if (currentThreadHasHistory.value) {
      flushPendingThreadConfigNotice(currentChatId.value)
      syncThreadConfigSnapshot(currentChatId.value, { overwrite: false })
    }
  },
  { deep: false }
)

watch(currentAgentId, (newAgentId, oldAgentId) => {
  if (oldAgentId === undefined || newAgentId === oldAgentId) return
  maybeInsertThreadConfigNotice()
})

watch(selectedAgentConfigId, (newConfigId, oldConfigId) => {
  if (oldConfigId === undefined || newConfigId === oldConfigId) return
  maybeInsertThreadConfigNotice()
})

watch(
  () => JSON.stringify(agentConfig.value || {}),
  (newConfigJson, oldConfigJson) => {
    if (oldConfigJson === undefined || newConfigJson === oldConfigJson) return
    maybeInsertThreadConfigNotice()
  }
)

watch(
  conversations,
  () => {
    if (isProcessing.value) {
      scrollController.scrollToBottom()
    }
  },
  { deep: true, flush: 'post' }
)

watch(
  configNoticeScrollVersion,
  () => {
    if (!currentChatId.value) return
    scrollController.scrollToBottom(true)
  },
  { flush: 'post' }
)

watch(currentChatId, (threadId, oldThreadId) => {
  if (threadId === oldThreadId) return
  emit('thread-change', threadId || '')
})
</script>

<style lang="less" scoped>
@import '@/assets/css/main.css';
@import '@/assets/css/animations.less';

.chat-container {
  display: flex;
  width: 100%;
  height: 100%;
  position: relative;

  --start-content-width: 1060px;
  --start-side-gap: 96px;

  background:
    radial-gradient(
      circle at 50% 0%,
      color-mix(in srgb, var(--main-color) 5%, transparent) 0%,
      color-mix(in srgb, var(--sub-color) 3%, transparent) 28%,
      transparent 56%
    ),
    linear-gradient(
      180deg,
      color-mix(in srgb, var(--main-color) 2%, var(--gray-0)) 0%,
      color-mix(in srgb, var(--sub-color) 1.5%, var(--gray-0)) 40%,
      var(--gray-0) 100%
    );
}

.chat {
  position: relative;
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden; /* Changed from overflow-x: hidden to overflow: hidden */
  box-sizing: border-box;
  transition: all 0.3s ease;
  background: transparent;

  .chat-header {
    user-select: none;
    z-index: 10;
    height: var(--header-height);
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem 8px;
    flex-shrink: 0; /* Prevent header from shrinking */

    .header__left,
    .header__right {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .switch-icon {
      color: var(--gray-500);
      transition: all 0.2s ease;
    }

    .agent-nav-btn:hover .switch-icon {
      color: var(--main-500);
    }

    .conversation-title {
      font-size: 15px;
      font-weight: 400;
      color: var(--text-primary);
      max-width: 200px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      margin-left: 8px;
    }
  }
}

.chat-content-container {
  flex: 1;
  display: flex;
  flex-direction: row;
  overflow: hidden;
  position: relative;
  width: 100%;
  contain: layout;
  background: transparent;
}

.chat-main {
  flex: 1 1 0;
  flex-basis: 0;
  display: flex;
  flex-direction: column;
  overflow-y: auto; /* Scroll is here now */
  position: relative;
  min-width: 0; /* Prevent flex item from overflowing */
  background: transparent;
  transition:
    flex-basis 0.3s cubic-bezier(0.4, 0, 0.2, 1),
    width 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  // scrollbar-width: none;
}

.agent-panel-wrapper {
  flex: 0 0 auto;
  align-self: flex-end;
  height: 70vh;
  overflow: hidden;
  z-index: 20;
  margin: 28px 8px;
  margin-left: 0;
  background: var(--gray-0);
  border-radius: 16px;
  border: 1px solid var(--gray-150);
  min-width: 0;
  will-change: flex-basis;
}

.agent-panel-wrapper.is-expanded {
  align-self: stretch;
  height: calc(100% - 16px);
  margin-top: 8px;
  margin-bottom: 8px;
}

@media (max-height: 700px) {
  .agent-panel-wrapper {
    height: calc(100% - 56px);
  }

  .agent-panel-wrapper.is-expanded {
    height: calc(100% - 16px);
  }
}

/* Workbench transition animations */
.agent-panel-wrapper {
  transition: flex-basis 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  opacity: 0;
  transform: translateX(10px);
  margin-left: -16px;
}

.agent-panel-wrapper.is-visible {
  opacity: 1;
  transform: translateX(0);
  margin-left: 0;
}

.agent-panel-wrapper.no-transition {
  transition: none !important;
}

.start-hero {
  position: absolute;
  top: clamp(88px, 14vh, 140px);
  left: 50%;
  transform: translateX(-50%);
  z-index: 3;
  width: min(820px, calc(100% - 48px));
  display: flex;
  justify-content: center;
  pointer-events: none;
}

.start-hero-card {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  max-width: 100%;
  padding: 0;

  background: transparent;
  border: none;
  box-shadow: none;
}

.start-hero-logo {
  width: 70px;
  height: 70px;
  flex: 0 0 auto;
  object-fit: contain;
  border-radius: 12px;
}

.start-hero-text {
  min-width: 0;
  text-align: left;

  h1 {
    margin: 0;
    color: var(--gray-950);
    font-size: clamp(1.42rem, 2vw, 1.9rem);
    font-weight: 750;
    line-height: 1.3;
    letter-spacing: -0.025em;
  }

  p {
    margin: 6px 0 0;
    color: var(--gray-600);
    font-size: 13px;
    line-height: 1.5;
  }
}

.agent-segment-wrapper {
  width: fit-content;
  max-width: 100%;
  margin: 0 auto 18px;
  overflow-x: auto;
  scrollbar-width: none;

  &::-webkit-scrollbar {
    display: none;
  }

  :deep(.ant-segmented) {
    width: auto;
    max-width: 100%;
    white-space: nowrap;
    background: var(--gray-50);
    border: 1px solid var(--gray-150);
    border-radius: 10px;
  }

  :deep(.ant-segmented-group) {
    width: auto;
    display: inline-flex;
  }

  :deep(.ant-segmented-item) {
    flex: 0 0 auto;
    min-width: 0;
  }

  :deep(.ant-segmented-item-label) {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.agent-switcher-wrapper {
  display: flex;
  justify-content: center;
  margin: 0 auto 18px;
}

.agent-switcher-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  max-width: 100%;
  padding: 4px 12px;
  border: 1px solid var(--gray-150);
  border-radius: 8px;
  background: var(--gray-0);
  color: var(--gray-900);
  cursor: pointer;
  transition:
    background-color 0.2s ease,
    border-color 0.2s ease,
    color 0.2s ease;

  &:hover {
    background: var(--gray-0);
    border-color: var(--gray-200);
  }
}

.agent-switcher-icon,
.agent-switcher-chevron {
  flex-shrink: 0;
  color: var(--gray-600);
}

.agent-switcher-text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:deep(.agent-switcher-menu) {
  min-width: 220px;
}

:deep(.agent-switcher-menu-item) {
  display: flex;
  align-items: center;
  gap: 8px;
}

:deep(.agent-switcher-menu-icon) {
  flex-shrink: 0;
  color: var(--gray-600);
}

:deep(.agent-switcher-menu-text) {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:deep(.agent-switcher-menu-badge) {
  flex-shrink: 0;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--main-30);
  color: var(--main-700);
  font-size: 12px;
}

.example-questions {
  margin: 0 0 14px;
  padding: 0;
  text-align: center;

  .example-chips {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
    width: 100%;
    margin: 0 auto;
  }

  .example-row {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 12px;
    width: 100%;
    flex-wrap: nowrap;
  }

  .example-chip {
    flex: 0 0 260px;
    width: 260px;
    max-width: 260px;
    min-width: 0;
    padding: 8px 16px;

    border: 1px solid color-mix(in srgb, var(--main-color) 10%, transparent);
    border-radius: 999px;

    background: linear-gradient(
      180deg,
      color-mix(in srgb, var(--gray-0) 95%, var(--main-color) 5%),
      color-mix(in srgb, var(--gray-0) 95%, var(--sub-color) 5%)
    );

    color: var(--gray-700);
    font-size: 13px;
    line-height: 1.35;
    font-weight: 500;
    cursor: pointer;
    user-select: none;

    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;

    box-shadow:
      0 1px 2px rgba(0, 0, 0, 0.02),
      0 6px 14px color-mix(in srgb, var(--main-color) 4%, transparent);

    transition:
      transform 0.18s ease,
      color 0.18s ease,
      border-color 0.18s ease,
      background 0.18s ease,
      box-shadow 0.18s ease;

    &:hover {
      transform: translateY(-1px);
      color: var(--main-bright);
      border-color: color-mix(in srgb, var(--main-color) 7%, transparent);

      background: linear-gradient(
        180deg,
        color-mix(in srgb, var(--gray-0) 97%, var(--main-color) 3%),
        color-mix(in srgb, var(--gray-0) 97%, var(--sub-color) 3%)
      );

      box-shadow:
        0 1px 2px rgba(0, 0, 0, 0.015),
        0 6px 12px color-mix(in srgb, var(--main-color) 2%, transparent);
    }

    &:active {
      transform: translateY(0);
      color: var(--main-700);
      border-color: color-mix(in srgb, var(--main-color) 34%, transparent);

      background: linear-gradient(
        180deg,
        color-mix(in srgb, var(--main-color) 18%, var(--gray-0)),
        color-mix(in srgb, var(--sub-color) 10%, var(--gray-0))
      );
    }

    &.active,
    &.selected {
      color: var(--main-bright);
      border-color: color-mix(in srgb, var(--main-color) 36%, transparent);

      background: linear-gradient(
        180deg,
        color-mix(in srgb, var(--main-color) 16%, var(--gray-0)),
        color-mix(in srgb, var(--sub-color) 10%, var(--gray-0))
      );

      box-shadow:
        0 4px 14px color-mix(in srgb, var(--main-color) 12%, transparent),
        0 12px 28px color-mix(in srgb, var(--sub-color) 10%, transparent);
    }
  }
}

/* 桌面端隐藏 inline 版本（由移动端滚动展示） */
.example-questions--inline {
  display: none;
}

.chat-loading {
  padding: 0 50px;
  text-align: center;
  position: absolute;
  top: 20%;
  width: 100%;
  z-index: 9;
  animation: slideInUp 0.5s ease-out;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;

  span {
    color: var(--gray-700);
    font-size: 14px;
  }

  .loading-spinner {
    width: 20px;
    height: 20px;
    border: 2px solid var(--gray-200);
    border-top-color: var(--main-color);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
}

.chat-box {
  width: 100%;
  max-width: 800px;
  margin: 0 auto;
  flex-grow: 1;
  padding: 1rem 1.5rem;
  display: flex;
  flex-direction: column;
}

.conv-box {
  display: flex;
  flex-direction: column;
}

.chat-inline-notice {
  display: flex;
  justify-content: center;
  padding: 6px 16px 12px;
  color: var(--gray-500);
  font-size: 12px;
  line-height: 1.6;
  text-align: center;
}

.bottom {
  position: sticky;
  bottom: 0;
  width: 100%;
  margin: 0 auto;
  padding: 12px 1rem 16px;
  z-index: 1000;

  background: linear-gradient(
    180deg,
    transparent 0%,
    color-mix(in srgb, var(--gray-0) 78%, var(--main-color) 4%) 34%,
    color-mix(in srgb, var(--gray-0) 92%, var(--sub-color) 4%) 100%
  );

  .message-input-wrapper {
    width: 100%;
    max-width: 800px;
    margin: 0 auto;

    .bottom-actions {
      display: flex;
      justify-content: center;
      align-items: center;
      width: 100%;
      background: transparent;
    }

    .note {
      font-size: small;
      color: var(--gray-300);
      margin: 4px 0;
      user-select: none;
    }
  }

  &.start-screen {
    position: absolute;
    top: auto;
    bottom: clamp(42px, 9vh, 92px);
    left: 50%;
    transform: translateX(-50%);
    width: min(var(--start-content-width), calc(100% - var(--start-side-gap)));
    max-width: var(--start-content-width);
    padding: 0;
    border-top: none;
    background: transparent;
    z-index: 100;
  }

  &.start-screen .message-input-wrapper {
    max-width: 100%;
  }
}

.loading-dots {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
}

.loading-dots div {
  width: 6px;
  height: 6px;
  background: linear-gradient(135deg, var(--main-color), var(--main-700));
  border-radius: 50%;
  animation: dotPulse 1.4s infinite ease-in-out both;
}

.loading-dots div:nth-child(1) {
  animation-delay: -0.32s;
}

.loading-dots div:nth-child(2) {
  animation-delay: -0.16s;
}

.loading-dots div:nth-child(3) {
  animation-delay: 0s;
}

.generating-status {
  display: flex;
  justify-content: flex-start;
  padding: 1rem 0;
  animation: fadeInUp 0.4s ease-out;
  transition: all 0.2s;
}

.generating-indicator {
  display: flex;
  align-items: center;
  padding: 0.75rem 0rem;

  .generating-text {
    margin-left: 12px;
    font-size: 14px;
    font-weight: 500;
    letter-spacing: 0.025em;
    /* 恢复灰色调：深灰 -> 亮灰(高光) -> 深灰 */
    background: linear-gradient(
      90deg,
      var(--gray-700) 0%,
      var(--gray-700) 40%,
      var(--gray-300) 45%,
      var(--gray-200) 50%,
      var(--gray-300) 55%,
      var(--gray-700) 60%,
      var(--gray-700) 100%
    );
    background-size: 200% auto;
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    animation: waveFlash 2s linear infinite;
  }
}

@keyframes waveFlash {
  0% {
    background-position: 200% center;
  }
  100% {
    background-position: -200% center;
  }
}

@media (max-width: 768px) {
  .start-hero {
    top: 72px;
    width: calc(100% - 28px);
  }

  .start-hero-card {
    width: 100%;
    justify-content: center;
  }

  .start-hero-logo {
    width: 36px;
    height: 36px;
  }

  .start-hero-text {
    h1 {
      font-size: 17px;
    }

    p {
      font-size: 12px;
    }
  }

  .bottom.start-screen {
    bottom: 24px;
    width: calc(100% - 24px);
  }

  .example-questions {
    .example-chips {
      gap: 8px;
    }

    .example-row {
      flex-direction: column;
      gap: 8px;
    }

    .example-chip {
      flex: 0 0 auto;
      width: 100%;
      max-width: 320px;
      padding: 7px 12px;
      font-size: 12px;
    }
  }
}

.start-showcase {
  position: absolute;
  top: clamp(220px, 30vh, 286px);
  left: 50%;
  transform: translateX(-50%);
  z-index: 2;

  width: min(var(--start-content-width), calc(100% - var(--start-side-gap)));
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: clamp(28px, 4vw, 52px);
  align-items: stretch;
  pointer-events: auto;
}

.showcase-column {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 14px;

  color: color-mix(in srgb, var(--gray-900) 86%, var(--main-color) 14%);
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.section-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: linear-gradient(135deg, var(--main-color), var(--sub-color));
  box-shadow:
    0 0 0 4px color-mix(in srgb, var(--main-color) 8%, transparent),
    0 0 18px color-mix(in srgb, var(--main-color) 18%, transparent);
}

.task-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  flex: 1;
}

.task-card,
.model-card,
.workflow-card {
  border: 1px solid color-mix(in srgb, var(--main-color) 7%, transparent);
  background:
    linear-gradient(
      145deg,
      color-mix(in srgb, var(--gray-0) 98.5%, var(--main-color) 1.5%),
      color-mix(in srgb, var(--gray-0) 99.2%, var(--sub-color) 0.8%)
    );
  box-shadow:
    0 10px 28px rgba(0, 0, 0, 0.022),
    0 18px 42px color-mix(in srgb, var(--main-color) 2.8%, transparent),
    inset 0 1px 0 rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(10px);
}

.task-card {
  min-height: 104px;
  padding: 18px 18px 16px;
  border-radius: 22px;

  display: flex;
  align-items: flex-start;
  gap: 13px;

  text-align: left;
  cursor: default;
  user-select: none;

  transition:
    transform 0.18s ease,
    border-color 0.18s ease,
    box-shadow 0.18s ease;

  &:hover {
    transform: translateY(-1px);
    border-color: color-mix(in srgb, var(--main-color) 12%, transparent);
    box-shadow:
      0 12px 30px rgba(0, 0, 0, 0.026),
      0 20px 44px color-mix(in srgb, var(--main-color) 3.5%, transparent),
      inset 0 1px 0 rgba(255, 255, 255, 0.88);
  }
}

.task-icon {
  width: 38px;
  height: 38px;
  flex: 0 0 auto;

  display: flex;
  align-items: center;
  justify-content: center;

  border-radius: 14px;
  background:
    linear-gradient(
      145deg,
      color-mix(in srgb, var(--gray-0) 95%, var(--main-color) 5%),
      color-mix(in srgb, var(--gray-0) 98%, var(--sub-color) 2%)
    );
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.86);

  font-size: 20px;
}

.task-content {
  min-width: 0;
}

.task-title {
  color: var(--gray-900);
  font-size: 14px;
  font-weight: 720;
  line-height: 1.35;
}

.task-desc {
  margin-top: 7px;
  color: var(--gray-600);
  font-size: 12px;
  line-height: 1.65;
}

.model-card {
  flex: 1;
  min-height: 158px;
  padding: 20px 22px 18px;
  border-radius: 24px;

  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.model-card-main {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px;
  align-items: start;

  p {
    margin: 7px 0 0;
    color: var(--gray-650);
    font-size: 13px;
    line-height: 1.85;
  }
}

.model-kicker {
  width: fit-content;
  padding: 3px 9px;
  border-radius: 999px;

  background: color-mix(in srgb, var(--main-color) 6%, transparent);
  color: color-mix(in srgb, var(--main-700) 84%, var(--gray-700) 16%);

  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.crop-tags {
  display: grid;
  grid-template-columns: repeat(2, auto);
  gap: 7px;

  span {
    padding: 4px 9px;
    border-radius: 999px;
    background: color-mix(in srgb, var(--gray-0) 96%, var(--main-color) 4%);
    border: 1px solid color-mix(in srgb, var(--main-color) 7%, transparent);
    color: var(--gray-600);
    font-size: 12px;
    line-height: 1.2;
    white-space: nowrap;
  }
}

.capability-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 18px;

  span {
    padding: 5px 11px;
    border-radius: 999px;

    background:
      linear-gradient(
        180deg,
        color-mix(in srgb, var(--gray-0) 96.5%, var(--main-color) 3.5%),
        color-mix(in srgb, var(--gray-0) 98.5%, var(--sub-color) 1.5%)
      );
    border: 1px solid color-mix(in srgb, var(--main-color) 8%, transparent);

    color: color-mix(in srgb, var(--main-700) 76%, var(--gray-600) 24%);
    font-size: 12px;
    font-weight: 600;
  }
}

.workflow-card {
  position: relative;
  margin-top: 14px;
  min-height: 86px;
  padding: 17px 18px 15px;
  border-radius: 22px;

  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
  overflow: hidden;
}

.workflow-line {
  position: absolute;
  top: 30px;
  left: 44px;
  right: 44px;
  height: 1px;
  background:
    linear-gradient(
      90deg,
      transparent,
      color-mix(in srgb, var(--main-color) 18%, transparent),
      color-mix(in srgb, var(--sub-color) 14%, transparent),
      transparent
    );
}

.workflow-step {
  position: relative;
  z-index: 1;
  min-width: 0;

  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;

  color: var(--gray-600);
  font-size: 12px;
  line-height: 1.35;
  text-align: center;
}

.workflow-index {
  width: 26px;
  height: 26px;
  border-radius: 999px;

  display: flex;
  align-items: center;
  justify-content: center;

  background:
    linear-gradient(
      145deg,
      color-mix(in srgb, var(--gray-0) 88%, var(--main-color) 12%),
      color-mix(in srgb, var(--gray-0) 94%, var(--sub-color) 6%)
    );
  border: 1px solid color-mix(in srgb, var(--main-color) 14%, transparent);
  box-shadow:
    0 4px 10px color-mix(in srgb, var(--main-color) 5%, transparent),
    inset 0 1px 0 rgba(255, 255, 255, 0.9);

  color: var(--main-700);
  font-size: 12px;
  font-weight: 800;
}

// 智能体选择器的图标对齐
.agent-segment-wrapper {
  :deep(.ant-segmented-item-label) {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  :deep(.agent-option-label) {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  :deep(.agent-option-icon) {
    flex-shrink: 0;
    color: var(--gray-600);
  }
}

/* ==================== Responsive Fixes ==================== */

/* 避免移动端浏览器地址栏变化和 flex 子项默认最小高度导致布局跳动 */
.chat-container,
.chat,
.chat-content-container {
  min-height: 0;
}

.chat-container {
  height: 100%;
  min-height: 100%;
}

/* 中等笔记本：降低首页首屏内容密度，避免 hero / showcase / input 重叠 */
@media (min-width: 769px) and (max-width: 1366px), (min-width: 769px) and (max-height: 920px) {
  .chat .chat-header {
    padding: 0.75rem 8px;
  }

  .start-hero {
    top: clamp(64px, 10vh, 102px);
    width: min(760px, calc(100% - 56px));
  }

  .start-hero-logo {
    width: 54px;
    height: 54px;
  }

  .start-hero-text {
    h1 {
      font-size: clamp(1.2rem, 1.7vw, 1.55rem);
      line-height: 1.25;
    }

    p {
      font-size: 12px;
      margin-top: 4px;
    }
  }

  .start-showcase {
    top: clamp(158px, 23vh, 214px);
    width: min(960px, calc(100% - 64px));
    gap: clamp(18px, 2.8vw, 32px);
  }

  .section-title {
    margin-bottom: 10px;
    font-size: 13px;
  }

  .task-grid {
    gap: 10px;
  }

  .task-card {
    min-height: 86px;
    padding: 14px 14px 12px;
    border-radius: 18px;
    gap: 10px;
  }

  .task-icon {
    width: 32px;
    height: 32px;
    border-radius: 12px;
    font-size: 17px;
  }

  .task-title {
    font-size: 13px;
  }

  .task-desc {
    margin-top: 5px;
    font-size: 11.5px;
    line-height: 1.5;
  }

  .model-card {
    min-height: 130px;
    padding: 15px 16px 14px;
    border-radius: 20px;
  }

  .model-card-main {
    gap: 12px;

    p {
      margin-top: 6px;
      font-size: 12px;
      line-height: 1.6;
    }
  }

  .crop-tags {
    gap: 6px;

    span {
      padding: 3px 8px;
      font-size: 11px;
    }
  }

  .capability-tags {
    margin-top: 12px;
    gap: 6px;

    span {
      padding: 4px 9px;
      font-size: 11px;
    }
  }

  .workflow-card {
    min-height: 72px;
    margin-top: 10px;
    padding: 13px 14px 12px;
    border-radius: 18px;
  }

  .workflow-line {
    top: 25px;
    left: 34px;
    right: 34px;
  }

  .workflow-index {
    width: 22px;
    height: 22px;
    font-size: 11px;
  }

  .workflow-step {
    gap: 6px;
    font-size: 11px;
  }

  .bottom.start-screen {
    bottom: clamp(18px, 5vh, 44px);
    width: min(820px, calc(100% - 40px));
  }

  .example-questions {
    margin-bottom: 10px;

    .example-chips {
      gap: 8px;
    }

    .example-row {
      gap: 10px;
    }

    .example-chip {
      flex-basis: 220px;
      width: 220px;
      max-width: 220px;
      padding: 7px 12px;
      font-size: 12px;
    }
  }
}

/* 宽屏 + 中高视口 (921-1000px)：介于紧凑和大屏之间的过渡间距，避免 showcase 与底部重叠 */
@media (min-width: 1367px) and (min-height: 921px) and (max-height: 1000px) {
  .start-hero {
    top: clamp(72px, 11vh, 120px);
  }

  .start-showcase {
    top: clamp(180px, 24vh, 250px);
  }

  .bottom.start-screen {
    bottom: clamp(24px, 6vh, 58px);
  }
}

/* 窄笔记本 / 平板横屏：右侧介绍区收敛，避免首屏撑爆 */
@media (min-width: 769px) and (max-width: 1100px) {
  .start-showcase {
    width: min(760px, calc(100% - 48px));
    grid-template-columns: 1fr;
    top: clamp(154px, 22vh, 196px);
    gap: 16px;
  }

  .showcase-column-right {
    display: none;
  }

  .task-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .bottom.start-screen {
    bottom: 22px;
  }
}

/* 小屏下 Agent 面板改为浮层，不再挤压主聊天区 */
@media (max-width: 900px) {
  .chat-content-container {
    display: block;
  }

  .chat-main {
    width: 100%;
    height: 100%;
    flex-basis: auto;
  }

  .agent-panel-wrapper {
    position: fixed;
    top: calc(var(--header-height) + 8px);
    right: 8px;
    bottom: calc(8px + env(safe-area-inset-bottom));
    left: 8px;

    width: auto;
    height: auto;
    margin: 0;
    border-radius: 18px;
    z-index: 1200;

    flex: none !important;
    flex-basis: auto !important;

    opacity: 0;
    pointer-events: none;
    transform: translateY(12px);
  }

  .agent-panel-wrapper.is-visible {
    opacity: 1;
    pointer-events: auto;
    transform: translateY(0);
  }

  .agent-panel-wrapper.is-expanded {
    top: 8px;
    right: 8px;
    bottom: calc(8px + env(safe-area-inset-bottom));
    left: 8px;
    height: auto;
    margin: 0;
  }
}

/* 手机端：首页改为自然文档流，避免 absolute 重叠 */
@media (max-width: 768px) {
  .chat .chat-header {
    height: auto;
    min-height: var(--header-height);
    padding: 0.65rem 10px;

    .conversation-title {
      max-width: 44vw;
      font-size: 14px;
    }
  }

  .chat-main {
    padding-bottom: calc(160px + env(safe-area-inset-bottom));
  }

  .chat-main.has-conversations {
    padding-bottom: 0;
  }

  .chat-box {
    padding: 0.75rem 0.875rem;
  }

  .start-hero {
    position: relative;
    top: auto;
    left: auto;
    transform: none;

    width: calc(100% - 24px);
    margin: 22px auto 14px;
  }

  .start-hero-card {
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: 12px;
  }

  .start-hero-logo {
    width: 56px;
    height: 56px;
    border-radius: 14px;
  }

  .start-hero-text {
    h1 {
      text-align: center;
      font-size: 17px;
      line-height: 1.35;
    }

    p {
      font-size: 12px;
      line-height: 1.45;
      text-align: center;
    }
  }

  .start-showcase {
    position: relative;
    top: auto;
    left: auto;
    transform: none;

    width: calc(100% - 24px);
    margin: 0 auto 14px;

    display: grid;
    grid-template-columns: 1fr;
    gap: 14px;
  }

  .section-title {
    margin-bottom: 10px;
    font-size: 13px;
  }

  .task-grid {
    grid-template-columns: 1fr;
    gap: 10px;
  }

  .task-card {
    min-height: auto;
    padding: 13px 14px;
    border-radius: 18px;
  }

  .task-icon {
    width: 32px;
    height: 32px;
    border-radius: 12px;
    font-size: 17px;
  }

  .task-title {
    font-size: 13px;
  }

  .task-desc {
    margin-top: 4px;
    font-size: 12px;
    line-height: 1.5;
  }

  .model-card {
    min-height: auto;
    padding: 15px;
    border-radius: 18px;
  }

  .model-card-main {
    grid-template-columns: 1fr;
    gap: 12px;

    p {
      font-size: 12px;
      line-height: 1.6;
    }
  }

  .crop-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .capability-tags {
    margin-top: 12px;
    gap: 6px;

    span {
      padding: 4px 9px;
      font-size: 11px;
    }
  }

  .workflow-card {
    min-height: auto;
    margin-top: 10px;
    padding: 14px;
    border-radius: 18px;

    display: flex;
    gap: 8px;
    overflow-x: auto;
    scrollbar-width: none;

    &::-webkit-scrollbar {
      display: none;
    }
  }

  .workflow-line {
    display: none;
  }

  .workflow-step {
    flex: 0 0 64px;
    font-size: 11px;
  }

  .workflow-index {
    width: 24px;
    height: 24px;
    font-size: 11px;
  }

  .bottom {
    padding: 10px 12px calc(12px + env(safe-area-inset-bottom));
  }

  .bottom.start-screen {
    position: fixed;
    right: 12px;
    bottom: calc(12px + env(safe-area-inset-bottom));
    left: 12px;
    transform: none;

    width: auto;
    max-width: none;
    padding: 0;
  }

  .bottom.start-screen .message-input-wrapper {
    max-width: none;
  }

  .agent-segment-wrapper {
    margin-bottom: 10px;
  }

  .agent-switcher-wrapper {
    margin-bottom: 10px;
  }

  .example-questions--fixed {
    display: none;
  }

  .example-questions--inline {
    display: block;
    margin-top: 4px;
    margin-bottom: 12px;
    padding: 0 12px;

    .example-chips {
      align-items: stretch;
      gap: 7px;
    }

    .example-row {
      flex-direction: column;
      gap: 7px;
    }

    .example-chip {
      width: 100%;
      max-width: none;
      padding: 7px 11px;
      font-size: 12px;
    }
  }
}

/* 极窄手机：进一步压缩展示内容，保证输入区优先 */
@media (max-width: 420px) {
  .chat-main {
    padding-bottom: calc(140px + env(safe-area-inset-bottom));
  }

  .chat-main.has-conversations {
    padding-bottom: 0;
  }

  .start-hero {
    margin-top: 16px;
  }

  .start-hero-card {
    align-items: center;
  }

  .start-hero-logo {
    width: 48px;
    height: 48px;
  }

  .start-hero-text {
    h1 {
      font-size: 16px;
    }

    p {
      font-size: 11.5px;
    }
  }

  .start-showcase {
    width: calc(100% - 20px);
    margin-bottom: 14px;
  }

  .showcase-column-right {
    display: none;
  }

  .task-card {
    padding: 12px;
  }

  .bottom.start-screen {
    right: 10px;
    left: 10px;
  }
}

/* 横屏手机：隐藏首页展示区，优先保证输入可用 */
@media (max-width: 768px) and (max-height: 520px) {
  .start-hero {
    margin-top: 10px;
  }

  .start-showcase {
    display: none;
  }

  .chat-main {
    padding-bottom: calc(100px + env(safe-area-inset-bottom));
  }

  .chat-main.has-conversations {
    padding-bottom: 0;
  }

  .example-questions {
    display: none;
  }
}

</style>

<style lang="less">
.agent-nav-btn {
  display: flex;
  gap: 6px;
  padding: 6px 8px;
  height: 32px;
  justify-content: center;
  align-items: center;
  border-radius: 6px;
  color: var(--gray-900);
  cursor: pointer;
  width: auto;
  font-size: 15px;
  transition: background-color 0.3s;
  border: none;
  background: transparent;

  &:hover:not(.is-disabled) {
    background-color: var(--gray-100);
  }

  &.is-disabled {
    cursor: not-allowed;
    opacity: 0.7;
    pointer-events: none;
  }

  .nav-btn-icon {
    height: 18px;
  }

  .loading-icon {
    animation: spin 1s linear infinite;
  }
}

.hide-text {
  display: none;
}

@media (min-width: 769px) {
  .hide-text {
    display: inline;
  }
}

/* AgentState 按钮有内容时的样式 */
.agent-nav-btn.agent-state-btn.has-content:hover:not(.is-disabled) {
  color: var(--main-700);
  background-color: var(--main-20);
}

.agent-nav-btn.agent-state-btn.active {
  color: var(--main-700);
  background-color: var(--main-20);
}
</style>
