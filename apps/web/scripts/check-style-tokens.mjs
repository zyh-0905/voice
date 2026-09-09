// 样式门禁:业务代码禁止新增硬编码颜色(十六进制/RGB/HSL),必须使用语义设计 token。
// tokens.css 与 element-theme.css 是唯一允许出现原始色值的文件。
import { readdir, readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { join, relative } from 'node:path'

const root = fileURLToPath(new URL('../src/', import.meta.url))
const entries = await readdir(root, { recursive: true })
const allowed = /\.(vue|ts|css)$/i
const ignored = /(?:tokens\.css|element-theme\.css|[\\/]tests?[\\/]fixtures[\\/])/i
const color = /#[0-9a-f]{3,8}\b|\b(?:rgb|rgba|hsl|hsla)\s*\(/gi
const violations = []
for (const entry of entries) {
  const file = join(root, entry)
  if (!allowed.test(file) || ignored.test(file)) continue
  let text
  try {
    text = await readFile(file, 'utf8')
  } catch {
    continue // 目录或不可读文件(recursive readdir 返回目录名)
  }
  let match
  while ((match = color.exec(text))) {
    const line = text.slice(0, match.index).split('\n').length
    violations.push(`${relative(process.cwd(), file)}:${line}: ${match[0]}`)
  }
}
if (violations.length) {
  console.error('Hard-coded colors found; use semantic design tokens:')
  console.error(violations.join('\n'))
  process.exit(1)
}
console.log('Style token check passed.')
