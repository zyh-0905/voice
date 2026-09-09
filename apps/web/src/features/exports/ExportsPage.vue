<template>
  <div class="vl-page vl-exports">
    <PageHeader title="导出" description="下载经过脱敏处理的治理结果;文件不包含原始敏感值。" />

    <AsyncState
      :status="status"
      :message="error ?? undefined"
      empty-message="暂无可导出的数据"
    >
      <template #error>
        <p class="vl-exports__error">暂时无法获取导出数据,请稍后重试。</p>
        <VlButton variant="secondary" @click="reload()">重试</VlButton>
      </template>

      <VlPanel title="治理结果 CSV" :description="`${rows.length.toLocaleString()} 条记录将导出为脱敏字段。`">
        <template #actions>
          <VlButton variant="primary" data-testid="export-csv" :disabled="!rows.length" @click="download">
            导出脱敏 CSV
          </VlButton>
        </template>
        <p class="vl-exports__hint">导出文件不包含原始敏感值;后续对接后端导出端点,不再在浏览器内拼接。</p>
      </VlPanel>
    </AsyncState>
  </div>
</template>

<script setup lang="ts">
// ExportsPage — 规范第 7 节:导出脱敏结果。当前为演示数据,
// 后续接入 GET /projects/{p}/exports/redacted.csv 后端端点替代本地拼接。
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import PageHeader from '../../components/common/PageHeader.vue'
import VlPanel from '../../components/common/VlPanel.vue'
import VlButton from '../../components/common/VlButton.vue'
import AsyncState from '../../components/common/AsyncState.vue'
import { apiClient } from '../../api/client'
import type { DatasetPreview } from '../../types/domain'

const route = useRoute()
const projectId = String(route.params.p)
const client = apiClient()
const isRealMode = import.meta.env.VITE_USE_MOCK === 'false'

const status = ref<'idle' | 'loading' | 'success' | 'empty' | 'error'>('success')
const error = ref('')
const rows = ref<DatasetPreview[]>([
  { id: 'ds-1', name: '8 月第 4 周反馈批次', rows: 1248, status: 'ready', hasTime: false },
])

function reload() {
  status.value = 'success'
}

async function download() {
  if (isRealMode) {
    // 真实环境:下载后端脱敏导出文件,不在浏览器内拼接
    try {
      const blob = await client.exportRedactedCsv(projectId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${projectId}-redacted.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      status.value = 'error'
      error.value = err instanceof Error ? err.message : String(err)
    }
    return
  }
  // 演示:构造脱敏样例 CSV
  const csv = ['id,name,rows,status', ...rows.value.map(r => `${r.id},${r.name},${r.rows},${r.status}`)].join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${projectId}-redacted.csv`
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.vl-exports {
  max-width: 48rem;
}
.vl-exports__hint {
  margin: 0;
  color: var(--vl-color-text-muted);
}
.vl-exports__error {
  color: var(--vl-color-danger);
}
</style>
