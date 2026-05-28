<template>
  <section class="conversation-nav-section" :class="{ collapsed }">
    <div v-if="showHistory && !collapsed" class="history-panel">
      <div class="history-label" @click="listCollapsed = !listCollapsed">
        <span>对话历史</span>
        <ChevronDown :size="14" class="collapse-icon" :class="{ collapsed: listCollapsed }" />
      </div>
      <div v-show="!listCollapsed" class="conversation-list">
        <template v-if="sortedChats.length > 0">
          <div
            v-for="chat in sortedChats"
            :key="chat.id"
            type="button"
            class="conversation-item"
            :class="{ active: currentChatId === chat.id }"
            @click="$emit('select-chat', chat.id)"
            @click.middle="$emit('delete-chat', chat.id)"
          >
            <span class="conversation-title">{{ chat.title || '新的对话' }}</span>
            <span class="actions-mask"></span>
            <span class="conversation-actions" @click.stop>
              <a-dropdown :trigger="['click']">
                <template #overlay>
                  <a-menu>
                    <a-menu-item
                      key="pin"
                      :icon="h(chat.is_pinned ? PinOff : Pin, { size: 14 })"
                      @click.stop="$emit('toggle-pin', chat.id)"
                    >
                      {{ chat.is_pinned ? '取消置顶' : '置顶' }}
                    </a-menu-item>
                    <a-menu-item
                      key="rename"
                      :icon="h(Pencil, { size: 14 })"
                      @click.stop="renameChat(chat.id)"
                    >
                      重命名
                    </a-menu-item>
                    <a-menu-item
                      key="delete"
                      :icon="h(Trash2, { size: 14 })"
                      @click.stop="$emit('delete-chat', chat.id)"
                    >
                      删除
                    </a-menu-item>
                  </a-menu>
                </template>
                <span class="action-btn-wrapper">
                  <a-button type="text" class="more-btn">
                    <MoreVertical :size="16" />
                  </a-button>
                  <Pin v-if="chat.is_pinned" :size="14" class="pinned-indicator" />
                </span>
              </a-dropdown>
            </span>
          </div>
        </template>
        <div v-else-if="!collapsed" class="empty-list">暂无对话历史</div>
        <div v-if="hasMoreChats && !collapsed" class="load-more-wrapper">
          <a-button
            type="text"
            class="load-more-btn"
            :loading="isLoadingMore"
            @click="$emit('load-more-chats')"
          >
            {{ isLoadingMore ? '加载中...' : '加载更多' }}
          </a-button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, h, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { ChevronDown, MoreVertical, Pencil, Pin, PinOff, Trash2 } from 'lucide-vue-next'
import { parseToShanghai } from '@/utils/time'

const props = defineProps({
  currentChatId: {
    type: String,
    default: null
  },
  chatsList: {
    type: Array,
    default: () => []
  },
  hasMoreChats: {
    type: Boolean,
    default: false
  },
  isLoadingMore: {
    type: Boolean,
    default: false
  },
  collapsed: {
    type: Boolean,
    default: false
  },
  showHistory: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits([
  'select-chat',
  'delete-chat',
  'rename-chat',
  'toggle-pin',
  'load-more-chats'
])

const listCollapsed = ref(false)

const sortedChats = computed(() => {
  return [...props.chatsList].sort((a, b) => {
    if (a.is_pinned !== b.is_pinned) {
      return a.is_pinned ? -1 : 1
    }
    const dateA = parseToShanghai(b.created_at)
    const dateB = parseToShanghai(a.created_at)
    if (!dateA || !dateB) return 0
    return dateA.diff(dateB)
  })
})

const renameChat = async (chatId) => {
  const chat = props.chatsList.find((item) => item.id === chatId)
  if (!chat) return

  let newTitle = chat.title || ''
  Modal.confirm({
    title: '重命名对话',
    content: h('div', { style: { marginTop: '12px' } }, [
      h('input', {
        value: newTitle,
        style: {
          width: '100%',
          padding: '4px 8px',
          border: '1px solid var(--gray-150)',
          background: 'var(--gray-0)',
          borderRadius: '4px'
        },
        onInput: (event) => {
          newTitle = event.target.value
        }
      })
    ]),
    okText: '确认',
    cancelText: '取消',
    onOk: () => {
      if (!newTitle.trim()) {
        message.warning('标题不能为空')
        return Promise.reject()
      }
      emit('rename-chat', { chatId, title: newTitle })
    }
  })
}
</script>

<style lang="less" scoped>
.conversation-nav-section {
  display: flex;
  min-height: 0;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
  overflow: hidden;
}

.conversation-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-panel {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
}

.history-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 8px;
  color: var(--gray-500);
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  border-radius: 4px;
  transition: background-color 0.2s ease;

  &:hover {
    background: var(--main-20);
  }

  &:active {
    background: var(--main-30);
  }
}

.collapse-icon {
  transition: transform 0.2s ease;

  &.collapsed {
    transform: rotate(-90deg);
  }
}
.conversation-list {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  padding: 6px 10px; // 原来 8px 12px
  scrollbar-width: thin;
}

.conversation-item {
  position: relative;
  display: flex;
  align-items: center; // 原来 flex-start
  box-sizing: border-box; // 关键：让 min-height 包含 padding
  padding: 8px 12px; // 原来 12px 14px
  border-radius: 8px; // 原来 10px
  margin: 4px 0; // 原来 6px 0
  cursor: pointer;
  transition: all 0.2s ease;
  overflow: hidden;
  border: 1px solid var(--gray-200);
  background: var(--gray-0);
  min-height: 48px; // 原来 64px

  .conversation-title {
    flex: 1;
    font-size: 14px;
    color: var(--gray-800);
    white-space: normal;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    line-height: 1.35; // 原来 1.5
  }

  .actions-mask {
    position: absolute;
    right: 1px;
    top: 1px;
    bottom: 1px;
    border-radius: 10px;
    width: 80px;
    background: linear-gradient(to right, transparent, var(--gray-0) 30px);
    opacity: 0;
    transition: opacity 0.3s ease;
    pointer-events: none;
  }

  .conversation-actions {
    display: flex;
    align-items: center;
    position: absolute;
    right: 8px;
    top: 50%;
    transform: translateY(-50%);
    opacity: 0;
    transition: opacity 0.3s ease;
  }

  .action-btn-wrapper {
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
  }

  .more-btn {
    position: absolute;
    inset: 0;
    z-index: 1;
    display: none;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    padding: 0;
    color: var(--gray-600);
  }

  .pinned-indicator {
    color: var(--main-color);
    opacity: 0.8;
    pointer-events: none;
  }

  // 默认显示置顶图标
  &:has(.pinned-indicator) {
    .conversation-actions,
    .actions-mask {
      opacity: 1;
    }
    .actions-mask {
      background: linear-gradient(to right, transparent, var(--gray-0) 30px);
    }
  }

  &:hover:not(.active) {
    background: linear-gradient(
      90deg,
      color-mix(in srgb, var(--main-color) 12%, transparent) 0%,
      color-mix(in srgb, var(--sub-color) 12%, transparent) 100%
    );
    border-color: color-mix(in srgb, var(--main-color) 30%, transparent);

    .actions-mask {
      background: linear-gradient(to right, transparent, var(--gray-0) 50px);
      opacity: 1;
    }

    .conversation-actions {
      opacity: 1;

      .more-btn {
        display: flex;
      }

      .pinned-indicator {
        display: none;
      }
    }
  }

  &.active {
    background: linear-gradient(
      90deg,
      color-mix(in srgb, var(--main-color) 12%, transparent) 0%,
      color-mix(in srgb, var(--sub-color) 12%, transparent) 100%
    );
    border: 1px solid transparent;
    border-radius: 10px;
    box-shadow: 0 2px 8px color-mix(in srgb, var(--main-500) 12%, transparent);
    position: relative;

    &::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      border-radius: 10px;
      padding: 1px;
      background: linear-gradient(135deg, var(--main-color), var(--sub-color));
      -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
      mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
      -webkit-mask-composite: xor;
      mask-composite: exclude;
    }

    .conversation-title {
      color: var(--main-600);
      font-weight: 500;
    }

    .conversation-actions {
      opacity: 0;

      .more-btn {
        display: none;
      }
    }

    .actions-mask {
      opacity: 0;
    }

    &:hover {
      .actions-mask {
        background: linear-gradient(to right, transparent, var(--gray-0) 50px);
        opacity: 1;
      }

      .conversation-actions {
        opacity: 1;

        .more-btn {
          display: flex;
        }

        .pinned-indicator {
          display: none;
        }
      }
    }

    &:has(.pinned-indicator) {
      .conversation-actions {
        opacity: 1;
      }

      &:hover {
        .conversation-actions {
          opacity: 1;

          .more-btn {
            display: none;
          }

          .pinned-indicator {
            display: block;
          }
        }
      }
    }
  }
}

.empty-list {
  margin-top: 20px;
  color: var(--gray-500);
  font-size: 12px;
  text-align: center;
}

.load-more-wrapper {
  padding: 8px;
  text-align: center;
}

.load-more-btn {
  color: var(--main-color);
  font-size: 12px;
}
</style>
