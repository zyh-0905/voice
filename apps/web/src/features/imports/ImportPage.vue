<script setup lang="ts">
import {ref} from 'vue'; import FieldMapping from './FieldMapping.vue'; import DatasetList from './DatasetList.vue'; import ImportHealth from './ImportHealth.vue';
const file=ref<File|null>(null); const step=ref(1); const busy=ref(false); const error=ref('');
function choose(e:Event){file.value=(e.target as HTMLInputElement).files?.[0]||null; error.value='';}
function upload(){if(!file.value){error.value='请选择 CSV/Excel 文件';return} busy.value=true; setTimeout(()=>{busy.value=false;step.value=2},500)}
</script>
<template><section class="page" data-testid="import-page"><h1>数据导入</h1><p class="muted">上传通话数据，完成字段映射与治理检查。演示环境使用 mock 数据。</p><div class="steps">导入文件 → 字段映射 → 治理报告</div><div v-if="step===1" class="card"><input data-testid="file-input" type="file" accept=".csv,.xlsx,.xls" @change="choose"><p v-if="file">{{file.name}}</p><button data-testid="upload-button" :disabled="busy" @click="upload">{{busy?'上传中…':'开始上传'}}</button><p v-if="error" class="error" data-testid="import-error">{{error}}</p></div><FieldMapping v-else-if="step===2" @next="step=3"/><ImportHealth v-else @done="step=1"/><DatasetList/></section></template>
