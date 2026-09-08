# VoiceLens Web

当前仓库包含 VoiceLens Web 的首个可运行前端垂直切片：登录演示、项目选择、概览工作台、数据导入向导、字段映射、治理报告和分析进度。

## 启动

要求 Node.js 22.x 与 npm。安装依赖并启动：

```bash
npm --prefix apps/web install
npm --prefix apps/web run dev
```

验证命令：

```bash
npm --prefix apps/web run typecheck
npm --prefix apps/web run test:unit -- --run
npm --prefix apps/web run build
```

当前 API 位于 `src/api`，使用 mock client；后续 FastAPI `/api/v1` 接入时保持 `ApiClient` 契约即可替换。演示数据均有 demo/mock 标识，不代表真实人工复核结果。
