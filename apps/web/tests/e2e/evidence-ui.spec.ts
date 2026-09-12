import { test, expect } from './ui-fixtures'

// 证据侧栏/抽屉语义与断点切换(风格规范 UI-06, 工程计划 W12/W20)
test('桌面为 360px 非模态侧栏,窄屏切换为模态抽屉且不丢选中', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  const trigger = page.locator('[data-resource-id="refund"]').getByRole('button', { name: '查看证据' })
  await trigger.click()

  const panel = page.getByTestId('evidence-panel')
  await expect(panel).toBeVisible()
  // 非模态:无 aria-modal,无遮罩层,不锁背景
  await expect(panel).not.toHaveAttribute('aria-modal', /.*/)
  await expect(page.locator('.vl-overlay')).toHaveCount(0)
  await expect(panel).toContainText('退款进度')

  // 断点切换到 <1440:同一选中记录转入模态抽屉,不显示两份可交互证据
  await page.setViewportSize({ width: 1280, height: 720 })
  const drawer = page.getByTestId('evidence-drawer')
  await expect(drawer).toBeVisible()
  await expect(drawer).toHaveAttribute('aria-modal', 'true')
  await expect(page.getByTestId('evidence-panel')).toHaveCount(0)
  await expect(drawer).toContainText('退款进度')

  // Esc 关闭后焦点回到原触发行按钮
  await page.getByTestId('evidence-close').press('Escape')
  await expect(drawer).toBeHidden()
  await expect(trigger).toBeFocused()
})


// W22 证据源查询:引文可回溯到脱敏全文与源行,不返回原始文件
test('证据引文可查看源反馈,给出脱敏全文与源行号', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.locator('[data-resource-id="refund"]').getByRole('button', { name: '查看证据' }).click()
  const panel = page.getByTestId('evidence-panel')
  await expect(panel).toBeVisible()

  // 默认不展开源反馈,由人工按需回溯
  await expect(page.getByTestId('evidence-source')).toHaveCount(0)

  await panel.getByTestId('evidence-open-source').first().click()
  const source = page.getByTestId('evidence-source')
  await expect(source).toBeVisible()
  await expect(source).toContainText('合成样本 DEMO-002')
  await expect(source).toContainText('源行 37')
  await expect(source).toContainText('电话')
})
