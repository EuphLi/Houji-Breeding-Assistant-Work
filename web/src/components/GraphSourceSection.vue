<template>
  <div class="source-section">
    <div class="section-title">图谱来源 ({{ sources.length }})</div>
    <GraphResultList :results="sources" empty-text="未找到图谱来源" />
  </div>
</template>

<script setup>
import GraphResultList from '@/components/sources/GraphResultList.vue'

defineProps({
  sources: {
    type: Array,
    default: () => []
  }
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