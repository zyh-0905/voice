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

// —— v1.2 玻璃材质:半透明表面叠加在最差底色上后,文字仍需达标 ——
// 规范 3.1 备注「透明度…变化后须重新测试」;纯色对测试无法覆盖,故单列。
function rgba(token: string): { r: number; g: number; b: number; a: number } {
  const m = css.match(new RegExp(`${token}:\\s*rgba\\(([^)]+)\\)`))?.[1]
  if (!m) throw new Error(`Missing rgba token: ${token}`)
  const [r, g, b, a] = m.split(',').map(part => Number(part.trim()))
  return { r: r!, g: g!, b: b!, a: a! }
}
function hexToRgb(hex: string) {
  return { r: parseInt(hex.slice(1, 3), 16), g: parseInt(hex.slice(3, 5), 16), b: parseInt(hex.slice(5, 7), 16), a: 1 }
}
/** 把半透明表面叠加在不透明底色上,得到实际呈现的等效色 */
function composite(overlay: { r: number; g: number; b: number; a: number }, base: { r: number; g: number; b: number }) {
  const mix = (o: number, b: number) => Math.round(overlay.a * o + (1 - overlay.a) * b)
  return {
    r: mix(overlay.r, base.r), g: mix(overlay.g, base.g), b: mix(overlay.b, base.b),
  }
}
function luminanceRgb(c: { r: number; g: number; b: number }): number {
  const linear = [c.r, c.g, c.b].map((v) => {
    const s = v / 255
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  })
  return linear[0]! * 0.2126 + linear[1]! * 0.7152 + linear[2]! * 0.0722
}
function contrastRgb(fgHex: string, bgRgb: { r: number; g: number; b: number }): number {
  const a = luminance(color(fgHex)), b = luminanceRgb(bgRgb)
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
}

const glassSurfaces = ['--vl-glass-chrome', '--vl-glass-panel', '--vl-glass-float']
const backgroundTints = ['--vl-tint-warm', '--vl-tint-cool', '--vl-color-bg']
const textTokens = ['--vl-color-text', '--vl-color-text-secondary', '--vl-color-text-muted']
const glassCases: [string, string, string][] = glassSurfaces.flatMap(surface =>
  backgroundTints.flatMap(tint => textTokens.map(text => [surface, tint, text])),
)

test.each(glassCases)('%s over %s:文字 %s 混合后仍 >= 4.5', (surfaceToken, tintToken, textToken) => {
  const surface = rgba(surfaceToken)
  const base = hexToRgb(color(tintToken))
  expect(contrastRgb(textToken, composite(surface, base))).toBeGreaterThanOrEqual(4.5)
})

test('品牌渐变最浅一级仍满足白字 4.5:1', () => {
  // 取渐变中最浅的色标(白字承载在其上,是最差情形)
  const stops = [...css.matchAll(/--vl-gradient-brand:[^;]*?(#[0-9a-fA-F]{6})/g)].map(m => m[1]!)
  const first = css.match(/--vl-gradient-brand:\s*linear-gradient\(\s*[^,]+,\s*(#[0-9a-fA-F]{6})/)?.[1]
  if (!first) throw new Error('Missing --vl-gradient-brand light stop')
  const light = hexToRgb(first)
  const lightLum = luminanceRgb(light)
  const whiteLum = luminanceRgb({ r: 255, g: 255, b: 255 })
  const contrast = (Math.max(lightLum, whiteLum) + 0.05) / (Math.min(lightLum, whiteLum) + 0.05)
  expect(contrast).toBeGreaterThanOrEqual(4.5)
  expect(stops.length).toBeGreaterThan(0)
})

test('品牌文字压在品牌浅底/浅渐变上 >= 4.5(导航当前项与字标的真实组合)', () => {
  const ink = hexToRgb(color('--vl-color-brand-ink'))
  const soft = hexToRgb(color('--vl-color-brand-soft'))
  const softLum = luminanceRgb(soft), inkLum = luminanceRgb(ink)
  expect((Math.max(softLum, inkLum) + 0.05) / (Math.min(softLum, inkLum) + 0.05)).toBeGreaterThanOrEqual(4.5)

  // 品牌浅色渐变的最浅一级
  const lightStop = css.match(/--vl-gradient-brand-soft:\s*linear-gradient\(\s*[^,]+,\s*(#[0-9a-fA-F]{6})/)?.[1]
  if (!lightStop) throw new Error('Missing --vl-gradient-brand-soft light stop')
  const stopLum = luminanceRgb(hexToRgb(lightStop))
  expect((Math.max(stopLum, inkLum) + 0.05) / (Math.min(stopLum, inkLum) + 0.05)).toBeGreaterThanOrEqual(4.5)
})

test('实底橙不用于浅底文字(brand 与 brand-ink 分工)', () => {
  const brand = hexToRgb(color('--vl-color-brand'))
  const soft = hexToRgb(color('--vl-color-brand-soft'))
  const a = luminanceRgb(brand), b = luminanceRgb(soft)
  // 记录事实:实底橙压在品牌浅底上不足 4.5,因此文字必须用 brand-ink
  expect((Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)).toBeLessThan(4.5)
})
