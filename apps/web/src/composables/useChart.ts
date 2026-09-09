// composables/useChart.ts — ECharts 统一生命周期(风格规范 11.3):
// init/setOption/resize/dispose;ResizeObserver 监听容器;组件卸载即 dispose;reduced-motion 关闭动画。
import { onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { AriaComponent, GridComponent, LegendComponent, TitleComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { ComposeOption } from 'echarts/core'
import type { BarSeriesOption, LineSeriesOption } from 'echarts/charts'
import type { AriaComponentOption, GridComponentOption, LegendComponentOption, TitleComponentOption, TooltipComponentOption } from 'echarts/components'

// 按需注册清单:LineChart/BarChart + Grid(含坐标轴)/Tooltip/Legend/Title/Aria + CanvasRenderer。
// 新增图表类型或能力时必须同步在此注册,并补充测试覆盖。
echarts.use([LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent, AriaComponent, CanvasRenderer])

export type ChartOption = ComposeOption<
  | LineSeriesOption
  | BarSeriesOption
  | GridComponentOption
  | TooltipComponentOption
  | LegendComponentOption
  | TitleComponentOption
  | AriaComponentOption
>

export interface UseChartResult {
  containerRef: Ref<HTMLElement | null>
  setOption: (option: ChartOption) => void
  resize: () => void
  dispose: () => void
}

export function useChart(): UseChartResult {
  const containerRef = ref<HTMLElement | null>(null)
  let chart: echarts.ECharts | null = null
  let observer: ResizeObserver | null = null
  const reducedMotion =
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
      : false

  function ensureInit(): void {
    const el = containerRef.value
    if (!el || chart) return
    chart = echarts.init(el)
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(() => chart?.resize())
      observer.observe(el)
    }
  }

  function setOption(option: ChartOption): void {
    ensureInit()
    chart?.setOption(reducedMotion ? { animation: false, ...option } : option)
  }

  function resize(): void {
    chart?.resize()
  }

  function dispose(): void {
    observer?.disconnect()
    observer = null
    chart?.dispose()
    chart = null
  }

  onMounted(ensureInit)
  // 容器由 v-if/v-show 延迟挂载时补偿初始化
  watch(containerRef, (el) => {
    if (el) ensureInit()
  })
  onBeforeUnmount(dispose)

  return { containerRef, setOption, resize, dispose }
}
