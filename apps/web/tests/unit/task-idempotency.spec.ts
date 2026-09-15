// task-idempotency.spec.ts — 幂等键的稳定性(规范 9.3):同一次用户意图的重试
// 必须共用一个键。此前键里掺了 Date.now(),每次点击都是新键,前后端的
// 幂等去重同时失效。
import { describe, expect, it } from 'vitest'

import { taskIdempotencyKey } from '../../src/lib/idempotency'

describe('taskIdempotencyKey', () => {
  it('同一意图(任务+动作+状态)两次调用得到同一个键', () => {
    const first = taskIdempotencyKey('task-003', 'task-confirm', 'DRAFT')
    const second = taskIdempotencyKey('task-003', 'task-confirm', 'DRAFT')
    expect(first).toBe(second)
  })

  it('动作或状态推进后是不同的键(新意图)', () => {
    const confirmDraft = taskIdempotencyKey('task-003', 'task-confirm', 'DRAFT')
    const startOpen = taskIdempotencyKey('task-003', 'task-start', 'OPEN')
    const startAgain = taskIdempotencyKey('task-003', 'task-confirm', 'OPEN')
    expect(new Set([confirmDraft, startOpen, startAgain]).size).toBe(3)
  })

  it('不同任务互不干扰', () => {
    expect(taskIdempotencyKey('task-a', 'task-confirm', 'DRAFT'))
      .not.toBe(taskIdempotencyKey('task-b', 'task-confirm', 'DRAFT'))
  })
})
