<template>
  <div class="vl-page vl-exports">
    <PageHeader :icon="Download" title="导出" description="下载经过脱敏处理的治理结果;文件不包含原始敏感值。" />

    <AsyncState
      :status="status"
      :message="error || undefined"
    >
      <template #empty>
        <EmptyState text="暂无可导出的数据" hint="导入数据并完成治理后即可导出脱敏结果" />
      </template>
      <template #error>
        <p class="vl-exports__error">暂时无法获取导出数据,请稍后重试。</p>
        <VlButton variant="secondary" @click="reload()">重试</VlButton>
      </template>

      <VlPanel title="治理结果 CSV" :description="`${rowCount.toLocaleString()} 条记录将导出为脱敏字段。`">
        <template #actions>
          <VlButton variant="primary" data-testid="export-csv" :disabled="!rowCount" :loading="busy" @click="download">
            导出脱敏 CSV
          </VlButton>
        </template>
        <p class="vl-exports__hint">
          导出文件不包含原始敏感值,并对以 = + - @ 开头的文本做公式注入处理;
          下载链接 24 小时后失效,删除项目后未过期的导出一并失效。
        </p>
        <dl class="vl-exports__meta" data-testid="export-meta">
          <dt>可导出记录</dt>
          <dd class="vl-number">{{ rowCount.toLocaleString() }}</dd>
          <dt>涉及批次</dt>
          <dd class="vl-number">{{ datasets.length }}</dd>
          <dt>导出列</dt>
          <dd>dataset_id、row_index、data</dd>
          <template v-if="exportInfo">
            <dt>最近导出</dt>
            <dd>{{ exportInfo.row_count?.toLocaleString() }} 行 · 有效至 {{ exportInfo.expires_at.slice(0, 16).replace('T', ' ') }}</dd>
          </template>
        </dl>
        <div v-if="datasets.length" class="vl-table-scroll vl-exports__table">
          <table class="vl-table" data-testid="export-datasets">
            <thead>
              <tr>
                <th scope="col">数据集 ID</th>
                <th scope="col" class="vl-number">可导出记录</th>
                <th scope="col">批次状态</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="batch in datasets" :key="batch.id">
                <th scope="row">{{ batch.id }}</th>
                <td class="vl-number">{{ batch.rows.toLocaleString() }}</td>
                <!-- redacted.csv 只返回 dataset_id、row_index、data;状态无从得知,不编造 -->
                <td class="vl-exports__unknown">未知</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-if="datasets.length" class="vl-exports__hint vl-exports__hint--table">
          redacted.csv 端点不返回批次名称与状态,因此本页只展示接口可核对的数据集 ID 与行数。
        </p>
        <p v-if="error" class="vl-exports__error" data-testid="export-error" role="alert">{{ error }}</p>
      </VlPanel>
    </AsyncState>
  </div>
</template>

<script setup lang="ts">
// ExportsPage — 规范第 7 节:导出脱敏结果。
// 列表数据来自 GET /projects/{p}/exports/redacted.csv(列:dataset_id、row_index、data),
// 不再用本地拼接的样例行冒充;该端点没有的字段(批次名称/状态)显示为未知或省略。
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Download } from '@element-plus/icons-vue'
import PageHeader from '../../components/common/PageHeader.vue'
import VlPanel from '../../components/common/VlPanel.vue'
import VlButton from '../../components/common/VlButton.vue'
import AsyncState from '../../components/common/AsyncState.vue'
import EmptyState from '../../components/common/EmptyState.vue'
import { ApiHttpError, apiClient, isMockMode, type ExportJob } from '../../api/client'

const route = useRoute()
const projectId = String(route.params.p)
const client = apiClient()
const isRealMode = !isMockMode()

const status = ref<'idle' | 'loading' | 'success' | 'empty' | 'error'>('idle')
const busy = ref(false)
const exportInfo = ref<ExportJob | null>(null)
const error = ref('')
const datasets = ref<Array<{ id: string; rows: number }>>([])
const rowCount = computed(() => datasets.value.reduce((sum, batch) => sum + batch.rows, 0))
/** 已加载的 CSV 文本:演示模式直接把它作为下载内容,不再另造样例 */
const csv = ref('')

/** 取 CSV 行首字段;dataset_id 由服务端生成,这里只处理引号包裹的基础形态 */
function firstCsvField(line: string): string {
  if (line.startsWith('"')) {
    const end = line.indexOf('"', 1)
    return end < 0 ? '' : line.slice(1, end).replace(/""/g, '"')
  }
  const comma = line.indexOf(',')
  return comma < 0 ? line : line.slice(0, comma)
}

/** 按数据集聚合可导出行数;表头行不计数 */
function parseRedactedCsv(text: string): Array<{ id: string; rows: number }> {
  const counts = new Map<string, number>()
  for (const line of text.split(/\r?\n/)) {
    if (!line) continue
    const id = firstCsvField(line)
    if (!id || id === 'dataset_id') continue
    counts.set(id, (counts.get(id) ?? 0) + 1)
  }
  return [...counts.entries()].map(([id, rows]) => ({ id, rows }))
}

async function load() {
  status.value = 'loading'
  error.value = ''
  try {
    csv.value = await client.redactedCsv(projectId)
    datasets.value = parseRedactedCsv(csv.value)
    status.value = datasets.value.length ? 'success' : 'empty'
  } catch (err) {
    status.value = 'error'
    error.value = err instanceof Error ? err.message : String(err)
  }
}

function reload() {
  void load()
}

onMounted(() => { void load() })

async function download() {
  busy.value = true
  error.value = ''
  try {
    let blob: Blob
    if (isRealMode) {
      // 10.3:先创建导出任务,再经鉴权下载;链接 24 小时失效,失败时提示重新导出
      const job = await client.createExport(projectId, { scope: 'project' }, `export-${projectId}`)
      blob = await client.downloadExport(projectId, job.id)
      exportInfo.value = job
    } else {
      // 演示模式不创建服务端任务:下载的就是本页加载的脱敏行
      blob = new Blob([csv.value], { type: 'text/csv;charset=utf-8' })
    }
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
.vl-exports__table {
  margin-top: var(--vl-space-4);
}
.vl-exports__hint--table {
  margin-top: var(--vl-space-3);
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
.vl-exports__unknown {
  color: var(--vl-color-text-muted);
}
.vl-exports__error {
  color: var(--vl-color-danger);
}
</style>
