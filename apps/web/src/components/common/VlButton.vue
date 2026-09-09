<template>
  <el-button
    class="vl-button"
    :type="elType"
    :loading="loading"
    :disabled="disabled"
    :native-type="type"
    :aria-label="ariaLabel"
    v-bind="$attrs"
  >
    <slot />
  </el-button>
</template>

<script setup lang="ts">
// VlButton — 风格规范 6.2/9.4:40/44/32px 基线由 base.css 与 element-theme.css 控制;
// primary/secondary/ghost/danger 四种变体,原生 button 语义,loading 不变宽。
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
    loading?: boolean
    disabled?: boolean
    type?: 'button' | 'submit'
    ariaLabel?: string
  }>(),
  { variant: 'secondary', loading: false, disabled: false, type: 'button' },
)

const elType = computed<'primary' | 'default' | 'text' | 'danger'>(() => {
  switch (props.variant) {
    case 'primary':
      return 'primary'
    case 'ghost':
      return 'text'
    case 'danger':
      return 'danger'
    default:
      return 'default'
  }
})
</script>
