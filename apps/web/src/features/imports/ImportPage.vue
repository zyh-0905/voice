<template>
  <section class="vl-page" data-testid="import-page">
    <PageHeader :icon="Upload" title="数据导入" :description="`项目:${projectId}`">
      <template #actions>
        <VlButton v-if="step !== 'upload'" variant="ghost" @click="restart">重新开始</VlButton>
      </template>
    </PageHeader>

    <ol class="vl-import-steps" aria-label="导入步骤">
      <li
        v-for="(label, key) in stepOrder"
        :key="key"
        class="vl-import-steps__item"
        :class="{ 'vl-import-steps__item--current': step === key, 'vl-import-steps__item--done': isDone(key) }"
      >
        <el-icon v-if="isDone(key)" :size="14" aria-hidden="true"><CircleCheckFilled /></el-icon>
        <span>{{ label }}</span>
      </li>
    </ol>

    <section v-if="step === 'upload'" class="vl-panel vl-import-upload">
      <h2 class="vl-import-upload__title">1 · 上传反馈文件</h2>
      <p class="vl-import-upload__hint">支持 CSV、XLSX、XLS、TXT,最大 20 MB。数据仅用于本项目的脱敏治理与分析。</p>
      <label class="vl-import-upload__drop">
        <span class="vl-import-upload__label">选择文件</span>
        <input
          data-testid="file-input"
          type="file"
          accept=".csv,.xlsx,.xls,.txt"
          @change="choose"
        />
      </label>
      <p v-if="file" class="vl-import-upload__file">{{ file.name }}</p>
      <div class="vl-import-upload__consent">
        <label class="vl-field">
          <input v-model="consent" type="checkbox" data-testid="consent-checkbox" />
          <span class="vl-import-upload__consent-text">我确认已获得这些反馈数据的授权,可用于本平台的治理与分析。</span>
        </label>
      </div>
      <p v-if="error" class="vl-import-upload__error" data-testid="import-error" role="alert">{{ error }}</p>
      <div class="vl-import-upload__actions">
        <VlButton variant="primary" :disabled="busy" :loading="busy" data-testid="upload-button" @click="upload">
          上传并解析
        </VlButton>
      </div>
    </section>

    <section v-else-if="step === 'mapping'" class="vl-panel">
      <h2 class="vl-import-upload__title">2 · 字段映射</h2>
      <FieldMapping @next="onMapped" />
    </section>

    <section v-else-if="step === 'report'" class="vl-panel">
      <h2 class="vl-import-upload__title">3 · 治理报告</h2>
      <ImportHealth :health="health" />
      <p v-if="warnings.length" class="vl-import-report__warnings" data-testid="import-warnings">
        存在 {{ warnings.length }} 项提示,可继续分析。
      </p>
      <div class="vl-import-upload__actions">
        <VlButton variant="primary" data-testid="report-next" @click="goAnalyze">选择批次并分析</VlButton>
      </div>
    </section>

    <section v-else class="vl-panel vl-import-analyze">
      <h2 class="vl-import-upload__title">4 · 选择批次并分析</h2>
      <DatasetList :project-id="projectId" />
    </section>
  </section>
</template>

<script setup lang="ts">
// ImportPage — 工程计划 W05 四步向导:上传 → 映射 → 治理报告 → 选择批次分析。
// 授权不预勾选;每步独立 loading/error;刷新从已存 step/dataset 恢复,不丢用户输入。
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { CircleCheckFilled, Upload } from '@element-plus/icons-vue'
import { ApiHttpError, fetchHttpClient } from '../../api/client'
import { mockApi } from '../../api/mock'
import PageHeader from '../../components/common/PageHeader.vue'
import VlButton from '../../components/common/VlButton.vue'
import ImportHealth from '../../components/common/ImportHealth.vue'
import FieldMapping from './FieldMapping.vue'
import DatasetList from './DatasetList.vue'
import type { DatasetPreview, ImportHealthView } from '../../types/domain'
import { useImportFlow, syntheticHealth, type ImportStep } from './service'

const route = useRoute()
const projectId = computed(() => String(route.params.p))

const client = import.meta.env.VITE_USE_MOCK !== 'false' ? mockApi : fetchHttpClient()
const { step, readStoredStep, persistStep, clearStoredStep } = useImportFlow(projectId.value)
step.value = readStoredStep()

const stepOrder: Record<ImportStep, string> = { upload: '上传', mapping: '映射', report: '治理报告', analyze: '选择分析' }
const order: ImportStep[] = ['upload', 'mapping', 'report', 'analyze']
function isDone(key: ImportStep) { return order.indexOf(key) < order.indexOf(step.value) }

const file = ref<File | null>(null)
const consent = ref(false)
const busy = ref(false)
const error = ref('')
const dataset = ref<DatasetPreview | null>(null)
const health = ref<ImportHealthView>(syntheticHealth())
const warnings = ref<string[]>([])

function choose(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0] ?? null
  error.value = ''
  if (f && !/\.(csv|xlsx|xls|txt)$/i.test(f.name)) { error.value = '仅支持 CSV、XLSX、XLS 或 TXT 文件'; return }
  if (f && f.size > 20 * 1024 * 1024) { error.value = '文件大小不能超过 20 MB'; return }
  file.value = f
}

async function upload() {
  if (!file.value) { error.value = '请选择要导入的文件'; return }
  if (!consent.value) { error.value = '请先确认数据授权'; return }
  busy.value = true
  error.value = ''
  try {
    // 必须留下返回的批次:后续的校验与治理报告都按 dataset_id 走。
    // 此前返回值被丢弃,下游只能去找一个没人写的 sessionStorage 键。
    dataset.value = await client.upload(projectId.value, file.value)
    persistStep('mapping')
  } catch (err) {
    error.value = err instanceof ApiHttpError ? (err.body?.message || err.message) : '上传失败,请稍后重试'
  } finally {
    busy.value = false
  }
}

async function onMapped() {
  // 进入治理报告前先让服务端完成校验:这既是治理报告的数字来源,也是批次转入 READY
  // 的必经步骤——未校验的批次会被 create_analysis 以 dataset_not_ready 拒绝。
  // 此前这里填的是写死的 syntheticHealth(),报告与实际文件无关,批次也永远停在 uploaded。
  if (!dataset.value) { error.value = '批次尚未上传,请返回上一步'; return }
  busy.value = true
  error.value = ''
  try {
    health.value = await client.health(projectId.value, dataset.value.id)
    warnings.value = health.value.undatedRows > 0 ? ['部分反馈缺少时间字段,趋势分析将受限'] : []
    persistStep('report')
  } catch (err) {
    error.value = err instanceof Error ? err.message : '生成治理报告失败'
  } finally {
    busy.value = false
  }
}

function goAnalyze() {
  persistStep('analyze')
}

function restart() {
  file.value = null
  consent.value = false
  error.value = ''
  clearStoredStep()
}
</script>

<style scoped>
.vl-import-steps {
  list-style: none;
  margin: 0 0 var(--vl-space-5);
  padding: 0;
  display: flex;
  gap: var(--vl-space-3);
  flex-wrap: wrap;
}
.vl-import-steps__item {
  display: inline-flex;
  align-items: center;
  gap: var(--vl-space-2);
  border: 1px solid var(--vl-color-border);
  border-radius: var(--vl-radius-control);
  background: var(--vl-glass-panel);
  color: var(--vl-color-text-muted);
  padding: var(--vl-space-2) var(--vl-space-3);
  font-size: var(--vl-text-xs);
  box-shadow: var(--vl-highlight-inset);
}
.vl-import-steps__item--current {
  border-color: var(--vl-color-brand-line);
  background: var(--vl-gradient-brand-soft);
  color: var(--vl-color-brand-ink);
  font-weight: 600;
}
.vl-import-steps__item--done {
  border-color: var(--vl-color-success-bg);
  background: var(--vl-color-success-bg);
  color: var(--vl-color-success);
}
.vl-import-upload__title {
  margin: 0 0 var(--vl-space-2);
  font-size: var(--vl-text-md);
}
.vl-import-upload__hint {
  margin: 0 0 var(--vl-space-4);
  color: var(--vl-color-text-muted);
}
.vl-import-upload__drop {
  display: block;
}
.vl-import-upload__label {
  display: block;
  font-size: var(--vl-text-sm);
  margin-bottom: var(--vl-space-2);
}
.vl-import-upload__file {
  margin: var(--vl-space-2) 0 0;
}
.vl-import-upload__consent {
  margin: var(--vl-space-4) 0;
}
.vl-field {
  display: flex;
  align-items: flex-start;
  gap: var(--vl-space-2);
}
.vl-import-upload__error {
  color: var(--vl-color-danger);
}
.vl-import-upload__actions {
  margin-top: var(--vl-space-4);
  display: flex;
  gap: var(--vl-space-3);
}
.vl-import-report__warnings {
  margin: var(--vl-space-4) 0 0;
  color: var(--vl-color-warning);
}
</style>
