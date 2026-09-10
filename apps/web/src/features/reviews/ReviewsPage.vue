<template>
  <div class="vl-page">
    <PageHeader title="效果复盘" description="选择任务/run/revision/主题与两个时间窗口,核对统计与限制;不宣称因果。">
      <template #actions>
        <VlButton variant="primary" data-testid="create-review" @click="createReview">创建复盘</VlButton>
      </template>
    </PageHeader>

    <div v-if="reviews.length" class="vl-table-scroll">
      <table class="vl-review-table" data-testid="review-table">
        <thead>
          <tr>
            <th scope="col">复盘</th>
            <th scope="col">主题</th>
            <th scope="col">结果状态</th>
            <th scope="col"><span class="vl-sr-only">操作</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="review in reviews" :key="review.id" :data-resource-id="review.id">
            <th scope="row" class="vl-review-table__title">{{ review.title }}</th>
            <td>{{ review.topic }}</td>
            <td>
              <StatusBadge kind="review" :state="review.effectStatus" />
            </td>
            <td>
              <VlButton variant="ghost" size="small" data-testid="open-review" @click="openReview(review)">
                查看复盘
              </VlButton>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="vl-review__empty">暂无复盘记录,可点击「创建复盘」开始。</p>

    <el-dialog v-model="open" title="复盘对照" width="560px" append-to-body>
      <div v-if="current">
        <WindowCompare :before="current.before" :after="current.after" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
// ReviewsPage — 工程计划 W18:记录表 + 创建向导(演示以创建按钮示意);
// 复盘详情 Bento 对照由 WindowCompare 呈现,含黄金样例数值与可比性限制。
import { ref } from 'vue'
import PageHeader from '../../components/common/PageHeader.vue'
import VlButton from '../../components/common/VlButton.vue'
import StatusBadge from '../../components/common/StatusBadge.vue'
import WindowCompare from '../../components/common/WindowCompare.vue'

interface ReviewRow {
  id: string
  title: string
  topic: string
  effectStatus: 'pending' | 'confirmed' | 'excluded'
  before: { n: number; N: number }
  after: { n: number; N: number }
}

const reviews = ref<ReviewRow[]>([
  {
    id: 'review-1',
    title: '退款流程优化复盘',
    topic: '退款进度',
    effectStatus: 'confirmed',
    before: { n: 168, N: 1000 },
    after: { n: 102, N: 1000 },
  },
  {
    id: 'review-2',
    title: '物流文案更新复盘',
    topic: '物流体验',
    effectStatus: 'pending',
    before: { n: 80, N: 500 },
    after: { n: 100, N: 1000 },
  },
])

const open = ref(false)
const current = ref<ReviewRow | null>(null)

function openReview(review: ReviewRow) {
  current.value = review
  open.value = true
}

function createReview() {
  reviews.value.push({
    id: `review-${Date.now()}`,
    title: '新建复盘',
    topic: '待选择主题',
    effectStatus: 'pending',
    before: { n: 0, N: 0 },
    after: { n: 0, N: 0 },
  })
}
</script>

<style scoped>
.vl-review-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
}
.vl-review-table thead th {
  padding: var(--vl-space-3);
  background: var(--vl-color-subtle);
  font-size: var(--vl-text-sm);
  font-weight: 600;
}
.vl-review-table tbody th,
.vl-review-table tbody td {
  padding: var(--vl-space-3);
  border-bottom: 1px solid var(--vl-color-border);
  vertical-align: top;
}
.vl-review-table__title {
  font-weight: 600;
}
.vl-review__empty {
  color: var(--vl-color-text-muted);
}
.vl-sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>
