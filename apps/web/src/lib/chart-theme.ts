// lib/chart-theme.ts — 图表主题(风格规范 11.3 基线)。
// 从计算后的 CSS 变量读取颜色;空值报开发错误,不回落到另一套色值。
export interface ChartTheme {
  palette: string[]
  text: string
  grid: string
  fontFamily: string
}

export function readChartTheme(): ChartTheme {
  const css = getComputedStyle(document.documentElement)
  const read = (name: string): string => {
    const value = css.getPropertyValue(name).trim()
    if (!value) throw new Error(`Missing design token: ${name}`)
    return value
  }
  return {
    palette: Array.from({ length: 6 }, (_, i) => read(`--vl-chart-${i + 1}`)),
    text: read('--vl-color-text-secondary'),
    grid: read('--vl-color-border'),
    fontFamily: read('--vl-font-sans'),
  }
}
