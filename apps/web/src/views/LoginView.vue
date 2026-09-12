<template>
  <div class="vl-login">
    <section class="vl-login__brand">
      <p class="vl-login__mark" aria-hidden="true"><span class="vl-login__mark-block" /></p>
      <h1 class="vl-login__title">诉源镜 <span class="vl-login__latin">VoiceLens</span></h1>
      <p class="vl-login__slogan">从分散的声音,到有依据的行动</p>
      <ul class="vl-login__pillars">
        <li v-for="pillar in pillars" :key="pillar.title" class="vl-login__pillar">
          <span class="vl-login__pillar-icon" aria-hidden="true">
            <el-icon :size="16"><component :is="pillar.icon" /></el-icon>
          </span>
          <span>
            <b>{{ pillar.title }}</b>
            <span class="vl-login__pillar-desc">{{ pillar.description }}</span>
          </span>
        </li>
      </ul>
      <p class="vl-login__usage">
        本工作台用于对已获授权的反馈数据进行脱敏治理、主题分析与人工复核。
        演示环境仅展示合成数据,不代表任何真实业务结果。
      </p>
    </section>

    <section class="vl-login__form" aria-label="登录">
      <h2 class="vl-login__heading">登录</h2>
      <form class="vl-login__fields" @submit.prevent="submit">
        <div class="vl-field">
          <label for="vl-login-username">用户名</label>
          <input
            id="vl-login-username"
            v-model="username"
            class="vl-login__input"
            type="text"
            autocomplete="username"
            placeholder="演示账号:demo"
          />
        </div>
        <div class="vl-field">
          <label for="vl-login-password">密码</label>
          <input
            id="vl-login-password"
            v-model="password"
            class="vl-login__input"
            type="password"
            autocomplete="current-password"
            placeholder="演示密码:demo"
          />
        </div>
        <p v-if="error" class="vl-login__error" role="alert" data-testid="login-error">{{ error }}</p>
        <VlButton variant="primary" type="submit" data-testid="login-submit" :loading="busy" class="vl-login__submit">
          登录
        </VlButton>
      </form>
      <p class="vl-login__divider" role="separator">或</p>
      <VlButton variant="secondary" data-testid="login-readonly" @click="enterReadonly">进入只读合成演示</VlButton>
      <p class="vl-login__hint">只读演示账号:viewer / viewer</p>
      <p v-if="ssoIssuer" class="vl-login__sso" data-testid="login-sso">
        当前由外部身份提供商({{ ssoIssuer }})统一登录;请在 SSO 完成后返回本页。
      </p>
    </section>
  </div>
</template>

<script setup lang="ts">
// LoginView — 风格规范第 7 节 /login:温和品牌区 + 清晰登录表单,主操作「登录」;
// 数据用途说明、只读合成演示入口、通用错误(不泄露账号存在性)。
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { DocumentChecked, Finished, UserFilled } from '@element-plus/icons-vue'
import { DEMO_USER, DEMO_VIEWER, useSessionStore, type User } from '../stores/session'
import { apiClient, ApiHttpError, clearAccessToken, setAccessToken } from '../api/client'
import VlButton from '../components/common/VlButton.vue'

const router = useRouter()
const session = useSessionStore()
const client = apiClient()
const isRealMode = import.meta.env.VITE_USE_MOCK === 'false'
const username = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)
// 外部身份提供商模式:后端 /auth/config 声明,前端据此提示 SSO 入口
const ssoIssuer = ref<string | null>(null)

// 品牌区三句主张,对应规范 2.1 的关键词:证据优先、行动优先、低噪声
const pillars = [
  { title: '证据优先', description: '引文可定位、来源清楚', icon: DocumentChecked },
  { title: '行动优先', description: '待复核与逾期靠前', icon: Finished },
  { title: '人工确认', description: 'AI 建议需人工核验', icon: UserFilled },
]

async function submit() {
  error.value = ''
  if (isRealMode) {
    // 真实环境由后端校验;401 一律显示通用错误,不泄露账号存在性
    busy.value = true
    try {
      const result = await client.login(username.value, password.value)
      // 会话由服务端 HttpOnly Cookie 承载,前端不保存令牌
      clearAccessToken()
      session.loginAs({ id: result.user.id, name: result.user.name, email: result.user.email, role: (result.user.role as User['role']) || 'VIEWER' })
      void router.push('/overview')
    } catch (err) {
      error.value = err instanceof ApiHttpError && err.status === 401 ? '用户名或密码不正确' : '暂时无法登录,请稍后重试'
    } finally {
      busy.value = false
    }
    return
  }
  // 演示模式在本地核对两个演示账号,与后端 auth 模块一致
  const match = username.value === 'demo' && password.value === 'demo'
    ? DEMO_USER
    : username.value === 'viewer' && password.value === 'viewer'
      ? DEMO_VIEWER
      : null
  if (!match) {
    error.value = '用户名或密码不正确'
    return
  }
  enter(match)
}

onMounted(async () => {
  if (!isRealMode) return
  try {
    const config = await client.authConfig()
    if (config.mode === 'oidc') ssoIssuer.value = config.issuer ?? '外部身份提供商'
  } catch {
    // 配置不可用时保持本地表单,不阻塞登录
  }
})

function enter(user: typeof DEMO_USER | typeof DEMO_VIEWER) {
  error.value = ''
  busy.value = true
  if (user.role === 'VIEWER') session.loginAsViewer()
  else session.login()
  setAccessToken('demo-token')
  void router.push('/overview')
}

function enterReadonly() {
  enter(DEMO_VIEWER)
}
</script>

<style scoped>
.vl-login {
  min-height: 100dvh;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(20rem, 26rem);
  align-items: center;
  gap: var(--vl-space-10);
  max-width: var(--vl-content-max);
  margin-inline: auto;
  padding: var(--vl-space-8);
}
.vl-login__brand {
  max-width: 32rem;
  padding: var(--vl-space-8);
  border: 1px solid var(--vl-color-brand-line);
  border-radius: var(--vl-radius-dialog);
  background: var(--vl-color-brand-soft);
}
.vl-login__mark-block {
  display: inline-block;
  width: 1.75rem;
  height: 1.75rem;
  border-radius: var(--vl-radius-sm);
  background: var(--vl-color-brand);
}
.vl-login__title {
  margin: var(--vl-space-4) 0 0;
  font-size: var(--vl-text-xl);
  line-height: 2.25rem;
  font-weight: 600;
}
.vl-login__latin {
  font-size: var(--vl-text-md);
  font-weight: 400;
  color: var(--vl-color-brand);
}
.vl-login__slogan {
  margin: var(--vl-space-2) 0 0;
  font-size: var(--vl-text-md);
  color: var(--vl-color-text-secondary);
}
.vl-login__pillars {
  list-style: none;
  margin: var(--vl-space-6) 0 0;
  padding: 0;
  display: grid;
  gap: var(--vl-space-3);
}
.vl-login__pillar {
  display: flex;
  align-items: flex-start;
  gap: var(--vl-space-3);
  font-size: var(--vl-text-sm);
}
.vl-login__pillar-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.75rem;
  height: 1.75rem;
  border-radius: var(--vl-radius-sm);
  background: var(--vl-color-surface);
  color: var(--vl-color-brand);
  flex: none;
}
.vl-login__pillar-desc {
  display: block;
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-muted);
}
.vl-login__usage {
  margin: var(--vl-space-6) 0 0;
  padding-top: var(--vl-space-4);
  border-top: 1px solid var(--vl-color-brand-line);
  font-size: var(--vl-text-sm);
  color: var(--vl-color-text-muted);
}
.vl-login__form {
  border: 1px solid var(--vl-color-border);
  border-radius: var(--vl-radius-dialog);
  background: var(--vl-color-surface);
  padding: var(--vl-space-8);
  box-shadow: var(--vl-shadow-panel);
}
.vl-login__heading {
  margin: 0 0 var(--vl-space-5);
  font-size: var(--vl-text-lg);
  font-weight: 600;
}
.vl-login__fields {
  display: flex;
  flex-direction: column;
  gap: var(--vl-space-5);
}
.vl-login__fields .vl-field {
  display: flex;
  flex-direction: column;
  gap: var(--vl-space-1);
  font-size: var(--vl-text-sm);
  color: var(--vl-color-text-secondary);
}
.vl-login__input {
  min-height: var(--vl-control-height);
  border: 1px solid var(--vl-color-border-control);
  border-radius: var(--vl-radius-control);
  padding: 0 var(--vl-space-3);
  background: var(--vl-color-surface);
}
.vl-login__error {
  margin: 0;
  color: var(--vl-color-danger);
  font-size: var(--vl-text-sm);
}
.vl-login__submit {
  width: 100%;
}
.vl-login__divider {
  margin: var(--vl-space-5) 0;
  text-align: center;
  color: var(--vl-color-text-muted);
  font-size: var(--vl-text-xs);
}
.vl-login__hint {
  margin: var(--vl-space-3) 0 0;
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-muted);
}
.vl-login__sso {
  margin: var(--vl-space-4) 0 0;
  padding: var(--vl-space-2) var(--vl-space-3);
  border-radius: var(--vl-radius-sm);
  background: var(--vl-color-info-bg);
  color: var(--vl-color-info);
  font-size: var(--vl-text-xs);
}
@media (max-width: 767px) {
  .vl-login {
    grid-template-columns: minmax(0, 1fr);
    padding: var(--vl-space-4);
    align-content: start;
    gap: var(--vl-space-6);
  }
}
</style>
