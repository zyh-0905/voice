<template>
  <div class="vl-page vl-settings">
    <PageHeader :icon="Setting" title="设置" description="项目治理策略与运行模式;删除等危险操作置于页面底部并需二次确认。" />

    <VlPanel class="vl-settings__section" title="时间策略">
      <AsyncState :status="status" :message="error ?? undefined" empty-message="暂无项目设置。">
        <template #error>
          <p class="vl-settings__error" data-testid="settings-load-error">暂时无法获取项目设置,请稍后重试。</p>
          <VlButton variant="secondary" @click="load">重试</VlButton>
        </template>

        <template v-if="settings">
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
          <p class="vl-settings__hint" data-testid="settings-meta">
            规则版本 v{{ settings.version }} · {{ settings.model_available ? '模型可用' : '模型暂不可用' }}
          </p>
          <div class="vl-settings__actions">
            <VlButton
              variant="primary"
              data-testid="save-settings"
              :disabled="!canAct || saving"
              :loading="saving"
              @click="save"
            >
              {{ canAct ? '保存设置' : '只读成员不可修改' }}
            </VlButton>
            <p v-if="saved" class="vl-settings__success" data-testid="settings-saved">设置已保存</p>
          </div>
          <p v-if="!canAct" class="vl-settings__readonly" data-testid="settings-readonly-hint">
            当前角色为只读成员,无权保存项目设置。
          </p>
          <!-- W03:409 版本冲突保留用户选择,由用户决定何时重新加载 -->
          <div v-if="conflict" class="vl-settings__conflict" data-testid="settings-conflict" role="alert">
            <p class="vl-settings__conflict-text">{{ conflict }}</p>
            <VlButton variant="secondary" data-testid="settings-reload" @click="load">重新加载</VlButton>
          </div>
          <p v-if="saveError" class="vl-settings__error" data-testid="settings-save-error" role="alert">{{ saveError }}</p>
        </template>
      </AsyncState>
    </VlPanel>

    <VlPanel title="演示模式">
      <p class="vl-settings__hint">当前使用合成数据展示完整流程。导入真实数据后,系统会显示来源、版本和治理证据。</p>
    </VlPanel>

    <VlPanel class="vl-settings__section vl-settings__danger" title="危险操作">
      <p class="vl-settings__hint">
        删除项目数据需要管理员权限。删除会使引用这些数据的分析、主题结果、复盘与任务证据一并失效,
        操作不可撤销;执行前会先展示影响范围并要求输入项目名确认。
      </p>
      <VlButton variant="danger" data-testid="delete-data" :disabled="!canAct || previewing" :loading="previewing" @click="startDelete">
        删除项目数据
      </VlButton>
      <p v-if="!canAct" class="vl-settings__readonly" data-testid="readonly-hint">当前角色无权执行此操作。</p>
      <p v-if="deleteError" class="vl-settings__error" data-testid="delete-error" role="alert">{{ deleteError }}</p>
    </VlPanel>

    <!-- 10.4:先预览影响范围,再输入名称二次确认 -->
    <el-dialog v-model="confirmOpen" title="确认删除项目数据" width="520px" :close-on-click-modal="false" append-to-body>
      <template v-if="impact">
        <p class="vl-settings__impact-title">将清理以下内容(不可撤销):</p>
        <ul class="vl-settings__impact" data-testid="delete-impact">
          <li v-for="row in impactRows" :key="row.label">
            <span>{{ row.label }}</span><b class="vl-number">{{ row.value }}</b>
          </li>
        </ul>
        <p class="vl-settings__hint" data-testid="delete-invalidates">
          删除后旧报告不再作为有效结果保留,必须重新导入与分析。
        </p>
        <div class="vl-field vl-settings__confirm-field">
          <label for="vl-delete-confirm">请输入项目名称「{{ impact.target_name }}」以确认</label>
          <input id="vl-delete-confirm" v-model="confirmName" class="vl-settings__select" data-testid="delete-confirm-name" />
        </div>
      </template>
      <div class="vl-settings__confirm-actions">
        <VlButton variant="secondary" @click="confirmOpen = false">取消</VlButton>
        <VlButton
          variant="danger"
          :loading="deleting"
          :disabled="!impact || confirmName.trim() !== impact.target_name"
          data-testid="delete-project-confirm"
          @click="doDelete"
        >
          确认删除
        </VlButton>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
// SettingsPage — 工程计划 9.1/规范第 7 节:分组表单,危险区置底;
// W03/7.2:设置从服务端加载,保存带 expected_version,409 冲突保留本地选择并可重新加载;
// 删除影响说明与二次确认;只读成员不写入。不再使用浏览器 confirm 阻断流程。
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Setting } from '@element-plus/icons-vue'
import { ApiHttpError, apiClient, type DeletionPreview, type ProjectSettings } from '../../api/client'
import { useSessionStore } from '../../stores/session'
import PageHeader from '../../components/common/PageHeader.vue'
import VlPanel from '../../components/common/VlPanel.vue'
import VlButton from '../../components/common/VlButton.vue'
import AsyncState from '../../components/common/AsyncState.vue'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const canAct = computed(() => (session.user?.role ?? 'VIEWER') !== 'VIEWER')

const timezone = ref('Asia/Shanghai')
const window = ref('30')
const saved = ref(false)
const confirmOpen = ref(false)
const projectId = String(route.params.p)
const client = apiClient()

// 设置读取/写入状态:冲突与其它错误分开提示,保存成功后短暂展示
const status = ref<'idle' | 'loading' | 'success' | 'error'>('idle')
const error = ref('')
const settings = ref<ProjectSettings | null>(null)
const saving = ref(false)
const conflict = ref('')
const saveError = ref('')

async function load() {
  status.value = 'loading'
  conflict.value = ''
  saveError.value = ''
  try {
    const data = await client.getSettings(projectId)
    settings.value = data
    timezone.value = data.timezone
    status.value = 'success'
  } catch (err) {
    status.value = 'error'
    error.value = err instanceof Error ? err.message : String(err)
  }
}
onMounted(load)

async function save() {
  if (!canAct.value || !settings.value) return
  saving.value = true
  saved.value = false
  conflict.value = ''
  saveError.value = ''
  try {
    // expected_version 来自已加载设置:过期表示他人已修改,不做幂等键
    settings.value = await client.patchSettings(projectId, {
      expected_version: settings.value.version,
      timezone: timezone.value,
    })
    saved.value = true
    globalThis.setTimeout(() => (saved.value = false), 2000)
  } catch (err) {
    if (err instanceof ApiHttpError && err.status === 409) {
      conflict.value = '设置已被其他人修改,当前版本无法保存;可重新加载后再试(重新加载前你的选择会保留)。'
    } else if (err instanceof ApiHttpError && err.status === 403) {
      saveError.value = '当前角色无权修改项目设置。'
    } else {
      saveError.value = err instanceof Error ? err.message : '保存失败,请稍后重试'
    }
  } finally {
    saving.value = false
  }
}

const impact = ref<DeletionPreview | null>(null)
const confirmName = ref('')
const previewing = ref(false)
const deleting = ref(false)
const deleteError = ref('')

/** 影响范围逐项展示,不把不同对象合并成一个总数 */
const impactRows = computed(() => {
  const data = impact.value
  if (!data) return []
  return [
    { label: '数据批次', value: data.datasets },
    { label: '分析 run', value: data.runs },
    { label: '已发布主题', value: data.topics },
    { label: '整改任务', value: data.tasks },
    { label: '复盘记录', value: data.reviews },
    { label: '风险候选', value: data.risks },
  ]
})

async function startDelete() {
  if (!canAct.value) return
  deleteError.value = ''
  previewing.value = true
  try {
    impact.value = await client.previewDeletion(projectId, {
      target_type: 'project', target_id: projectId,
    })
    confirmName.value = ''
    confirmOpen.value = true
  } catch (err) {
    deleteError.value = err instanceof Error ? err.message : '无法获取删除影响范围'
  } finally {
    previewing.value = false
  }
}

async function doDelete() {
  if (!impact.value || confirmName.value.trim() !== impact.value.target_name) return
  deleting.value = true
  deleteError.value = ''
  try {
    // 幂等键在同一次用户意图的重试中保持不变
    await client.executeDeletion(projectId, {
      target_type: 'project', target_id: projectId, confirm_name: confirmName.value.trim(),
    }, `delete-${projectId}`)
    confirmOpen.value = false
    saved.value = false
    // 项目已清理:回到项目列表
    void router.push('/projects')
  } catch (err) {
    deleteError.value = err instanceof Error ? err.message : '删除失败,请稍后重试'
  } finally {
    deleting.value = false
  }
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
.vl-settings__conflict {
  display: flex;
  align-items: center;
  gap: var(--vl-space-3);
  margin-top: var(--vl-space-3);
  padding: var(--vl-space-2) var(--vl-space-3);
  border-radius: var(--vl-radius-sm);
  background: var(--vl-color-warning-bg);
  color: var(--vl-color-warning);
  font-size: var(--vl-text-sm);
}
.vl-settings__conflict-text {
  margin: 0;
}
.vl-settings__danger {
  border-color: var(--vl-color-danger-bg);
}
.vl-settings__readonly {
  margin: var(--vl-space-2) 0 0;
  color: var(--vl-color-text-muted);
}
.vl-settings__impact-title {
  margin: 0 0 var(--vl-space-3);
  font-size: var(--vl-text-sm);
  color: var(--vl-color-text-secondary);
}
.vl-settings__impact {
  list-style: none;
  margin: 0 0 var(--vl-space-4);
  padding: 0;
  display: grid;
  gap: var(--vl-space-2);
}
.vl-settings__impact li {
  display: flex;
  justify-content: space-between;
  border-bottom: 1px solid var(--vl-color-border);
  padding-bottom: var(--vl-space-1);
}
.vl-settings__confirm-field {
  display: block;
  margin-bottom: var(--vl-space-4);
}
.vl-settings__confirm-field label {
  display: block;
  margin-bottom: var(--vl-space-2);
  font-size: var(--vl-text-sm);
}
.vl-settings__error {
  margin: var(--vl-space-3) 0 0;
  color: var(--vl-color-danger);
}
.vl-settings__confirm-actions {
  display: flex;
  gap: var(--vl-space-3);
  justify-content: flex-end;
}
</style>
