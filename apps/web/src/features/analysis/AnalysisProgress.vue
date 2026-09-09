<template>
  <section class="page" data-testid="analysis-page">
    <h1>分析任务</h1>
    <p class="muted">项目:{{ projectId }} · 数据批次:{{ datasetId }}</p>
    <div class="card">
      <p>状态:{{ run.status }}</p>
      <p v-if="percent !== null">进度:{{ percent }}%</p>
      <button :disabled="run.status === 'running'" @click="start">{{ run.status === 'done' ? '重新分析' : '开始分析' }}</button>
    </div>
  </section>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { mockApi } from '../../api/mock'
import type { AnalysisRun } from '../../types/domain'

const route = useRoute()
const projectId = String(route.params.p)
const datasetId = String(route.query.dataset || 'demo-1')
const saved = sessionStorage.getItem(`voicelens:run:${projectId}:${datasetId}`)
const run = ref<AnalysisRun>(saved ? (JSON.parse(saved) as AnalysisRun) : { id: `run-${datasetId}`, status: 'queued' })
const percent = computed(() =>
  run.value.total
    ? Math.round((run.value.progress ?? (run.value.status === 'done' ? run.value.total : 0)) / run.value.total * 100)
    : null,
)
async function start() {
  run.value = { id: `run-${datasetId}`, status: 'running' }
  sessionStorage.setItem(`voicelens:run:${projectId}:${datasetId}`, JSON.stringify(run.value))
  try {
    run.value = await mockApi.runAnalysis(datasetId)
    sessionStorage.setItem(`voicelens:run:${projectId}:${datasetId}`, JSON.stringify(run.value))
  } catch {
    run.value = { id: `run-${datasetId}`, status: 'error' }
    sessionStorage.setItem(`voicelens:run:${projectId}:${datasetId}`, JSON.stringify(run.value))
  }
}
</script>
