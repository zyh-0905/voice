// lib/idempotency.ts — 任务写操作的幂等键构造(规范 9.3)

/**
 * 任务操作的幂等键:同一次用户意图的重试共用一个键。
 *
 * 意图 = (任务, 动作按钮, 当时任务状态):提交失败后重试是**同一意图** → 同键,
 * 服务端按键去重,网络层重试不会产生第二条任务事件;动作成功后状态推进 →
 * 新意图 → 自然换键。
 *
 * 不能掺 `Date.now()` 或随机数:那让每次点击都是新键,前后端两层的幂等去重
 * 同时失效(此前 TaskDetailPage 正是这样,「双击确认一次事件」只剩服务端
 * 状态机兜底)。
 */
export function taskIdempotencyKey(taskId: string, action: string, status: string): string {
  return `${taskId}-${action}-${status}`
}
