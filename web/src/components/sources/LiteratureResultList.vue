<template>
  <div class="literature-result-list">
    <div v-if="results.length > 0" class="literature-results">
      <div
        v-for="(result, index) in results"
        :key="getItemKey(result, index)"
        class="literature-result-item"
      >
        <div class="result-header">
          <h5 class="result-title">
            {{ getTitle(result, index) }}
          </h5>

          <span v-if="getScore(result) !== null" class="result-score">
            相关度: {{ (getScore(result) * 100).toFixed(1) }}%
          </span>
        </div>

        <div v-if="getMeta(result)" class="result-meta">
          {{ getMeta(result) }}
        </div>

        <div v-if="getContent(result)" class="result-content">
          {{ getContent(result) }}
        </div>

        <pre v-if="!getContent(result)" class="raw-result">{{ JSON.stringify(result, null, 2) }}</pre>
      </div>
    </div>

    <div v-else class="no-results">
      <p>{{ emptyText }}</p>
    </div>
  </div>
</template>

<script setup>
defineProps({
  results: {
    type: Array,
    default: () => []
  },
  emptyText: {
    type: String,
    default: '未找到文献来源'
  }
})

const getItemKey = (item, index) => {
  if (item?.id) return item.id
  if (item?.chunk_id) return item.chunk_id
  if (item?.document_id) return `${item.document_id}-${index}`
  if (item?.doc_id) return `${item.doc_id}-${index}`
  if (item?.title) return `${item.title}-${index}`

  return `${index}`
}

const getTitle = (item, index) => {
  return (
    item?.title ||
    item?.document_title ||
    item?.doc_title ||
    item?.file_name ||
    item?.filename ||
    item?.name ||
    item?.source ||
    item?.metadata?.title ||
    item?.metadata?.document_title ||
    item?.metadata?.doc_title ||
    item?.metadata?.file_name ||
    item?.metadata?.filename ||
    item?.metadata?.source ||
    `文献来源 ${index + 1}`
  )
}

const getMeta = (item) => {
  const parts = []

  const source =
    item?.source ||
    item?.document_name ||
    item?.collection_name ||
    item?.file_name ||
    item?.filename ||
    item?.metadata?.source ||
    item?.metadata?.document_name ||
    item?.metadata?.collection_name ||
    item?.metadata?.file_name ||
    item?.metadata?.filename

  const page =
    item?.page ||
    item?.page_number ||
    item?.pageNumber ||
    item?.metadata?.page ||
    item?.metadata?.page_number ||
    item?.metadata?.pageNumber

  const chunkId =
    item?.chunk_id ||
    item?.chunkId ||
    item?.metadata?.chunk_id ||
    item?.metadata?.chunkId

  if (source) {
    parts.push(source)
  }

  if (page !== undefined && page !== null && page !== '') {
    parts.push(`第 ${page} 页`)
  }

  if (chunkId) {
    parts.push(`片段 ${chunkId}`)
  }

  return parts.join(' · ')
}

const getContent = (item) => {
  return (
    item?.content ||
    item?.text ||
    item?.chunk ||
    item?.page_content ||
    item?.pageContent ||
    item?.summary ||
    item?.abstract ||
    item?.metadata?.content ||
    item?.metadata?.text ||
    item?.metadata?.chunk ||
    item?.metadata?.page_content ||
    item?.metadata?.pageContent ||
    ''
  )
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
.literature-result-list {
  .literature-results {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .literature-result-item {
    padding: 10px;
    border: 1px solid var(--gray-150);
    border-radius: 8px;
    background: var(--gray-0);

    .result-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
      margin-bottom: 4px;

      .result-title {
        margin: 0;
        font-size: 14px;
        line-height: 1.4;
        flex: 1;
        color: var(--gray-900);
        font-weight: 500;
      }

      .result-score {
        font-size: 11px;
        color: var(--gray-600);
        background: var(--gray-50);
        padding: 0 6px;
        border-radius: 10px;
        white-space: nowrap;
      }
    }

    .result-meta {
      margin-bottom: 4px;
      font-size: 11px;
      line-height: 1.4;
      color: var(--gray-500);
    }

    .result-content {
      font-size: 12px;
      line-height: 1.5;
      color: var(--gray-700);
      overflow: hidden;
      display: -webkit-box;
      line-clamp: 3;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
    }

    .raw-result {
      margin: 6px 0 0;
      padding: 8px;
      max-height: 180px;
      overflow: auto;
      font-size: 11px;
      line-height: 1.5;
      color: var(--gray-700);
      background: var(--gray-25);
      border: 1px solid var(--gray-100);
      border-radius: 6px;
      white-space: pre-wrap;
    }
  }

  .no-results {
    text-align: center;
    color: var(--gray-500);
    padding: 12px;
    font-size: 12px;
  }
}
</style>