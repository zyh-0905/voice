// real-api 套件的收尾:把 E2E 后端容器删掉。
//
// 为什么需要它:`docker run`(前台)被 Playwright 超时杀掉时收到的是 SIGKILL,
// 而 SIGKILL 无法转发给容器——容器会活下来占住 8010 与容器名,下一次运行报
// 「port already used」,看起来像环境问题,实际是上一次没收拾干净。
import { execFileSync } from 'node:child_process'

const CONTAINER = 'vl_e2e_api'

export default function globalTeardown(): void {
  try {
    execFileSync('docker', ['rm', '-f', CONTAINER], { stdio: 'ignore' })
  } catch {
    // 容器已经不在(正常退出时 --rm 会删掉):收尾失败不该让套件变红
  }
}
