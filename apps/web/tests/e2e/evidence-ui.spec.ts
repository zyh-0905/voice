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
