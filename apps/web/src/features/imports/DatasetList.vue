<template>
  <div class="vl-datasets" data-testid="dataset-list">
    <p v-if="loading" class="vl-datasets__state" aria-busy="true">正在读取数据批次…</p>
    <p v-else-if="!dataset" class="vl-datasets__empty">暂无数据批次</p>
    <div v-else class="vl-datasets__item">
      <div>
        <p class="vl-datasets__name">{{ dataset.name }}</p>
        <p class="vl-datasets__meta">{{ dataset.rows.toLocaleString() }} 行 · {{ dataset.status }}</p>
      </div>
      <VlButton variant="primary" @click="analyze">选择并分析</VlButton>
    </div>
  </div>
</template>

<script setup lang="ts">
// DatasetList — 工程计划 W05:分析批次从页面内存/dataset_id 恢复,不丢失状态。
import { computed, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import type { DatasetPreview } from '../../types/domain'
import VlButton from '../../components/common/VlButton.vue'

const props = defineProps<{ projectId: string }>()
const router = useRouter()
const loading = ref(true)
const dataset = ref<DatasetPreview | null>(null)

const storageKey = computed(() => `voicelens:dataset:${props.projectId}`)

onMounted(() => {
  const raw = sessionStorage.getItem(storageKey.value)
  if (raw) {
    try {
      dataset.value = JSON.parse(raw) as DatasetPreview
    } catch {
      dataset.value = null
    }
  }
  loading.value = false
})

function analyze() {
  if (dataset.value) void router.push(`/p/${props.projectId}/analysis?dataset=${dataset.value.id}`)
}
</script>

<style scoped>
.vl-datasets__state,
.vl-datasets__empty {
  margin: 0;
  color: var(--vl-color-text-muted);
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
