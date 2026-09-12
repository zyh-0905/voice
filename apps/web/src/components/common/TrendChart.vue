<template>
  <VlPanel :title="title" :description="summary">
    <p class="vl-trend-chart__meta">
      <span>单位:{{ unit }}</span>
      <span>时间范围:{{ timeRange.start }} 至 {{ timeRange.end }}</span>
    </p>
    <div ref="containerRef" class="vl-trend-chart__canvas" role="img" :aria-label="`${title},${summary}`" />
    <div class="vl-trend-chart__toggle">
      <VlButton
        variant="ghost"
        size="small"
        data-testid="chart-data-toggle"
        :aria-expanded="showTable"
        aria-controls="vl-chart-data-table"
        @click="showTable = !showTable"
      >
        {{ showTable ? '收起数据表' : '查看数据表' }}
      </VlButton>
    </div>
    <div v-show="showTable" id="vl-chart-data-table" class="vl-table-scroll">
      <table class="vl-trend-chart__table" data-testid="chart-data-table">
        <caption class="vl-trend-chart__caption">反馈趋势数据表 · 合成演示数据</caption>
        <thead>
          <tr>
            <th scope="col">日期</th>
            <th scope="col" class="vl-trend-chart__num">有效反馈({{ unit }})</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="point in data" :key="point.date">
            <th scope="row">{{ point.date }}</th>
            <td class="vl-trend-chart__num vl-number">{{ point.value === null ? '—' : formatCount(point.value) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </VlPanel>
</template>

<script setup lang="ts">
// TrendChart — 风格规范 6.6/11.3:折线不平滑、缺数据保持断点(connectNulls=false);
// 数值轴从 0 起;可见文字摘要、单位、时间范围与「查看数据表」入口;
// tooltip 用 richText 且不包含用户正文;aria 与 reduced-motion 由 useChart 统一处理。
import { computed, ref, watch, onMounted } from 'vue'
import type { TrendPoint } from '../../types/domain'
import { readChartTheme } from '../../lib/chart-theme'
import { useChart, type ChartOption } from '../../composables/useChart'
import VlPanel from './VlPanel.vue'
import VlButton from './VlButton.vue'

const props = withDefaults(
  defineProps<{
    data: TrendPoint[]
    unit: string
    timeRange: { start: string; end: string }
    summary: string
    title?: string
  }>(),
  { title: '反馈趋势' },
)

const showTable = ref(false)
const { containerRef, setOption } = useChart()

function formatCount(value: number): string {
  return new Intl.NumberFormat('zh-CN').format(value)
}

/** 均值与峰值只由现有数据点推导,不引入外部口径 */
const values = computed(() => props.data.map(p => p.value).filter((v): v is number => v !== null))
const average = computed(() => {
  if (!values.value.length) return null
  return Math.round(values.value.reduce((sum, v) => sum + v, 0) / values.value.length)
})
const peak = computed<{ date: string; value: number } | null>(() => {
  let best: { date: string; value: number } | null = null
  for (const point of props.data) {
    if (point.value === null) continue
    if (best === null || best.value < point.value) best = { date: point.date, value: point.value }
  }
  return best
})

function buildOption(): ChartOption {
  const theme = readChartTheme()
  const avg = average.value
  const top = peak.value
  return {
    aria: { enabled: true, description: props.summary },
    textStyle: { fontFamily: theme.fontFamily, color: theme.text },
    grid: { left: 48, right: 16, top: 24, bottom: 32 },
    tooltip: {
      trigger: 'axis',
      renderMode: 'richText',
      formatter: (params: unknown) => {
        const item = Array.isArray(params) ? params[0] : params
        if (!item || typeof item !== 'object') return ''
        const p = item as { axisValue?: unknown; value?: unknown }
        return `${String(p.axisValue ?? '')}:${p.value === null || p.value === undefined ? '—' : formatCount(Number(p.value))} ${props.unit}`
      },
    },
    xAxis: {
      type: 'category',
      data: props.data.map((point) => point.date),
      axisLine: { lineStyle: { color: theme.grid } },
      axisTick: { show: false },
      axisLabel: { color: theme.text },
    },
    yAxis: {
      type: 'value',
      min: 0,
      splitLine: { lineStyle: { color: theme.grid } },
      axisLabel: { color: theme.text },
    },
    series: [
      {
        type: 'line',
        name: props.title,
        data: props.data.map((point) => point.value),
        smooth: false,
        connectNulls: false,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { width: 2, color: theme.palette[0] },
        itemStyle: { color: theme.palette[0] },
        // 参考线(均值)与峰值标注:帮助读数,不改变坐标口径
        markLine: avg === null ? undefined : {
          silent: true,
          symbol: 'none',
          label: { formatter: `均值 ${avg}`, color: theme.text, fontSize: 11 },
          lineStyle: { type: 'dashed', color: theme.grid },
          data: [{ yAxis: avg }],
        },
        markPoint: top === null ? undefined : {
          symbolSize: 44,
          label: { formatter: String(top.value), color: theme.palette[0], fontSize: 11, fontWeight: 'bold' },
          itemStyle: { color: 'transparent', borderColor: 'transparent' },
          data: [{ name: '峰值', coord: [top.date, top.value] }],
        },
      },
    ],
  }
}

watch(
  () => props.data,
  () => setOption(buildOption()),
  { deep: true },
)
onMounted(() => setOption(buildOption()))
</script>

<style scoped>
.vl-trend-chart__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--vl-space-2) var(--vl-space-4);
  margin: 0 0 var(--vl-space-3);
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-muted);
}
.vl-trend-chart__canvas {
  height: 18.75rem; /* 300px,规范 6.6 参考 280-320px */
  width: 100%;
}
.vl-trend-chart__toggle {
  margin-top: var(--vl-space-3);
}
.vl-trend-chart__table {
  width: 100%;
  border-collapse: collapse;
  margin-top: var(--vl-space-3);
  text-align: left;
}
.vl-trend-chart__caption {
  text-align: left;
  padding-bottom: var(--vl-space-3);
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-muted);
}
.vl-trend-chart__table th,
.vl-trend-chart__table td {
  padding: var(--vl-space-3);
  border-bottom: 1px solid var(--vl-color-border);
}
.vl-trend-chart__table thead th {
  background: var(--vl-color-subtle);
  font-weight: 600;
}
.vl-trend-chart__num {
  text-align: right;
}
</style>
