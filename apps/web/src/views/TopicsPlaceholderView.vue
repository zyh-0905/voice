<template>
  <div class="vl-page">
    <PageHeader title="主题洞察" description="按主题核验反馈证据、CPI 与复核状态" />
    <VlPanel>
      <!-- 占位页:后续轮次替换为真实主题表(工程计划 W12) -->
      <p class="topics-placeholder__text">暂无已归类主题,仍可查看风险候选与待归类反馈</p>
    </VlPanel>
  </div>
</template>

<script setup lang="ts">
import PageHeader from '../components/common/PageHeader.vue'
import VlPanel from '../components/common/VlPanel.vue'
</script>

<style scoped>
.topics-placeholder__text {
  margin: 0;
  color: var(--vl-color-text-muted);
}
</style>
