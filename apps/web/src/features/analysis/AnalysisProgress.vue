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
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { apiClient } from '../../api/client'
import type { AnalysisRun } from '../../types/domain'

const client = apiClient()

const route = useRoute()
// 路由仅参数变化时组件会被复用,projectId/datasetId 必须是响应式派生值
const projectId = computed(() => String(route.params.p))
const datasetId = computed(() => String(route.query.dataset || 'demo-1'))
const storageKey = computed(() => `voicelens:run:${projectId.value}:${datasetId.value}`)

function readRun(key: string): AnalysisRun {
  const saved = sessionStorage.getItem(key)
  if (!saved) return { id: 'pending', status: 'queued' }
  try {
    return JSON.parse(saved) as AnalysisRun
  } catch {
    // 损坏的持久化数据不阻塞页面,回到排队初始态
    return { id: 'pending', status: 'queued' }
  }
}

const run = ref<AnalysisRun>(readRun(storageKey.value))
watch([projectId, datasetId], () => {
  run.value = readRun(storageKey.value)
})

const percent = computed(() =>
  run.value.total
    ? Math.round((run.value.progress ?? (run.value.status === 'done' ? run.value.total : 0)) / run.value.total * 100)
    : null,
)
async function start() {
  run.value = { id: 'pending', status: 'running' }
  sessionStorage.setItem(storageKey.value, JSON.stringify(run.value))
  try {
    run.value = await client.runAnalysis(datasetId.value)
    sessionStorage.setItem(storageKey.value, JSON.stringify(run.value))
  } catch {
    run.value = { id: 'pending', status: 'error' }
    sessionStorage.setItem(storageKey.value, JSON.stringify(run.value))
  }
}
</script>
