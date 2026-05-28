<template>
  <MessageInputComponent
    ref="inputRef"
    :model-value="modelValue"
    @update:modelValue="updateValue"
    :is-loading="isLoading"
    :disabled="disabled"
    :send-button-disabled="sendButtonDisabled"
    :placeholder="placeholder"
    :mention="mention"
    @send="handleSend"
    @keydown="handleKeyDown"
  >
    <template #top>
      <div v-if="currentImage" class="input-top-stack">
        <ImagePreviewComponent
          :image-data="currentImage"
          @remove="handleImageRemoved"
          class="image-preview-wrapper"
        />
      </div>
    </template>
    <template #options-left v-if="userStore.isSuperAdmin">
      <AttachmentOptionsComponent
        v-if="supportsFileUpload"
        :disabled="disabled"
        @upload="handleAttachmentUpload"
        @upload-image="handleImageUpload"
        @upload-image-success="handleImageUploadSuccess"
      />
    </template>
    <template #actions-left>
      <div class="input-actions-left">
        <a-popover
          v-if="showTodoEntry"
          v-model:open="todoPopoverOpen"
          placement="topLeft"
          trigger="click"
          overlay-class-name="todo-popover-overlay"
        >
          <template #content>
            <div class="todo-popover-card">
              <div class="todo-popover-header">
                <div class="todo-popover-title-wrap">
                  <span class="todo-popover-title">当前任务</span>
                  <span class="todo-popover-summary"
                    >{{ completedTodoCount }}/{{ totalTodoCount }} 已完成</span
                  >
                </div>
                <span class="todo-popover-progress">{{ todoProgress }}%</span>
              </div>

              <div class="todo-progress-bar">
                <span class="todo-progress-bar-fill" :style="{ width: `${todoProgress}%` }"></span>
              </div>

              <div class="todo-popover-list">
                <div
                  v-for="(todo, index) in todos"
                  :key="`${todo.content}-${index}`"
                  class="todo-item"
                >
                  <div class="todo-item-icon" :class="todo.status || 'unknown'">
                    <CheckCircleOutlined v-if="todo.status === 'completed'" />
                    <SyncOutlined v-else-if="todo.status === 'in_progress'" spin />
                    <ClockCircleOutlined v-else-if="todo.status === 'pending'" />
                    <CloseCircleOutlined v-else-if="todo.status === 'cancelled'" />
                    <QuestionCircleOutlined v-else />
                  </div>
                  <div class="todo-item-body">
                    <span class="todo-item-text">{{ todo.content }}</span>
                    <span class="todo-item-status">{{ getTodoStatusLabel(todo.status) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </template>

          <button class="input-action-btn" @click.stop>
            <span class="todo-entry-icon" aria-hidden="true">
              <SquareCheck :size="16" />
            </span>
            <span>待办</span>
          </button>
        </a-popover>
      </div>
    </template>
    <template #actions-right>
      <div class="input-actions-right">
        <button
          v-if="hasActiveThread"
          class="input-action-btn"
          :class="{ active: isPanelOpen }"
          @click.stop="$emit('toggle-panel')"
          title="查看文件"
        >
          <FolderKanban :size="18" />
          <span>文件</span>
        </button>
        <slot name="actions-left-extra"></slot>
      </div>
    </template>
  </MessageInputComponent>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import MessageInputComponent from '@/components/MessageInputComponent.vue'
import ImagePreviewComponent from '@/components/ImagePreviewComponent.vue'
import AttachmentOptionsComponent from '@/components/AttachmentOptionsComponent.vue'
import { FolderKanban, SquareCheck } from 'lucide-vue-next'
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  QuestionCircleOutlined,
  SyncOutlined
} from '@ant-design/icons-vue'
import { useUserStore } from '@/stores/user'
const userStore = useUserStore()

const props = defineProps({
  modelValue: { type: String, default: '' },
  isLoading: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  sendButtonDisabled: { type: Boolean, default: false },
  mention: { type: Object, default: () => null },
  supportsFileUpload: { type: Boolean, default: false },
  isPanelOpen: { type: Boolean, default: false },
  hasActiveThread: { type: Boolean, default: true },
  todos: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits([
  'update:modelValue',
  'send',
  'keydown',
  'upload-attachment',
  'toggle-panel'
])

const inputRef = ref(null)
const currentImage = ref(null)
const todoPopoverOpen = ref(false)
const placeholder = '有什么问题都可以问我哦~'

const totalTodoCount = computed(() => props.todos.length)
const completedTodoCount = computed(
  () => props.todos.filter((todo) => todo?.status === 'completed').length
)
const showTodoEntry = computed(() => props.hasActiveThread && totalTodoCount.value > 0)
const todoProgress = computed(() => {
  if (!totalTodoCount.value) return 0
  return Math.round((completedTodoCount.value / totalTodoCount.value) * 100)
})

watch(showTodoEntry, (visible) => {
  if (!visible) {
    todoPopoverOpen.value = false
  }
})

const updateValue = (val) => {
  emit('update:modelValue', val)
}

const handleAttachmentUpload = (files) => {
  if (!files?.length) return
  emit('upload-attachment', files)
}

const handleImageUpload = (imageData) => {
  if (imageData && imageData.success) {
    currentImage.value = imageData
  }
}

const handleImageUploadSuccess = () => {
  if (inputRef.value) {
    inputRef.value.closeOptions()
  }
}

const handleImageRemoved = () => {
  currentImage.value = null
}

const handleSend = () => {
  emit('send', { image: currentImage.value })
  currentImage.value = null
  todoPopoverOpen.value = false
}

const handleKeyDown = (e) => {
  if (props.sendButtonDisabled) {
    return
  }

  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  } else {
    emit('keydown', e)
  }
}

defineExpose({
  focus: () => inputRef.value?.focus(),
  closeOptions: () => inputRef.value?.closeOptions()
})

const getTodoStatusLabel = (status) => {
  const labelMap = {
    completed: '已完成',
    in_progress: '进行中',
    pending: '待处理',
    cancelled: '已取消'
  }
  return labelMap[status] || '未知状态'
}
</script>

<style lang="less" scoped>
.input-actions-left {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.input-actions-right {
  display: flex;
  align-items: center;
  margin-right: 6px;
  gap: 4px;
}

.input-top-stack {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 8px;
}

/* ==================== 输入框主体：GPT 风格 ==================== */
/* 这些选择器用于穿透 MessageInputComponent 内部结构 */
:deep(.message-input),
:deep(.message-input-container),
:deep(.message-input-wrapper),
:deep(.input-container),
:deep(.chat-input),
:deep(.agent-input),
:deep(.input-area) {
  width: 100%;
  border-radius: 26px;
  border: 1px solid color-mix(in srgb, var(--main-color) 8%, var(--gray-150));

  background:
    linear-gradient(
      180deg,
      color-mix(in srgb, var(--gray-0) 97%, var(--main-color) 2%),
      color-mix(in srgb, var(--gray-0) 98%, var(--sub-color) 1.5%)
    );

  box-shadow:
    0 1px 2px rgba(0, 0, 0, 0.035),
    0 8px 24px rgba(0, 0, 0, 0.04),
    0 18px 48px color-mix(in srgb, var(--main-color) 4%, transparent);

  transition:
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    background 0.18s ease;
}

:deep(.message-input:hover),
:deep(.message-input-container:hover),
:deep(.message-input-wrapper:hover),
:deep(.input-container:hover),
:deep(.chat-input:hover),
:deep(.agent-input:hover),
:deep(.input-area:hover) {
  border-color: color-mix(in srgb, var(--main-color) 14%, var(--gray-150));

  box-shadow:
    0 1px 2px rgba(0, 0, 0, 0.035),
    0 10px 28px rgba(0, 0, 0, 0.05),
    0 22px 54px color-mix(in srgb, var(--main-color) 5%, transparent);
}

:deep(.message-input:focus-within),
:deep(.message-input-container:focus-within),
:deep(.message-input-wrapper:focus-within),
:deep(.input-container:focus-within),
:deep(.chat-input:focus-within),
:deep(.agent-input:focus-within),
:deep(.input-area:focus-within) {
  border-color: color-mix(in srgb, var(--main-color) 22%, var(--gray-150));

  background:
    linear-gradient(
      180deg,
      color-mix(in srgb, var(--gray-0) 96%, var(--main-color) 3%),
      color-mix(in srgb, var(--gray-0) 98%, var(--sub-color) 2%)
    );

  box-shadow:
    0 0 0 3px color-mix(in srgb, var(--main-color) 7%, transparent),
    0 8px 26px rgba(0, 0, 0, 0.055),
    0 22px 58px color-mix(in srgb, var(--main-color) 6%, transparent);
}

/* 输入框内部布局 */
:deep(.message-input-inner),
:deep(.input-inner),
:deep(.textarea-wrapper),
:deep(.input-content) {
  padding: 10px 12px 8px;
  border-radius: 26px;
  background: transparent;
}

/* textarea / ant-input 样式 */
:deep(textarea),
:deep(.ant-input),
:deep(textarea.ant-input),
:deep(.ant-mentions textarea),
:deep(.ant-input-affix-wrapper textarea) {
  min-height: 42px !important;
  max-height: 180px;
  padding: 6px 4px !important;

  border: none !important;
  outline: none !important;
  box-shadow: none !important;
  background: transparent !important;

  color: var(--gray-900);
  font-size: 15px;
  line-height: 1.55;
  resize: none;

  /*
    CSS 自动高度兜底：
    新版 Chrome / Edge 支持 field-sizing: content。
    更稳的方案还是在 MessageInputComponent 里使用 a-textarea auto-size。
  */
  field-sizing: content;
  overflow-y: auto;
}

:deep(textarea::placeholder),
:deep(.ant-input::placeholder),
:deep(textarea.ant-input::placeholder) {
  color: var(--gray-400);
}

/* ant 外壳去掉默认边框 */
:deep(.ant-input-affix-wrapper),
:deep(.ant-mentions),
:deep(.ant-mentions-focused),
:deep(.ant-input-affix-wrapper-focused) {
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
}

/* 底部工具栏 */
:deep(.input-actions),
:deep(.input-footer),
:deep(.message-input-footer),
:deep(.input-toolbar) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 2px 2px 0;
  background: transparent;
}

/* ==================== 操作按钮 ==================== */
:deep(.input-action-btn) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;

  min-height: 32px;
  padding: 6px 10px;
  border-radius: 999px;

  font-size: 13px;
  font-weight: 500;
  line-height: 1;
  color: var(--gray-600);

  cursor: pointer;
  user-select: none;
  background: transparent;
  border: 1px solid transparent;

  transition:
    transform 0.16s ease,
    color 0.16s ease,
    border-color 0.16s ease,
    background 0.16s ease,
    box-shadow 0.16s ease;

  &:hover {
    transform: translateY(-1px);
    color: var(--main-bright);
    border-color: color-mix(in srgb, var(--main-color) 12%, transparent);

    background: linear-gradient(
      180deg,
      color-mix(in srgb, var(--main-color) 7%, var(--gray-0)),
      color-mix(in srgb, var(--sub-color) 4%, var(--gray-0))
    );

    box-shadow:
      0 2px 8px color-mix(in srgb, var(--main-color) 5%, transparent),
      0 8px 18px color-mix(in srgb, var(--sub-color) 4%, transparent);
  }

  &:active {
    transform: translateY(0);
    color: var(--main-700);
  }

  &.active {
    color: var(--main-bright);
    border-color: color-mix(in srgb, var(--main-color) 18%, transparent);

    background: linear-gradient(
      180deg,
      color-mix(in srgb, var(--main-color) 10%, var(--gray-0)),
      color-mix(in srgb, var(--sub-color) 6%, var(--gray-0))
    );

    box-shadow:
      0 2px 8px color-mix(in srgb, var(--main-color) 6%, transparent),
      0 8px 18px color-mix(in srgb, var(--sub-color) 4%, transparent);
  }

  &.disabled {
    opacity: 0.48;
    cursor: not-allowed;
    pointer-events: none;
  }

  span {
    line-height: 1;
  }
}

/* 发送按钮兼容 */
:deep(.send-btn),
:deep(.send-button),
:deep(.message-send-btn),
:deep(.input-send-btn),
:deep(button[type='submit']) {
  width: 34px;
  height: 34px;
  min-width: 34px;
  padding: 0;
  border-radius: 999px;
  border: none;

  display: inline-flex;
  align-items: center;
  justify-content: center;

  color: var(--gray-0);
  background: linear-gradient(
    135deg,
    var(--main-color),
    color-mix(in srgb, var(--main-color) 70%, var(--sub-color))
  );

  box-shadow:
    0 4px 12px color-mix(in srgb, var(--main-color) 16%, transparent),
    0 10px 24px color-mix(in srgb, var(--sub-color) 10%, transparent);

  cursor: pointer;

  transition:
    transform 0.16s ease,
    opacity 0.16s ease,
    box-shadow 0.16s ease,
    background 0.16s ease;

  &:hover:not(:disabled) {
    transform: translateY(-1px);
    opacity: 0.95;

    box-shadow:
      0 6px 16px color-mix(in srgb, var(--main-color) 20%, transparent),
      0 14px 30px color-mix(in srgb, var(--sub-color) 12%, transparent);
  }

  &:active:not(:disabled) {
    transform: translateY(0);
  }

  &:disabled {
    cursor: not-allowed;
    opacity: 0.45;
    background: var(--gray-300);
    box-shadow: none;
  }
}

/* ==================== Todo Popover ==================== */
.todo-entry-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: currentColor;
}

.todo-popover-card {
  width: min(320px, calc(100vw - 32px));
  padding: 14px;

  background:
    linear-gradient(
      180deg,
      color-mix(in srgb, var(--gray-0) 94%, var(--main-color) 3%),
      color-mix(in srgb, var(--gray-0) 97%, var(--sub-color) 2%)
    );
}

.todo-popover-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.todo-popover-title-wrap {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.todo-popover-title {
  font-size: 14px;
  font-weight: 650;
  color: var(--gray-900);
}

.todo-popover-summary {
  font-size: 12px;
  color: var(--gray-500);
}

.todo-popover-progress {
  font-size: 18px;
  line-height: 1;
  font-weight: 750;
  color: var(--main-700);
}

.todo-progress-bar {
  position: relative;
  width: 100%;
  height: 6px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--main-color) 6%, var(--gray-100));
  overflow: hidden;
  margin-bottom: 12px;
}

.todo-progress-bar-fill {
  display: block;
  height: 100%;
  border-radius: inherit;

  background: linear-gradient(
    90deg,
    var(--main-color) 0%,
    color-mix(in srgb, var(--main-color) 55%, var(--sub-color)) 100%
  );
}

.todo-popover-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 260px;
  overflow: auto;
  padding-right: 2px;
}

.todo-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 8px;
  border-radius: 10px;

  background: color-mix(in srgb, var(--gray-0) 92%, var(--main-color) 2%);
  border: 1px solid color-mix(in srgb, var(--main-color) 6%, var(--gray-100));
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
}

.todo-item-icon {
  width: 24px;
  height: 24px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: var(--gray-100);
  color: var(--gray-500);

  &.completed {
    background: var(--color-success-10);
    color: var(--color-success-700);
  }

  &.in_progress {
    background: var(--color-info-10);
    color: var(--color-info-700);
  }

  &.pending {
    background: var(--color-warning-10);
    color: var(--color-warning-700);
  }

  &.cancelled {
    background: var(--color-error-10);
    color: var(--color-error-700);
  }
}

.todo-item-body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.todo-item-text {
  font-size: 13px;
  line-height: 1.45;
  color: var(--gray-800);
  word-break: break-word;
  margin-right: 4px;
}

.todo-item-status {
  font-size: 12px;
  color: var(--gray-500);
}

:deep(.hide-text) {
  @media (max-width: 768px) {
    display: none;
  }
}

@media (max-width: 768px) {
  .input-actions-left {
    gap: 4px;
  }

  .input-actions-right {
    margin-right: 4px;
  }

  .input-top-stack {
    gap: 6px;
    margin-bottom: 8px;
  }

  :deep(.message-input),
  :deep(.message-input-container),
  :deep(.message-input-wrapper),
  :deep(.input-container),
  :deep(.chat-input),
  :deep(.agent-input),
  :deep(.input-area) {
    border-radius: 22px;
  }

  :deep(.message-input-inner),
  :deep(.input-inner),
  :deep(.textarea-wrapper),
  :deep(.input-content) {
    padding: 8px 10px 7px;
    border-radius: 22px;
  }

  :deep(textarea),
  :deep(.ant-input),
  :deep(textarea.ant-input),
  :deep(.ant-mentions textarea),
  :deep(.ant-input-affix-wrapper textarea) {
    min-height: 38px !important;
    font-size: 14px;
  }

  :deep(.input-action-btn) {
    min-height: 30px;
    padding: 5px 8px;
    font-size: 12px;
  }

  .todo-popover-card {
    width: min(320px, calc(100vw - 24px));
    padding: 12px;
  }
}
</style>

<style lang="less">
.todo-popover-overlay {
  .ant-popover-inner {
    padding: 0;
    border-radius: 16px;
    overflow: hidden;

    border: 1px solid color-mix(in srgb, var(--main-color) 8%, var(--gray-150));
    box-shadow:
      0 8px 24px rgba(0, 0, 0, 0.08),
      0 18px 48px color-mix(in srgb, var(--main-color) 6%, transparent);
  }

  .ant-popover-arrow::before {
    background: color-mix(in srgb, var(--gray-0) 96%, var(--main-color) 2%);
  }
}
</style>