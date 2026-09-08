import { execFileSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { join, relative } from 'node:path'

const root = new URL('../src/', import.meta.url).pathname.replace(/^\/(\w):/, '$1:')
const files = execFileSync('rg', ['--files', root], { encoding: 'utf8' }).trim().split(/\r?\n/).filter(Boolean)
const allowed = /\.(vue|ts|css)$/i
const ignored = /(?:tokens\.css|element-theme\.css|[\\/]tests?[\\/]fixtures[\\/])/i
const color = /#[0-9a-f]{3,8}\b|\b(?:rgb|rgba|hsl|hsla)\s*\(/gi
const violations = []
for (const file of files) {
  if (!allowed.test(file) || ignored.test(file)) continue
  const text = (await import('node:fs/promises')).readFile(file, 'utf8')
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