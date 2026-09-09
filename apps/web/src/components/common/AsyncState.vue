<template>
  <div v-if="status === 'loading'" class="vl-async-state" aria-busy="true">
    <slot name="loading"><div class="vl-skeleton" aria-hidden="true" /></slot>
  </div>
  <div v-else-if="status === 'empty'" class="vl-async-state" data-testid="async-empty">
    <slot name="empty"><p class="vl-async-state__text">{{ emptyMessage }}</p></slot>
  </div>
  <div v-else-if="status === 'error'" class="vl-async-state" data-testid="async-error" role="alert">
    <slot name="error">
      <p class="vl-async-state__text vl-async-state__text--error">
        {{ message || '暂时无法获取数据' }}
        <span v-if="requestId" class="vl-async-state__request-id">请求编号:{{ requestId }}</span>
      </p>
    </slot>
  </div>
  <div v-else-if="status === 'forbidden'" class="vl-async-state" data-testid="async-forbidden">
    <slot name="forbidden"><p class="vl-async-state__text">{{ message || '当前角色无权查看此内容' }}</p></slot>
  </div>
  <template v-else>
    <p v-if="refreshing" class="vl-async-state__refreshing" aria-live="polite">正在更新…</p>
    <p v-if="stale" class="vl-async-state__stale" data-testid="stale-data-notice">
      数据未刷新,以下为上次结果{{ staleAt ? `(${staleAt})` : '' }}
    </p>
    <slot />
  </template>
</template>

<script setup lang="ts">
// AsyncState — 风格规范 9.1/9.4:idle/loading/success/empty/error/forbidden 单状态互斥;
// refreshing 与 stale 是 success 之上的附加状态,不替代主状态。
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    status: 'idle' | 'loading' | 'success' | 'empty' | 'error' | 'forbidden'
    message?: string
    emptyMessage?: string
    requestId?: string
    refreshing?: boolean
    stale?: boolean
    staleAt?: string
  }>(),
  { status: 'idle', refreshing: false, stale: false },
)

const emptyMessage = computed(() => props.emptyMessage || '暂无数据')
</script>

<style scoped>
.vl-async-state {
  padding: var(--vl-space-6) var(--vl-space-4);
  text-align: center;
}
.vl-async-state__text {
  margin: 0;
  color: var(--vl-color-text-muted);
}
.vl-async-state__text--error {
  color: var(--vl-color-danger);
}
.vl-async-state__request-id {
  display: block;
  margin-top: var(--vl-space-2);
  font-size: var(--vl-text-xs);
}
.vl-skeleton {
  height: 6rem;
  border-radius: var(--vl-radius-panel);
  background: linear-gradient(
    100deg,
    var(--vl-color-subtle) 30%,
    var(--vl-color-hover) 50%,
    var(--vl-color-subtle) 70%
  );
  background-size: 200% 100%;
}
.vl-async-state__refreshing {
  margin: 0 0 var(--vl-space-3);
  font-size: var(--vl-text-xs);
  color: var(--vl-color-info);
}
.vl-async-state__stale {
  margin: 0 0 var(--vl-space-3);
  padding: var(--vl-space-2) var(--vl-space-3);
  border-radius: var(--vl-radius-sm);
  background: var(--vl-color-warning-bg);
  color: var(--vl-color-warning);
  font-size: var(--vl-text-xs);
}
@media (prefers-reduced-motion: reduce) {
  .vl-skeleton {
    animation: none !important;
  }
}
</style>
