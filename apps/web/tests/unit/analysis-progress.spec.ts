import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import AnalysisProgress from '../../src/features/analysis/AnalysisProgress.vue'

// 轮询的收敛条件只能在单元层验证,这是实测出来的结论:
// E2E 的 real-api 配置带 RUN_WORKER_INLINE=1,POST 返回时作业**已经**是终态,
// 于是页面根本不会排期第一次轮询——在那里数请求数永远是 0,是一条恒真的假闸门。
// (我按这个思路写过一条,它确实"通过"了,但通过的原因是轮询压根没发生。)
//
// mock 模式同理:mock client 是内存对象,不发网络请求。
//
// 所以这一条用假定时器直接驱动页面,断言的是**轮询次数**:
// 非终态每次到点查一次,拿到终态之后不再查。

const getAnalysis = vi.fn()
const listAnalyses = vi.fn()
const runAnalysis = vi.fn()

vi.mock('../../src/api/client', () => ({
  apiClient: () => ({ getAnalysis, listAnalyses, runAnalysis }),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { p: 'demo-project' }, query: {} }),
  useRouter: () => ({ replace: vi.fn() }),
}))

// 与组件里的 POLL_INTERVAL_MS 一致
const POLL_MS = 1_500

const VlButtonStub = { template: '<button @click="$emit(\'click\')"><slot /></button>' }

function mountPage() {
  return mount(AnalysisProgress, {
    global: { stubs: { VlButton: VlButtonStub } },
  })
}

describe('分析进度页轮询', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    getAnalysis.mockReset()
    listAnalyses.mockReset()
    runAnalysis.mockReset()
    listAnalyses.mockResolvedValue([])
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('非终态持续查询,拿到终态后停止', async () => {
    runAnalysis.mockResolvedValue({ id: 'r1', status: 'queued', total: 100, progress: 0 })
    getAnalysis
      .mockResolvedValueOnce({ id: 'r1', status: 'running', total: 100, progress: 50 })
      .mockResolvedValueOnce({ id: 'r1', status: 'done', total: 100, progress: 100 })

    const wrapper = mountPage()
    await flushPromises()
    await wrapper.get('[data-testid="analysis-start"]').trigger('click')
    await flushPromises()

    // 建作业本身不算查询
    expect(getAnalysis).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(POLL_MS)
    expect(getAnalysis, '第一次轮询').toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(POLL_MS)
    expect(getAnalysis, '第二次轮询拿到终态').toHaveBeenCalledTimes(2)

    // 关键断言:终态之后无论等多久都不再查。没有它,页面会一直打后端。
    await vi.advanceTimersByTimeAsync(POLL_MS * 20)
    expect(getAnalysis, '终态后不应再查询').toHaveBeenCalledTimes(2)

    expect(wrapper.get('[data-testid="analysis-status"]').text()).toBe('已完成')
  })

  it('组件卸载后停止轮询', async () => {
    runAnalysis.mockResolvedValue({ id: 'r1', status: 'queued', total: 100, progress: 0 })
    getAnalysis.mockResolvedValue({ id: 'r1', status: 'running', total: 100, progress: 10 })

    const wrapper = mountPage()
    await flushPromises()
    await wrapper.get('[data-testid="analysis-start"]').trigger('click')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(POLL_MS)
    expect(getAnalysis).toHaveBeenCalledTimes(1)

    wrapper.unmount()
    await vi.advanceTimersByTimeAsync(POLL_MS * 20)
    expect(getAnalysis, '卸载后定时器必须清掉').toHaveBeenCalledTimes(1)
  })

  it('查询失败不伪造终态', async () => {
    runAnalysis.mockResolvedValue({ id: 'r1', status: 'queued', total: 100, progress: 0 })
    getAnalysis.mockRejectedValue(new Error('network down'))

    const wrapper = mountPage()
    await flushPromises()
    await wrapper.get('[data-testid="analysis-start"]').trigger('click')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(POLL_MS)
    await flushPromises()

    // 作业本身未必失败,只是这一问没问到——显示成「失败」是在编造终态
    expect(wrapper.get('[data-testid="analysis-status"]').text()).toBe('排队中')
    expect(wrapper.find('[data-testid="analysis-error"]').exists()).toBe(false)

    // 而且还会继续退避重试,不会就此卡死
    await vi.advanceTimersByTimeAsync(POLL_MS)
    expect(getAnalysis.mock.calls.length).toBeGreaterThan(1)
  })
})
