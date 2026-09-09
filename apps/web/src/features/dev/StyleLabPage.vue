<template>
  <div class="vl-page">
    <PageHeader title="StyleLab" description="公共组件状态检查页。仅 development/test 注册,生产构建不含此路由。" />
    <DemoNotice source-kind="synthetic" />
    <div class="lab">
      <VlPanel title="VlButton 变体与状态">
        <div class="lab__row">
          <VlButton variant="primary">主要动作</VlButton>
          <VlButton variant="primary" loading>主要动作(加载)</VlButton>
          <VlButton variant="primary" disabled>主要动作(禁用)</VlButton>
          <VlButton variant="secondary">次要动作</VlButton>
          <VlButton variant="ghost">文本动作</VlButton>
          <VlButton variant="danger">危险操作</VlButton>
        </div>
      </VlPanel>

      <VlPanel title="MetricCard:0 / null / 失败 三分">
        <div class="lab__metrics">
          <MetricCard data-testid="metric-lab-zero" title="真实零" :value="0" scope-label="本项目·所有分析" />
          <MetricCard data-testid="metric-lab-null" title="无数据" :value="null" scope-label="所选分析与筛选" />
          <MetricCard data-testid="metric-lab-error" title="获取失败" :value="null" state="error" scope-label="所选分析与筛选" />
          <MetricCard title="有值" :value="1000" unit="条" scope-label="所选分析与筛选" href="/projects" />
        </div>
      </VlPanel>

      <VlPanel title="StatusBadge 语义对">
        <div class="lab__row">
          <StatusBadge v-for="state in ['DRAFT', 'OPEN', 'IN_PROGRESS', 'PENDING_REVIEW', 'CLOSED', 'CANCELLED']" :key="state" kind="task" :state="state" />
          <StatusBadge v-for="severity in ['NONE', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL']" :key="severity" kind="severity" :state="severity" />
          <StatusBadge kind="review" state="pending" />
          <StatusBadge kind="review" state="confirmed" />
          <StatusBadge kind="review" state="excluded" />
          <StatusBadge kind="source" state="ai" />
          <StatusBadge kind="source" state="unknown_value_for_fallback" />
        </div>
      </VlPanel>

      <VlPanel title="DemoNotice 三种来源">
        <div class="lab__row">
          <DemoNotice source-kind="synthetic" />
          <DemoNotice source-kind="precomputed" />
          <DemoNotice source-kind="real" :read-only="true" />
        </div>
      </VlPanel>

      <VlPanel title="AsyncState 状态">
        <div class="lab__row">
          <AsyncState status="loading" />
          <AsyncState status="empty" empty-message="暂无已归类主题,仍可查看风险候选与待归类反馈" />
          <AsyncState status="error" message="暂时无法获取数据" request-id="req-lab-001" />
          <AsyncState status="forbidden" message="当前角色无权查看此内容" />
          <AsyncState status="success" :stale="true" stale-at="2026-09-09 16:00:00"><p>成功内容,数据已过期标注</p></AsyncState>
        </div>
      </VlPanel>

      <VlPanel title="证据组件">
        <div class="lab__row">
          <EvidenceQuote :quote="labQuote" />
          <AiProvenanceBadge :provenance="{ origin: 'ai', needsReview: true, reviewRecord: null }" />
          <AiProvenanceBadge :provenance="{ origin: 'human', needsReview: false, reviewRecord: { reviewer: 'demo-user', reviewedAt: '2026-09-08T10:00:00+08:00' } }" />
        </div>
      </VlPanel>

      <TrendChart
        :data="labTrend"
        unit="条"
        :time-range="{ start: '2026-08-26', end: '2026-09-01' }"
        summary="StyleLab 合成趋势数据,仅用于组件状态检查。"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
// StyleLabPage — 风格规范 11.1:仅 development/test 的组件状态页;
// 必须使用业务页真正导入的组件;不增加生产接口或测试后门。
import PageHeader from '../../components/common/PageHeader.vue'
import VlPanel from '../../components/common/VlPanel.vue'
import VlButton from '../../components/common/VlButton.vue'
import MetricCard from '../../components/common/MetricCard.vue'
import StatusBadge from '../../components/common/StatusBadge.vue'
import DemoNotice from '../../components/common/DemoNotice.vue'
import AsyncState from '../../components/common/AsyncState.vue'
import EvidenceQuote from '../../components/common/EvidenceQuote.vue'
import AiProvenanceBadge from '../../components/common/AiProvenanceBadge.vue'
import TrendChart from '../../components/common/TrendChart.vue'
import type { EvidenceQuoteItem, TrendPoint } from '../../types/domain'

const labQuote: EvidenceQuoteItem = {
  feedbackId: 'fb_lab_001',
  text: '合成样本 LAB-001:配送体验整体良好,但物流信息更新不及时。',
  start: 14,
  end: 24,
  channel: '在线客服',
  occurredAt: '2026-09-01T10:00:00+08:00',
  rowIndex: 1,
}

const labTrend: TrendPoint[] = [
  { date: '08-26', value: 142 },
  { date: '08-27', value: 151 },
  { date: '08-28', value: null },
  { date: '08-29', value: 158 },
  { date: '08-30', value: 149 },
  { date: '08-31', value: 161 },
  { date: '09-01', value: 155 },
]
</script>

<style scoped>
.lab {
  display: flex;
  flex-direction: column;
  gap: var(--vl-space-4);
  margin-top: var(--vl-space-4);
}
.lab__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--vl-space-3);
}
.lab__metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--vl-space-4);
}
</style>
