<template>
  <div ref="containerRef" class="vl-sparkline" aria-hidden="true" data-testid="sparkline" />
</template>

<script setup lang="ts">
// SparklineChart — 指标卡上的迷你趋势(纯装饰:数值与结论仍以文字和数据表为准,
// 因此 aria-hidden,读屏不重复播报)。数据必须来自真实结果,不编造同比。
import { onMounted, watch } from 'vue'
import { readChartTheme } from '../../lib/chart-theme'
import { useChart, type ChartOption } from '../../composables/useChart'
import type { TrendPoint } from '../../types/domain'

const props = defineProps<{
  data: TrendPoint[]
  /** 折线颜色,默认品牌色(图表色板首色) */
  color?: string
}>()

const { containerRef, setOption } = useChart()

function buildOption(): ChartOption {
  const theme = readChartTheme()
  const values = props.data.map(point => point.value)
  return {
    animation: false,
    grid: { left: 0, right: 0, top: 4, bottom: 0 },
    xAxis: { type: 'category', show: false, boundaryGap: false, data: props.data.map(p => p.date) },
    yAxis: { type: 'value', show: false, scale: true },
    series: [{
      type: 'line',
      data: values,
      smooth: false,
      connectNulls: false,
      symbol: 'none',
      lineStyle: { width: 2, color: props.color ?? theme.palette[0] },
    }],
  }
}

onMounted(() => setOption(buildOption()))
watch(() => props.data, () => setOption(buildOption()), { deep: true })
</script>

<style scoped>
.vl-sparkline {
  width: 100%;
  height: 2.5rem;
}
</style>
