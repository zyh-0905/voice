// 临时:打印 axe 对比度违规节点(用完即删)
import { chromium } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

const browser = await chromium.launch()
const context = await browser.newContext({ viewport: { width: 1280, height: 720 } })
const page = await context.newPage()
await page.goto('http://localhost:4173/login')
await page.getByLabel('用户名').fill('demo')
await page.getByLabel('密码').fill('demo')
await page.getByTestId('login-submit').click()
await page.waitForURL(/overview/)
await page.waitForSelector('[data-testid="topic-table"]')

const results = await new AxeBuilder({ page }).analyze()
for (const v of results.violations.filter(v => ['serious', 'critical'].includes(v.impact ?? ''))) {
  console.log(`VIOLATION ${v.id} (${v.impact}) — ${v.nodes.length} 个节点`)
  for (const n of v.nodes.slice(0, 12)) {
    console.log('  target:', n.target.join(' '))
    const msg = (n.failureSummary ?? '').split('\n').find(l => l.includes('contrast of')) ?? ''
    console.log('   ', msg.trim().slice(0, 140))
  }
}
await browser.close()
