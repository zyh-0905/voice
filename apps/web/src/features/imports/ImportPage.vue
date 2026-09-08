<script setup lang="ts">
import { ref } from 'vue'; import FieldMapping from './FieldMapping.vue'; import DatasetList from './DatasetList.vue'; import ImportHealth from './ImportHealth.vue'; import { mockApi } from '../../api/mock'
const file=ref<File|null>(null), step=ref(1), busy=ref(false), error=ref('')
function choose(e:Event){ file.value=(e.target as HTMLInputElement).files?.[0]||null; error.value='' }
async function upload(){ if(!file.value){error.value='请选择文件';return}; busy.value=true; try{await mockApi.upload(file.value);step.value=2}finally{busy.value=false} }
</script>
<template><section class="page" data-testid="import-page"><h1>数据导入</h1><p>上传通话数据，完成字段映射与治理检查。</p><div v-if="step===1" class="card"><input data-testid="file-input" type="file" accept=".csv,.xlsx,.xls" @change="choose"><p v-if="file">{{file.name}}</p><button data-testid="upload-button" :disabled="busy" @click="upload">{{busy?'上传中…':'开始上传'}}</button><p v-if="error" class="error">{{error}}</p></div><FieldMapping v-else-if="step===2" @next="step=3"/><ImportHealth v-else @done="step=1"/><DatasetList/></section></template>
