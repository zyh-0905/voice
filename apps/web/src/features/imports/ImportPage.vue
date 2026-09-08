<script setup lang="ts">
import { ref } from 'vue'
import FieldMapping from './FieldMapping.vue'
import DatasetList from './DatasetList.vue'
import ImportHealth from './ImportHealth.vue'
import { mockApi } from '../../api/mock'
const file = ref<File | null>(null)
const step = ref(1)
const busy = ref(false)
const error = ref('')
function choose(event: Event) {
  const selected = (event.target as HTMLInputElement).files?.[0] ?? null
  error.value = ''
  if (selected && !/\.(csv|xlsx|xls|txt)$/i.test(selected.name)) { error.value = '仅支持 CSV、XLSX、XLS 或 TXT 文件'; file.value = null; return }
  if (selected && selected.size > 20 * 1024 * 1024) { error.value = '文件大小不能超过 20 MB'; file.value = null; return }
  file.value = selected
}
async function upload() {
  if (!file.value) { error.value = '请选择要导入的文件'; return }
  busy.value = true; error.value = ''
  try { await mockApi.upload(file.value); step.value = 2 } catch { error.value = '上传失败，请稍后重试' } finally { busy.value = false }
}
</script>
<template>
  <section class="page" data-testid="import-page">
    <h1>数据导入</h1>
    <p class="muted">上传通话数据，完成字段映射与治理检查。当前为 demo/mock 演示环境。</p>
    <div class="steps">导入文件 → 字段映射 → 治理报告</div>
    <div v-if="step === 1" class="card">
      <input data-testid="file-input" type="file" accept=".csv,.xlsx,.xls,.txt" @change="choose">
      <p v-if="file">{{ file.name }}</p>
      <button data-testid="upload-button" :disabled="busy" @click="upload">{{ busy ? '上传中…' : '开始上传' }}</button>
      <p v-if="error" class="error" data-testid="import-error">{{ error }}</p>
    </div>
    <FieldMapping v-else-if="step === 2" @next="step = 3" />
    <ImportHealth v-else @done="step = 1" />
    <DatasetList />
  </section>
</template>
