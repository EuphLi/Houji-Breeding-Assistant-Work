<template>
  <div class="source-section">
    <div class="section-title">文献来源 ({{ normalizedSources.length }})</div>

    <WebSearchResultList
      :results="normalizedSources"
      empty-text="未找到文献来源"
    />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import WebSearchResultList from '@/components/sources/WebSearchResultList.vue'

const props = defineProps({
  sources: {
    type: Array,
    default: () => []
  }
})

const getPubMedUrl = (item) => {
  const pmid = item?.pmid || item?.PMID || item?.metadata?.pmid || item?.metadata?.PMID

  if (!pmid) {
    return ''
  }

  return `https://pubmed.ncbi.nlm.nih.gov/${pmid}/`
}

const normalizedSources = computed(() => {
  return props.sources.map((item, index) => {
    const title =
      item?.title ||
      item?.article_title ||
      item?.paper_title ||
      item?.document_title ||
      item?.name ||
      item?.metadata?.title ||
      item?.metadata?.article_title ||
      `文献来源 ${index + 1}`

    const url =
      item?.url ||
      item?.link ||
      item?.href ||
      item?.pubmed_url ||
      item?.doi_url ||
      item?.metadata?.url ||
      item?.metadata?.link ||
      item?.metadata?.pubmed_url ||
      getPubMedUrl(item)

    const content =
      item?.content ||
      item?.abstract ||
      item?.summary ||
      item?.snippet ||
      item?.text ||
      item?.description ||
      item?.metadata?.content ||
      item?.metadata?.abstract ||
      item?.metadata?.summary ||
      item?.metadata?.snippet ||
      ''

    const score =
      typeof item?.score === 'number'
        ? item.score
        : typeof item?.similarity === 'number'
          ? item.similarity
          : typeof item?.relevance_score === 'number'
            ? item.relevance_score
            : typeof item?.metadata?.score === 'number'
              ? item.metadata.score
              : undefined

    return {
      ...item,
      title,
      url,
      content,
      score
    }
  })
})
</script>

<style scoped lang="less">
.source-section {
  .section-title {
    font-size: 12px;
    color: var(--gray-700);
    margin-bottom: 8px;
    font-weight: 600;
  }
}
</style>