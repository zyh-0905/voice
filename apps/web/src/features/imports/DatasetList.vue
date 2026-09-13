<template>
  <div class="vl-datasets" data-testid="dataset-list">
    <p v-if="loading" class="vl-datasets__state" aria-busy="true">正在读取数据批次…</p>
    <p v-else-if="error" class="vl-datasets__state vl-datasets__state--error" role="alert" data-testid="dataset-list-error">{{ error }}</p>
    <p v-else-if="!dataset" class="vl-datasets__empty">暂无数据批次,请先完成上传与治理。</p>
    <div v-else class="vl-datasets__item">
      <div>
        <p class="vl-datasets__name">{{ dataset.name }}</p>
        <p class="vl-datasets__meta">{{ dataset.rows.toLocaleString() }} 行 · {{ statusLabel }}</p>
      </div>
      <VlButton variant="primary" :disabled="!analyzable" @click="analyze">选择并分析</VlButton>
    </div>
    <p v-if="dataset && !analyzable" class="vl-datasets__hint" data-testid="dataset-not-ready">
      该批次尚未通过治理校验,请先在上一步完成校验。
    </p>
  </div>
</template>

<script setup lang="ts">
// DatasetList — 工程计划 W05 第 4 步:选择批次并分析。
//
// 这里**从服务端读取批次**,而不是从 sessionStorage。此前它读一个
// `voicelens:dataset:<project>` 键,而全仓库没有任何地方写这个键——于是这一屏永远显示
// 「暂无数据批次」,分析按钮从不出现,UI 上根本没有发起分析的路径。mock 用例只走到
// 第 3 步就停了,所以一直没被发现。
// 改走服务端还顺带满足 W05 的「刷新不丢批次」:页面重载后仍能恢复。
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { apiClient } from '../../api/client'
import type { DatasetBatch } from '../../types/domain'
import VlButton from '../../components/common/VlButton.vue'

const props = defineProps<{ projectId: string }>()
const router = useRouter()
const client = apiClient()

const loading = ref(true)
const error = ref('')
const dataset = ref<DatasetBatch | null>(null)

const statusLabel = computed(() => (dataset.value?.status === 'ready' ? '已就绪' : dataset.value?.status ?? ''))
// 只有通过治理校验的批次才能发起分析(服务端同样会以 422 dataset_not_ready 拒绝)
const analyzable = computed(() => dataset.value?.status === 'ready')

onMounted(async () => {
  try {
    const batches = await client.recentBatches(props.projectId)
    // 取**最近**一批:向导刚上传的就是它。
    // 服务端按插入顺序返回(不是倒序),直接取 [0] 会拿到项目里最早的那批——
    // 刚上传的批次反而被忽略,分析按钮因状态不是 ready 而禁用。
    dataset.value = [...batches].sort((a, b) => (b.createdAt > a.createdAt ? 1 : -1))[0] ?? null
  } catch (err) {
    error.value = err instanceof Error ? err.message : '读取数据批次失败'
  } finally {
    loading.value = false
  }
})

function analyze() {
  if (dataset.value) void router.push(`/p/${props.projectId}/analysis?dataset=${dataset.value.id}`)
}
</script>

<style scoped>
.vl-datasets__state,
.vl-datasets__empty,
.vl-datasets__hint {
  margin: 0;
  color: var(--vl-color-text-muted);
}
.vl-datasets__state--error {
  color: var(--vl-color-danger);
}
.vl-datasets__hint {
  margin-top: var(--vl-space-2);
  font-size: var(--vl-text-xs);
}
.vl-datasets__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--vl-space-4);
}
.vl-datasets__name {
  margin: 0;
  font-weight: 600;
}
.vl-datasets__meta {
  margin: var(--vl-space-1) 0 0;
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-muted);
}
</style>
