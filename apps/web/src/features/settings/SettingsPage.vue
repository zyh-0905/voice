<template>
  <div class="vl-page vl-settings">
    <PageHeader title="设置" description="项目治理策略与运行模式;删除等危险操作置于页面底部并需二次确认。" />

    <VlPanel class="vl-settings__section" title="时间策略">
      <div class="vl-field">
        <label for="vl-settings-timezone" class="vl-settings__label">默认时区</label>
        <select id="vl-settings-timezone" v-model="timezone" class="vl-settings__select">
          <option value="Asia/Shanghai">Asia/Shanghai</option>
          <option value="UTC">UTC</option>
        </select>
        <p class="vl-settings__hint">分析将按所选时区解释事件时间,修改后仅影响新建分析。</p>
      </div>
      <div class="vl-field">
        <label for="vl-settings-window" class="vl-settings__label">默认时间窗口</label>
        <select id="vl-settings-window" v-model="window" class="vl-settings__select">
          <option value="30">最近 30 天</option>
          <option value="90">最近 90 天</option>
        </select>
      </div>
      <div class="vl-settings__actions">
        <VlButton variant="primary" data-testid="save-settings" :disabled="!canAct" @click="save">
          {{ canAct ? '保存设置' : '只读成员不可修改' }}
        </VlButton>
        <p v-if="saved" class="vl-settings__success" data-testid="settings-saved">设置已保存</p>
      </div>
    </VlPanel>

    <VlPanel title="演示模式">
      <p class="vl-settings__hint">当前使用合成数据展示完整流程。导入真实数据后,系统会显示来源、版本和治理证据。</p>
    </VlPanel>

    <VlPanel class="vl-settings__section vl-settings__danger" title="危险操作">
      <p class="vl-settings__hint">
        删除项目数据需要管理员权限。此操作不可撤销,将移除全部治理、分析与复盘结果。
      </p>
      <VlButton variant="danger" data-testid="delete-data" :disabled="!canAct" @click="openDeleteConfirm">
        删除项目数据
      </VlButton>
      <p v-if="!canAct" class="vl-settings__readonly" data-testid="readonly-hint">当前角色无权执行此操作。</p>
    </VlPanel>

    <el-dialog v-model="confirmOpen" title="确认删除" width="420px" append-to-body>
      <p>确认删除该项目全部数据吗?此操作不可撤销。</p>
      <div class="vl-settings__confirm-actions">
        <VlButton variant="secondary" @click="confirmOpen = false">取消</VlButton>
        <VlButton variant="danger" data-testid="delete-project-confirm" @click="doDelete">确认删除</VlButton>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
// SettingsPage — 工程计划 9.1/规范第 7 节:分组表单,危险区置底;
// 删除影响说明与二次确认;只读成员不写入。不再使用浏览器 confirm 阻断流程。
import { computed, ref } from 'vue'
import { useSessionStore } from '../../stores/session'
import PageHeader from '../../components/common/PageHeader.vue'
import VlPanel from '../../components/common/VlPanel.vue'
import VlButton from '../../components/common/VlButton.vue'

const session = useSessionStore()
const canAct = computed(() => (session.user?.role ?? 'VIEWER') !== 'VIEWER')

const timezone = ref('Asia/Shanghai')
const window = ref('30')
const saved = ref(false)
const confirmOpen = ref(false)

function save() {
  saved.value = true
  globalThis.setTimeout(() => (saved.value = false), 2000)
}
function openDeleteConfirm() {
  if (canAct.value) confirmOpen.value = true
}

function doDelete() {
  confirmOpen.value = false
  saved.value = false
}
</script>

<style scoped>
.vl-settings {
  max-width: 48rem;
}
.vl-settings__section {
  margin-top: var(--vl-space-4);
}
.vl-settings__label {
  display: block;
  margin-bottom: var(--vl-space-1);
  font-size: var(--vl-text-sm);
}
.vl-settings__select {
  min-height: var(--vl-control-height);
  border: 1px solid var(--vl-color-border-control);
  border-radius: var(--vl-radius-control);
  padding: 0 var(--vl-space-3);
  width: 100%;
}
.vl-settings__hint {
  margin: var(--vl-space-2) 0 0;
  color: var(--vl-color-text-muted);
}
.vl-settings__actions {
  display: flex;
  align-items: center;
  gap: var(--vl-space-3);
  margin-top: var(--vl-space-4);
}
.vl-settings__success {
  margin: 0;
  color: var(--vl-color-success);
}
.vl-settings__danger {
  border-color: var(--vl-color-danger-bg);
}
.vl-settings__readonly {
  margin: var(--vl-space-2) 0 0;
  color: var(--vl-color-text-muted);
}
.vl-settings__confirm-actions {
  display: flex;
  gap: var(--vl-space-3);
  justify-content: flex-end;
}
</style>
