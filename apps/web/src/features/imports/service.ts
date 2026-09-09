// features/imports/service.ts — 导入向导状态与持久化(工程计划 W05)。
// 仅保存安全状态(dataset_id、run_id、step、health),原文只留在页面内存。
import { ref } from 'vue'
import type { ImportHealthView } from '../../types/domain'

export type ImportStep = 'upload' | 'mapping' | 'report' | 'analyze'

const STEP_KEY = (projectId: string) => `voicelens:import:${projectId}:step`

export function useImportFlow(projectId: string) {
  const step = ref<ImportStep>('upload')

  function readStoredStep(): ImportStep {
    const raw = sessionStorage.getItem(STEP_KEY(projectId))
    return raw === 'mapping' || raw === 'report' || raw === 'analyze' ? raw : 'upload'
  }

  function persistStep(next: ImportStep) {
    step.value = next
    sessionStorage.setItem(STEP_KEY(projectId), next)
  }

  function clearStoredStep() {
    step.value = 'upload'
    sessionStorage.removeItem(STEP_KEY(projectId))
  }

  return { step, readStoredStep, persistStep, clearStoredStep }
}

/** 供治理报告阶段使用;演示环境为确定性合成健康视图,接入后端后替换 */
export function syntheticHealth(): ImportHealthView {
  return { inputRows: 10, validRows: 7, invalidRows: 1, duplicateRows: 2, redactedRows: 3, undatedRows: 0 }
}
