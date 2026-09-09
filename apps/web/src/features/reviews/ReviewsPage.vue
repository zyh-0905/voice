<template>
  <main class="page">
    <header class="heading"><div><h1>复核与复盘</h1><p>围绕固定分析版本核对证据并记录人工结论 <span class="demo">演示数据</span></p></div><span class="version">分析版本 v2026.09.09-01</span></header>
    <div v-if="loading" class="state">正在加载复核材料…</div>
    <div v-else-if="error" class="state error">加载失败：{{ error }} <button @click="load">重试</button></div>
    <div v-else-if="!review" class="state">暂无可复核的分析版本</div>
    <template v-else>
      <section class="notice">复盘结果用于记录观察与后续行动。当前证据只展示关联线索，不能宣称因果关系或自动证明措施有效。</section>
      <section class="card"><h2>证据对照</h2><div class="evidence" v-for="item in review.evidence" :key="item.id"><div><b>{{ item.label }}</b><p>{{ item.detail }}</p></div><span class="tag">{{ item.source }}</span></div></section>
      <section class="card"><h2>人工确认</h2><p class="muted">请基于原始记录完成确认，确认内容将写入审计日志。</p><button class="primary" :disabled="confirmed" @click="confirmed=true">{{ confirmed ? '已确认并记录' : '确认本次复核' }}</button></section>
      <section class="card"><h2>复盘结果</h2><dl><div><dt>观察</dt><dd>{{ review.observation }}</dd></div><div><dt>后续动作</dt><dd>{{ review.next }}</dd></div></dl></section>
    </template>
  </main>
</template>
<script setup lang="ts">
import { ref } from 'vue'
const loading = ref(true); const error = ref(''); const confirmed = ref(false)
const review = ref<any>(null)
function load(){ loading.value=true; error.value=''; setTimeout(()=>{ review.value={evidence:[{id:'e1',label:'退款率上升',detail:'近 30 天退款率 8.4%，较基线高 2.1 个百分点',source:'数据集 orders.csv'},{id:'e2',label:'客服主题关联',detail:'“退款延迟”主题占比 14%，与异常窗口重叠',source:'主题分析 v1'}],observation:'异常与退款延迟主题在时间窗口上重叠，需业务负责人进一步核对。',next:'抽样复核 20 条订单并在下个版本比较指标。'}; loading.value=false },180) }
load()
</script>
<style scoped>
.page{padding:32px;max-width:1100px;margin:auto}.heading{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px}h1{margin:0;color:var(--vl-text);font-size:var(--vl-font-title)}h2{margin:0 0 14px;font-size:17px}.demo,.version,.tag{font-size:12px;color:var(--vl-muted);border:1px solid var(--vl-border);padding:4px 8px;border-radius:12px}.card{background:var(--vl-surface);border:1px solid var(--vl-border);border-radius:var(--vl-radius);padding:20px;margin-bottom:16px;box-shadow:var(--vl-shadow-sm)}.notice{padding:14px 16px;border-left:3px solid var(--vl-color-primary);background:var(--vl-color-notice-bg);color:var(--vl-text);margin-bottom:16px}.evidence{display:flex;justify-content:space-between;gap:16px;padding:14px 0;border-bottom:1px solid var(--vl-border)}.evidence:last-child{border:0}.evidence p,.muted{color:var(--vl-muted);margin:6px 0 0}.primary{background:var(--vl-color-primary);color:var(--vl-color-white);border:0;padding:10px 16px;border-radius:8px}.primary:disabled{opacity:.7}.state{text-align:center;padding:64px}.error{color:var(--vl-color-danger-strong)}dt{color:var(--vl-muted);font-size:12px}dd{margin:4px 0 14px;color:var(--vl-text)}
</style>
