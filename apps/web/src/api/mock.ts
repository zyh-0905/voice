import type { ApiClient } from './client'
import type { DatasetPreview } from '../types/domain'

/** Deterministic demo client. Supports legacy `upload(file)` and project-scoped `upload(projectId, file)`. */
async function uploadMock(projectOrFile: string | File, fileOrSignal?: File | AbortSignal, _maybeSignal?: AbortSignal): Promise<DatasetPreview> {
  await new Promise((resolve) => setTimeout(resolve, 300))
  const file = typeof projectOrFile === 'string' && fileOrSignal instanceof File ? fileOrSignal : projectOrFile
  const name = typeof file === 'string' ? file : file.name
  return { id: 'demo-1', name, rows: 1248, status: 'ready', hasTime: false }
}

export const mockApi: ApiClient = {
  upload: uploadMock,
  async health() { return { completeness: 0.98, piiMasked: true, timeFieldMissing: 12 } },
  async runAnalysis() {
    await new Promise((resolve) => setTimeout(resolve, 500))
    return { id: 'run-1', status: 'done', total: 1248 }
  },
}
