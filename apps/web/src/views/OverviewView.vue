<template>
  <div>
    <h1>概览</h1>
    <p v-if="analysis" data-testid="demo-notice">演示数据 · 合成分析版本 {{ analysis.version }}</p>
    <div v-if="analysis" class="metrics">
      <article>待处理风险 <b data-testid="metric-pending-risks">3</b></article>
      <article>逾期任务 <b data-testid="metric-overdue-tasks">2</b></article>
      <article>进行中任务 <b data-testid="metric-active-tasks">8</b></article>
      <article>有效反馈 <b data-testid="metric-valid-feedback">{{ analysis.validFeedback }}</b></article>
    </div>
    <section v-if="analysis" class="panel" aria-labelledby="analysis-title">
      <h2 id="analysis-title">主题分析</h2>
      <p data-testid="analysis-summary">{{ analysis.summary }}</p>
      <p class="caption">每条合成反馈归入一个主题；占比分母为 {{ analysis.validFeedback }} 条有效反馈。</p>
      <ul class="topics" data-testid="topic-list">
        <li v-for="topic in analysis.topics" :key="topic.id">
          <div class="topic-heading"><h3>{{ topic.title }}</h3><span>{{ topic.count }} 条 · {{ percentage(topic.count) }}%</span></div>
          <div class="bar-track" aria-hidden="true"><div class="bar" :style="{ width: `${percentage(topic.count)}%` }"></div></div>
          <p>{{ topic.summary }}</p>
          <button @click="openEvidence(topic, $event)">查看「{{ topic.title }}」证据</button>
        </li>
      </ul>
      <button data-testid="chart-data-toggle" :aria-expanded="showTable" aria-controls="topic-data-table" @click="showTable = !showTable">{{ showTable ? '收起数据表' : '查看数据表' }}</button>
      <div v-show="showTable" id="topic-data-table" class="table-wrapper">
        <table data-testid="chart-data-table">
          <caption>主题分布 · 合成演示数据</caption>
          <thead><tr><th scope="col">主题</th><th scope="col">反馈数</th><th scope="col">占有效反馈</th></tr></thead>
          <tbody><tr v-for="topic in analysis.topics" :key="topic.id"><th scope="row">{{ topic.title }}</th><td>{{ topic.count }}</td><td>{{ percentage(topic.count) }}%</td></tr></tbody>
        </table>
      </div>
    </section>
    <section v-else class="panel" data-testid="analysis-empty" aria-live="polite">
      <h2>暂无分析结果</h2><p>当前项目还没有可展示的分析结果。请先导入反馈并完成分析。</p>
    </section>
    <section v-if="analysis" class="panel" data-testid="evidence-panel">
      <h2>证据与来源</h2>
      <p data-testid="ai-provenance">AI 演示分析 · 来源为合成样本，未经人工复核</p>
      <ul><li v-for="item in analysis.topics" :key="item.id"><button @click="openEvidence(item, $event)">{{ item.title }} · 查看证据</button></li></ul>
    </section>
    <aside v-if="selected" class="drawer" data-testid="evidence-drawer" role="dialog" aria-modal="true" aria-labelledby="evidence-title" @keydown.tab.prevent="closeButton?.focus()">
      <button ref="closeButton" data-testid="evidence-close" @click="close">关闭</button>
      <h3 id="evidence-title">{{ selected.title }}</h3><p>{{ selected.evidence }}</p>
      <p>来源：{{ analysis?.version }} · 合成反馈，仅用于演示</p>
    </aside>
  </div>
</template>
<script setup lang="ts">
import { computed, ref, nextTick, onBeforeUnmount, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useSessionStore } from '../stores/session'
import { useProjectStore } from '../stores/project'
import { demoAnalysis } from '../features/analysis/demoAnalysis'
const route = useRoute()
const session = useSessionStore()
const project = useProjectStore()
const analysis = computed(() => session.isDemo && (route.params.p || project.selectedProjectId) === 'demo-project' ? demoAnalysis : null)
const showTable = ref(false)
const selected = ref<{ title: string; evidence: string } | null>(null)
const closeButton = ref<HTMLButtonElement | null>(null)
let trigger: HTMLElement | null = null
const percentage = (count: number) => analysis.value ? Math.round(count / analysis.value.validFeedback * 100) : 0
function openEvidence(item: { title: string; evidence: string }, event: MouseEvent) {
  trigger = event.currentTarget as HTMLElement
  selected.value = item
}
function close() { selected.value = null; trigger?.focus() }
const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape' && selected.value) close() }
window.addEventListener('keydown', onKey)
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
watch(selected, async value => { if (value) { await nextTick(); closeButton.value?.focus() } })
watch(analysis, () => { close(); showTable.value = false })
</script>
<style scoped>
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}
.metrics article,.panel{padding:20px;background:var(--vl-surface);border:1px solid var(--vl-border);border-radius:12px}
.metrics b{display:block;font-size:28px;margin-top:8px}
.panel{margin-top:24px}.panel h2{margin:0}.caption{font-size:13px}
ul{padding:0;list-style:none}.topics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}
.topics li{padding:16px;border:1px solid var(--vl-border);border-radius:8px}
.topic-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.topic-heading h3{font-size:16px}
.bar-track{height:8px;border-radius:8px;background:var(--vl-bg);overflow:hidden}.bar{height:100%;background:var(--vl-green);transition:width .2s ease}
button{padding:10px;border:1px solid var(--vl-border);border-radius:6px;background:var(--vl-surface);color:var(--vl-text);cursor:pointer}
li button{margin-top:8px}.table-wrapper{overflow-x:auto;margin-top:16px}table{width:100%;border-collapse:collapse;text-align:left}caption{text-align:left;padding-bottom:12px}th,td{padding:12px;border-bottom:1px solid var(--vl-border)}
.drawer{position:fixed;z-index:30;right:0;top:0;height:100dvh;width:min(420px,100vw);padding:24px;overflow-y:auto;background:var(--vl-surface);box-shadow:-8px 0 28px var(--vl-color-shadow)}
@media(max-width:900px){.topics{grid-template-columns:1fr}}@media(max-width:700px){.metrics{grid-template-columns:repeat(2,1fr)}}
@media(prefers-reduced-motion:reduce){.bar{transition:none}}
</style>
