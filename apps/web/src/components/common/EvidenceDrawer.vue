<template>
  <Teleport to="body">
    <Transition name="vl-drawer">
      <div v-if="open" class="vl-overlay" @click.self="emit('close')">
        <aside
          ref="drawerRef"
          class="vl-evidence-drawer"
          data-testid="evidence-drawer"
          role="dialog"
          aria-modal="true"
          aria-labelledby="vl-evidence-drawer-title"
          @keydown="onKeydown"
        >
          <header class="vl-evidence-drawer__header">
            <h2 id="vl-evidence-drawer-title" class="vl-evidence-drawer__title">{{ evidence.topicTitle }}</h2>
            <button
              ref="closeButtonRef"
              type="button"
              class="vl-evidence-drawer__close"
              data-testid="evidence-close"
              @click="emit('close')"
            >
              关闭证据
            </button>
          </header>
          <EvidenceContent :evidence="evidence" :run-label="runLabel" />
        </aside>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
// EvidenceDrawer — 风格规范 6.4/9.5:窄屏模态抽屉;背景不可交互、Tab 在内部循环、
// Esc 关闭、关闭后焦点回到打开前元素;与 EvidencePanel 共用同一内容组件。
import { nextTick, ref, watch } from 'vue'
import type { EvidenceContext } from '../../types/domain'
import EvidenceContent from './EvidenceContent.vue'

const props = defineProps<{
  open: boolean
  evidence: EvidenceContext
  runLabel: string
}>()

const emit = defineEmits<{
  close: []
}>()

const drawerRef = ref<HTMLElement | null>(null)
const closeButtonRef = ref<HTMLButtonElement | null>(null)
let returnFocus: HTMLElement | null = null

watch(
  () => props.open,
  async (open) => {
    if (open) {
      returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
      await nextTick()
      closeButtonRef.value?.focus()
    } else {
      returnFocus?.focus()
      returnFocus = null
    }
  },
)

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    emit('close')
    return
  }
  if (event.key !== 'Tab' || !drawerRef.value) return
  const focusable = Array.from(drawerRef.value.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
    (el) => el.offsetParent !== null || el === document.activeElement,
  )
  if (!focusable.length) return
  const first = focusable[0]!
  const last = focusable[focusable.length - 1]!
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}
</script>

<style scoped>
.vl-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--vl-z-modal);
  background: var(--vl-color-overlay);
}
.vl-evidence-drawer {
  position: absolute;
  inset-block: 0;
  inset-inline-end: 0;
  width: min(30rem, 100vw);
  overflow-y: auto;
  background: var(--vl-color-surface);
  padding: var(--vl-space-6);
  box-shadow: var(--vl-shadow-float);
}
.vl-evidence-drawer__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--vl-space-3);
  margin-bottom: var(--vl-space-3);
}
.vl-evidence-drawer__title {
  margin: 0;
  font-size: var(--vl-text-md);
  line-height: var(--vl-space-6);
  font-weight: 600;
}
.vl-evidence-drawer__close {
  border: none;
  background: none;
  padding: var(--vl-space-1) 0;
  font-size: var(--vl-text-xs);
  color: var(--vl-color-brand);
  cursor: pointer;
  min-height: var(--vl-control-height-compact);
}
.vl-drawer-enter-active,
.vl-drawer-leave-active {
  transition: opacity var(--vl-motion-normal) var(--vl-ease);
}
.vl-drawer-enter-from,
.vl-drawer-leave-to {
  opacity: 0;
}
@media (max-width: 767px) {
  .vl-evidence-drawer {
    width: 100vw;
    padding: var(--vl-space-4);
  }
}
</style>
