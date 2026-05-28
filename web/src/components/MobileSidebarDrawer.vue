<script setup>
import { computed, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import {
  LibraryBig,
  ClipboardList,
  MessageCirclePlus
} from 'lucide-vue-next'

import { useAgentStore } from '@/stores/agent'
import { useChatThreadsStore } from '@/stores/chatThreads'
import { useInfoStore } from '@/stores/info'
import { useTaskerStore } from '@/stores/tasker'
import { useUserStore } from '@/stores/user'
import { storeToRefs } from 'pinia'
import UserInfoComponent from '@/components/UserInfoComponent.vue'
import ConversationNavSection from '@/components/ConversationNavSection.vue'

const props = defineProps({
  open: { type: Boolean, required: true }
})

const emit = defineEmits(['update:open'])

const agentStore = useAgentStore()
const chatThreadsStore = useChatThreadsStore()
const infoStore = useInfoStore()
const taskerStore = useTaskerStore()
const userStore = useUserStore()
const { activeCount: activeCountRef, isDrawerOpen } = storeToRefs(taskerStore)
const { threads, currentThreadId, hasMoreThreads, isLoadingMoreThreads } =
  storeToRefs(chatThreadsStore)

const route = useRoute()
const router = useRouter()

const isLiteMode = import.meta.env.VITE_LITE_MODE === 'true'

const organizationName = computed(() => {
  return infoStore.organization.name || infoStore.branding.name || 'Yuxi'
})

const activeTaskCount = computed(() => activeCountRef.value || 0)

const mainList = computed(() => {
  const items = [
    {
      name: '创建新对话',
      path: '/agent',
      icon: MessageCirclePlus,
      activeIcon: MessageCirclePlus,
      action: true
    }
  ]

  // if (userStore.isAdmin) {
    if (!isLiteMode) {
      items.push({
        name: '育种知识图谱',
        path: '/graph',
        activePaths: ['/graph'],
        icon: LibraryBig,
        activeIcon: LibraryBig
      })
    }
  // }

  return items
})

const isNavItemActive = (item) => {
  const activePaths = item.activePaths || [item.path]
  return activePaths.some((path) => route.path === path || route.path.startsWith(`${path}/`))
}

const handleSelectChat = (threadId) => {
  if (!threadId) return
  chatThreadsStore.setCurrentThreadId(threadId)
  router.push({ name: 'AgentCompWithThreadId', params: { thread_id: threadId } })
}

const handleDeleteChat = async (threadId) => {
  if (!threadId) return
  try {
    await chatThreadsStore.deleteThread(threadId)
    if (route.params.thread_id === threadId) {
      await router.replace({ name: 'AgentComp' })
    }
  } catch (error) {
    console.warn('删除对话失败:', error)
  }
}

const handleRenameChat = async ({ chatId, title }) => {
  try {
    await chatThreadsStore.updateThread(chatId, title)
  } catch (error) {
    console.warn('重命名对话失败:', error)
  }
}

const handleTogglePinChat = async (threadId) => {
  const thread = threads.value.find((item) => item.id === threadId)
  if (!thread) return
  try {
    await chatThreadsStore.updateThread(threadId, null, !thread.is_pinned)
    await chatThreadsStore.loadThreads()
    if (currentThreadId.value) {
      chatThreadsStore.setCurrentThreadId(currentThreadId.value)
    }
  } catch (error) {
    console.warn('更新置顶状态失败:', error)
  }
}

const close = () => {
  emit('update:open', false)
}

watch(() => route.path, () => {
  close()
})
</script>

<template>
  <a-drawer
    :open="open"
    placement="left"
    :width="320"
    :closable="true"
    :body-style="{ padding: '0px' }"
    @close="close"
  >
    <div class="drawer-sidebar-content">
      <div class="sidebar-brand">
        <router-link to="/agent" class="brand-link" @click="close">
          <span class="brand-name">{{ organizationName }}</span>
        </router-link>
      </div>
      <div class="nav">
        <RouterLink
          v-for="(item, index) in mainList"
          :key="index"
          :to="item.path"
          v-show="!item.hidden"
          class="nav-item"
          :class="{ active: !item.action && isNavItemActive(item), 'primary-action': item.action }"
          :active-class="item.action ? '' : 'active'"
          @click="close"
        >
          <component
            class="icon"
            :is="isNavItemActive(item) ? item.activeIcon : item.icon"
            size="18"
          />
          <span class="nav-text">{{ item.name }}</span>
        </RouterLink>
      </div>
      <div class="fill">
        <ConversationNavSection
          class="sidebar-conversations"
          :current-chat-id="currentThreadId"
          :chats-list="threads"
          :has-more-chats="hasMoreThreads"
          :is-loading-more="isLoadingMoreThreads"
          @select-chat="(id) => { handleSelectChat(id); close(); }"
          @delete-chat="handleDeleteChat"
          @rename-chat="handleRenameChat"
          @toggle-pin="handleTogglePinChat"
          @load-more-chats="() => chatThreadsStore.loadMoreThreads()"
        />
      </div>
      <div class="foo">
        <div class="nav-item user-info">
          <UserInfoComponent :show-role="true">
            <template v-if="userStore.isSuperAdmin" #actions>
              <a-tooltip placement="top" title="任务中心">
                <button
                  class="user-task-center"
                  :class="{ active: isDrawerOpen }"
                  type="button"
                  aria-label="任务中心"
                  @click.stop="taskerStore.openDrawer()"
                >
                  <a-badge
                    :count="activeTaskCount"
                    :overflow-count="99"
                    class="task-center-badge"
                    size="small"
                  >
                    <ClipboardList class="icon" size="16" />
                  </a-badge>
                </button>
              </a-tooltip>
            </template>
          </UserInfoComponent>
        </div>
      </div>
    </div>
  </a-drawer>
</template>

<style lang="less" scoped>

.foo .user-info :deep(.user-info-component) {
  width: 100%;
}

.drawer-sidebar-content {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 6px 8px;
  gap: 16px;
  background-color: #fafafa;

  .sidebar-brand {
    display: flex;
    align-items: center;
    height: 40px;
    justify-content: center;
  }

  .brand-link {
    display: flex;
    align-items: center;
    height: 40px;
    color: var(--gray-900);
    text-decoration: none;
    padding: 0 6px;
  }

  .brand-name {
    overflow: hidden;
    color: transparent;
    font-size: 20px;
    font-weight: 650;
    text-overflow: ellipsis;
    white-space: nowrap;
    background: linear-gradient(135deg, var(--gray-1000) 0%, var(--main-bright) 52%, var(--sub-color) 100%);
    background-clip: text;
  }

  .nav {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .nav-item {
    display: flex;
    align-items: center;
    width: 100%;
    height: 40px;
    padding: 0 10px;
    border-radius: 8px;
    color: var(--gray-700);
    font-size: 14px;
    font-weight: 600;
    text-decoration: none;
    cursor: pointer;
    transition:
      background-color 0.2s ease-in-out,
      color 0.2s ease-in-out;

    .icon {
      flex: 0 0 18px;
      width: 18px;
      height: 18px;
    }

    .nav-text {
      margin-left: 8px;
      font-weight: 500;
    }

    &:hover {
      background-color: var(--main-20);
      color: var(--main-color);
    }

    &.active {
      background-color: color-mix(in srgb, var(--main-color) 6%, var(--gray-0));
      color: var(--main-color);
    }

    &.primary-action {
      margin-bottom: 8px;
      background: linear-gradient(135deg, var(--main-color), var(--sub-color));
      color: #fff;
      box-shadow: 0 4px 15px color-mix(in srgb, var(--main-500) 40%, transparent);

      &:hover {
        opacity: 0.88;
        color: #fff;
      }
    }
  }

  .fill {
    flex: 1 1 0;
    min-height: 0;
  }

  .sidebar-conversations {
    height: 100%;
    min-height: 0;
    overflow: hidden;
  }

  .foo {
    flex-shrink: 0;
  }

  .user-info {
    padding: 0 3px;
    overflow: hidden;
  }

  .user-task-center {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    padding: 0;
    border: 1px solid transparent;
    border-radius: 6px;
    background: transparent;
    color: var(--gray-600);
    cursor: pointer;

    &:hover,
    &.active {
      background: var(--main-30);
      color: var(--main-color);
    }
  }
}
</style>
