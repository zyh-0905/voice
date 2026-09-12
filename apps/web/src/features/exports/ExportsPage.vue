<template>
  <div class="vl-page vl-exports">
    <PageHeader :icon="Download" title="导出" description="下载经过脱敏处理的治理结果;文件不包含原始敏感值。" />

    <AsyncState
      :status="status"
      :message="error ?? undefined"
    >
      <template #empty>
        <EmptyState text="暂无可导出的数据" hint="导入数据并完成治理后即可导出脱敏结果" />
      </template>
      <template #error>
        <p class="vl-exports__error">暂时无法获取导出数据,请稍后重试。</p>
        <VlButton variant="secondary" @click="reload()">重试</VlButton>
      </template>

      <VlPanel title="治理结果 CSV" :description="`${rows.length.toLocaleString()} 条记录将导出为脱敏字段。`">
        <template #actions>
          <VlButton variant="primary" data-testid="export-csv" :disabled="!rows.length" :loading="busy" @click="download">
            导出脱敏 CSV
          </VlButton>
        </template>
        <p class="vl-exports__hint">
          导出文件不包含原始敏感值,并对以 = + - @ 开头的文本做公式注入处理;
          下载链接 24 小时后失效,删除项目后未过期的导出一并失效。
        </p>
        <dl v-if="exportInfo" class="vl-exports__meta" data-testid="export-meta">
          <dt>最近导出</dt>
          <dd>{{ exportInfo.row_count?.toLocaleString() }} 行 · 有效至 {{ exportInfo.expires_at.slice(0, 16).replace('T', ' ') }}</dd>
        </dl>
        <p v-if="error" class="vl-exports__error" data-testid="export-error" role="alert">{{ error }}</p>
      </VlPanel>
    </AsyncState>
  </div>
</template>

<script setup lang="ts">
// ExportsPage — 规范第 7 节:导出脱敏结果。当前为演示数据,
// 后续接入 GET /projects/{p}/exports/redacted.csv 后端端点替代本地拼接。
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { Download } from '@element-plus/icons-vue'
import PageHeader from '../../components/common/PageHeader.vue'
import VlPanel from '../../components/common/VlPanel.vue'
import VlButton from '../../components/common/VlButton.vue'
import AsyncState from '../../components/common/AsyncState.vue'
import EmptyState from '../../components/common/EmptyState.vue'
import { ApiHttpError, apiClient, type ExportJob } from '../../api/client'
import type { DatasetPreview } from '../../types/domain'

const route = useRoute()
const projectId = String(route.params.p)
const client = apiClient()
const isRealMode = import.meta.env.VITE_USE_MOCK === 'false'

const status = ref<'idle' | 'loading' | 'success' | 'empty' | 'error'>('success')
const busy = ref(false)
const exportInfo = ref<ExportJob | null>(null)
const error = ref('')
const rows = ref<DatasetPreview[]>([
  { id: 'ds-1', name: '8 月第 4 周反馈批次', rows: 1248, status: 'ready', hasTime: false },
])

function reload() {
  status.value = 'success'
}

async function download() {
  if (isRealMode) {
    // 10.3:先创建导出任务,再经鉴权下载;链接 24 小时失效,失败时提示重新导出
    busy.value = true
    error.value = ''
    try {
      const job = await client.createExport(projectId, { scope: 'project' }, `export-${projectId}`)
      const blob = await client.downloadExport(projectId, job.id)
      exportInfo.value = job
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${projectId}-redacted.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      if (err instanceof ApiHttpError && err.status === 410) {
        error.value = '导出已过期或失效,请重新导出'
      } else {
        error.value = err instanceof Error ? err.message : String(err)
      }
    } finally {
      busy.value = false
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
.vl-exports__meta {
  display: grid;
  grid-template-columns: 6rem 1fr;
  gap: var(--vl-space-2);
  margin: var(--vl-space-4) 0 0;
  font-size: var(--vl-text-sm);
}
.vl-exports__meta dt {
  color: var(--vl-color-text-muted);
}
.vl-exports__meta dd {
  margin: 0;
}
.vl-exports__error {
  color: var(--vl-color-danger);
}
</style>
