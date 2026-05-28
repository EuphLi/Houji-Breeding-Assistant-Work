<template>
  <div class="graph-result-list">
    <div v-if="normalizedResults.length > 0" class="graph-results-wrap">
      <div class="graph-summary">
        <span>共 {{ normalizedResults.length }} 条图谱关系</span>
        <span v-if="hasMore">已显示 {{ visibleResults.length }} 条</span>
      </div>

      <div class="graph-results">
        <div
          v-for="(result, index) in visibleResults"
          :key="getItemKey(result, index)"
          class="graph-result-item"
        >
          <div class="relation-row">
            <div class="triple-chip" :title="getHead(result, index)">
              {{ getHead(result, index) }}
            </div>

            <div class="triple-chip relation-chip" :title="getRelation(result)">
              {{ getRelation(result) }}
            </div>

            <div class="triple-chip" :title="getTail(result, index)">
              {{ getTail(result, index) }}
            </div>
          </div>

          <div
            v-if="getExtraContent(result, index)"
            class="result-content"
            :title="getExtraContent(result, index)"
          >
            {{ getExtraContent(result, index) }}
          </div>

          <div v-if="getScore(result) !== null" class="result-footer">
            <span class="result-score">
              相关度 {{ (getScore(result) * 100).toFixed(1) }}%
            </span>
          </div>
        </div>
      </div>

      <button
        v-if="hasMore"
        type="button"
        class="load-more-btn"
        @click="loadMore"
      >
        展示更多 {{ nextLoadCount }} 条
      </button>
    </div>

    <div v-else class="no-results">
      <p>{{ emptyText }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  results: {
    type: Array,
    default: () => []
  },
  emptyText: {
    type: String,
    default: '未找到图谱来源'
  }
})

const INITIAL_LIMIT = 30
const LOAD_STEP = 30

const visibleLimit = ref(INITIAL_LIMIT)

const normalizedResults = computed(() => {
  return props.results.map((item, index) => {
    if (Array.isArray(item) && item.length >= 3) {
      return {
        id: `triple-${index}`,
        head: item[0],
        relation: item[1],
        tail: item[2],
        content: ''
      }
    }

    return item
  })
})

const visibleResults = computed(() => {
  return normalizedResults.value.slice(0, visibleLimit.value)
})

const hasMore = computed(() => {
  return visibleLimit.value < normalizedResults.value.length
})

const nextLoadCount = computed(() => {
  return Math.min(LOAD_STEP, normalizedResults.value.length - visibleLimit.value)
})

const loadMore = () => {
  visibleLimit.value += LOAD_STEP
}

watch(
  () => props.results,
  () => {
    visibleLimit.value = INITIAL_LIMIT
  },
  { deep: true }
)

const getItemKey = (item, index) => {
  if (item?.id) return item.id
  if (item?.edge_id) return item.edge_id
  if (item?.entity_id) return item.entity_id

  const head = getHead(item, index)
  const relation = getRelation(item)
  const tail = getTail(item, index)

  if (head && relation && tail) {
    return `${head}-${relation}-${tail}-${index}`
  }

  return `${index}`
}

const getHead = (item, index) => {
  return (
    item?.head ||
    item?.source ||
    item?.from ||
    item?.subject ||
    item?.source_entity ||
    item?.sourceEntity ||
    item?.start ||
    item?.metadata?.head ||
    item?.metadata?.source ||
    item?.metadata?.subject ||
    `实体 ${index + 1}`
  )
}

const getRelation = (item) => {
  return (
    item?.relation ||
    item?.predicate ||
    item?.type ||
    item?.relation_type ||
    item?.relationType ||
    item?.label ||
    item?.metadata?.relation ||
    item?.metadata?.predicate ||
    item?.metadata?.type ||
    '关联'
  )
}

const getTail = (item, index) => {
  return (
    item?.tail ||
    item?.target ||
    item?.to ||
    item?.object ||
    item?.target_entity ||
    item?.targetEntity ||
    item?.end ||
    item?.metadata?.tail ||
    item?.metadata?.target ||
    item?.metadata?.object ||
    `目标 ${index + 1}`
  )
}

const getRelationText = (item, index) => {
  return `${getHead(item, index)} → ${getRelation(item)} → ${getTail(item, index)}`
}

const getExtraContent = (item, index = 0) => {
  const content =
    item?.content ||
    item?.description ||
    item?.text ||
    item?.summary ||
    item?.metadata?.content ||
    item?.metadata?.description ||
    item?.properties?.description ||
    ''

  const relationText = getRelationText(item, index)

  if (!content || content === relationText) {
    return ''
  }

  return content
}

const getScore = (item) => {
  if (typeof item?.score === 'number') return item.score
  if (typeof item?.similarity === 'number') return item.similarity
  if (typeof item?.relevance_score === 'number') return item.relevance_score
  if (typeof item?.metadata?.score === 'number') return item.metadata.score

  return null
}
</script>

<style scoped lang="less">
.graph-result-list {
  .graph-results-wrap {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .graph-summary {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    font-size: 12px;
    line-height: 1.4;
    color: var(--gray-600);
    padding: 2px 0 4px;
  }

  .graph-results {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 10px;
  }

  .graph-result-item {
    padding: 12px;
    border: 1px solid var(--gray-150);
    border-radius: 10px;
    background: var(--gray-0);
    transition:
      border-color 0.15s ease,
      background-color 0.15s ease,
      box-shadow 0.15s ease;

    &:hover {
      border-color: var(--main-100);
      background: var(--gray-25);
      box-shadow: 0 4px 14px rgba(0, 0, 0, 0.04);
    }
  }

  .relation-row {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    align-items: center;
    gap: 8px;
  }

 .triple-chip {
  min-width: 0;
  width: 100%;
  height: 40px;
  padding: 0 12px;
  border-radius: 8px;
  background: var(--gray-50);
  color: var(--gray-900);
  font-size: 13px;
  line-height: 40px;
  font-weight: 550;
  text-align: center;
  box-sizing: border-box;

  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.relation-chip {
  background: var(--main-50);
  color: var(--main-700);
  border: 1px solid var(--main-100);
  font-weight: 650;
}

  .result-content {
    margin-top: 8px;
    padding: 8px 9px;
    border-radius: 8px;
    background: var(--gray-25);
    color: var(--gray-700);
    font-size: 12px;
    line-height: 1.55;
    overflow: hidden;
    display: -webkit-box;
    line-clamp: 2;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }

  .result-footer {
    margin-top: 8px;
    display: flex;
    justify-content: flex-end;
    align-items: center;
  }

  .result-score {
    font-size: 11px;
    color: var(--gray-600);
    background: var(--gray-50);
    padding: 2px 7px;
    border-radius: 999px;
    white-space: nowrap;
  }

  .load-more-btn {
    align-self: center;
    margin-top: 2px;
    padding: 7px 14px;
    border: 1px solid var(--gray-150);
    border-radius: 999px;
    background: var(--gray-0);
    color: var(--gray-700);
    font-size: 12px;
    cursor: pointer;
    transition: all 0.15s ease;

    &:hover {
      border-color: var(--main-100);
      color: var(--main-700);
      background: var(--main-50);
    }
  }

  .no-results {
    text-align: center;
    color: var(--gray-500);
    padding: 12px;
    font-size: 12px;
  }
}

@media (max-width: 720px) {
  .graph-result-list {
    .graph-results {
      grid-template-columns: 1fr;
    }

    .relation-row {
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 6px;
    }

    .triple-chip {
      height: 36px;
      padding: 0 8px;
      font-size: 12px;
      line-height: 36px;
    }
  } 
}
</style>