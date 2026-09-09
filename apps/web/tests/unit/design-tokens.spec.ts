// design-tokens.spec.ts — 颜色值与关键对比度门禁(风格规范 12.2)。
import { readFileSync } from 'node:fs'
import { expect, test } from 'vitest'

// vitest 的 jsdom 环境下 import.meta.url 非 file scheme,按 cwd(apps/web)读取
const css = readFileSync('src/styles/tokens.css', 'utf8')
function color(token: string): string {
  const value = css.match(new RegExp(`${token}:\\s*(#[0-9a-fA-F]{6})\\s*;`))?.[1]
  if (!value) throw new Error(`Missing hex token: ${token}`)
  return value
}
function luminance(hex: string): number {
  const channels = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
  const linear = channels.map(c => c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
  return linear[0]! * 0.2126 + linear[1]! * 0.7152 + linear[2]! * 0.0722
}
function contrast(fg: string, bg: string): number {
  const a = luminance(color(fg)), b = luminance(color(bg))
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
}
const cases: [string, string, number][] = [
  ['--vl-color-text', '--vl-color-surface', 4.5],
  ['--vl-color-text-secondary', '--vl-color-surface', 4.5],
  ['--vl-color-text-muted', '--vl-color-bg', 4.5],
  ['--vl-color-surface', '--vl-color-brand', 4.5],
  ['--vl-color-surface', '--vl-color-brand-hover', 4.5],
  ['--vl-color-warning', '--vl-color-warning-bg', 4.5],
  ['--vl-color-danger', '--vl-color-danger-bg', 4.5],
  ['--vl-color-success', '--vl-color-success-bg', 4.5],
  ['--vl-color-info', '--vl-color-info-bg', 4.5],
  ['--vl-color-border-control', '--vl-color-surface', 3],
  ['--vl-color-border-control', '--vl-color-bg', 3],
]
test.each(cases)('%s on %s >= %s', (fg, bg, minimum) => {
  expect(contrast(fg, bg)).toBeGreaterThanOrEqual(minimum)
})

test('核心语义 token 与图表色全部存在', () => {
  const required = [
    '--vl-color-bg', '--vl-color-surface', '--vl-color-text', '--vl-color-brand',
    '--vl-color-brand-soft', '--vl-color-border', '--vl-color-border-control',
    '--vl-sidebar-width', '--vl-header-height', '--vl-evidence-width', '--vl-content-max',
    '--vl-text-xl', '--vl-text-metric', '--vl-radius-panel', '--vl-radius-control',
    '--vl-control-height', '--vl-control-height-touch', '--vl-control-height-compact',
  ]
  for (const token of required) {
    expect(css, `missing token ${token}`).toContain(`${token}:`)
  }
  for (let i = 1; i <= 6; i++) {
    expect(css).toContain(`--vl-chart-${i}:`)
  }
})
