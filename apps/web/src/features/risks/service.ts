import { ref } from 'vue'
import type { RiskItem } from '../../types/domain'

/** 确定性演示风险队列:critical 置顶,候选不是已确认事故 */
export function syntheticRisks(): RiskItem[] {
  return [
    { id: 'risk-critical-1', title: '支付失败率突增', rule: 'R-302 · 近24小时', severity: 'CRITICAL', reviewState: 'pending', status: 'OPEN' },
    { id: 'risk-high-1', title: '退款率异常', rule: 'R-204 · 近30天', severity: 'HIGH', reviewState: 'pending', status: 'OPEN' },
    { id: 'risk-high-2', title: '重复发送通知', rule: 'R-210 · 去重', severity: 'HIGH', reviewState: 'confirmed', status: 'IN_PROGRESS' },
    { id: 'risk-medium-1', title: '订单金额缺失', rule: 'R-101 · 完整性', severity: 'MEDIUM', reviewState: 'excluded', status: 'CLOSED' },
  ]
}

export interface RiskStatus {
  id: string
  label: string
  appearance: 'neutral' | 'info' | 'warning' | 'success' | 'danger'
}
