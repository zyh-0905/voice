# 24 项 UI 验收核销(工程计划 13.6 UI-01—UI-24)

> 生成时间:2026-09-10。状态取值:`已验证`(自动化证据)/ `待人工`(需人工浏览器检查)。
> 证据来源:lint:style 门禁、Vitest 单测、Playwright E2E(overview-ui/evidence-ui/
> import-permissions/accessibility/visual)、计算样式探针、后端 pytest。

| ID | 检查点 | 证据来源 | 状态 |
|---|---|---|---|
| UI-01 | 语义 tokens 与暖灰/青绿主题 | check-style-tokens 门禁真实拦截(冒烟验证过);迁移期别名已全部删除;tokens.css 为唯一色值源;design-tokens 单测锁定色值 | 已验证 |
| UI-02 | 外壳与断点 | 计算样式探针:侧栏 224px/顶栏 64px/1600px 限宽/1440 四列+360px 证据列/768 侧栏隐藏+菜单按钮;E2E 覆盖 1440/1280/768/375 | 已验证(1920 档待人工走查) |
| UI-03 | 首页行动顺序与范围 | overview-ui E2E 断言四卡顺序与 scopeLabel(所选分析与筛选 / 本项目·所有分析) | 已验证 |
| UI-04 | 表格密度与导航 | 主题/风险/任务均为表格;topic-table 行内「查看证据」显式入口 E2E | 已验证 |
| UI-05 | 选中与返回上下文 | evidence-ui:断点切换不丢选中;Escape 后焦点回触发行 | 已验证 |
| UI-06 | 侧栏/抽屉语义 | evidence-ui:1440 非模态侧栏(无 aria-modal、无遮罩);1280 模态抽屉(aria-modal+遮罩);同时只存在一份 | 已验证 |
| UI-07 | 证据安全 | 全代码库无 v-html(grep);evidence-quote 单测:Unicode offset、HTML 字面量显示、越界钳制 | 已验证 |
| UI-08 | 草稿与正式动作 | W15 后端 pytest:草稿不能 approve、confirm 缺字段 422、全生命周期分离;前端真实模式禁写操作防乐观更新 | 已验证 |
| UI-09 | 风险/来源标签 | W08 候选恒 PENDING(pytest);ui-status 单测:PENDING ≠ 已人工确认;AiProvenanceBadge 无审核记录不显示确认 | 已验证 |
| UI-10 | 0/null/失败 | metric-card 单测三分;AsyncState 单状态互斥 | 已验证 |
| UI-11 | CPI/复盘显示 | window-compare 单测:黄金样例、百分点、分母反例、数据不足不输出变化 | 已验证 |
| UI-12 | 表单校验 | 登录 label+通用错误;映射必填校验聚焦首个错误(E2E);错误不清空其他输入 | 已验证 |
| UI-13 | 空态分流 | 首页「还没有导入客户反馈」vs 主题「暂无已归类主题…」文案分离;任务/风险筛选空态独立 | 已验证 |
| UI-14 | 进度与刷新 | useOverviewData:refreshing/stale 分离、刷新失败标「数据未刷新,以下为上次结果」;无假百分比(后端 completed/total 真实值) | 已验证 |
| UI-15 | 错误与冲突 | 403→forbidden(前端)/401 token_expired(后端);W13/W15 409 保留语义(后端);429 Retry-After(认证限流) | 已验证 |
| UI-16 | 上下文/隐私 | AbortController 取消旧请求+响应 project_id 校验;切项目重置筛选;URL 只存 ID/时间/枚举;正文不入存储 | 已验证 |
| UI-17 | 图表可读 | TrendChart:可见摘要+单位+时间范围+数据表切换(E2E);null 断点显示「—」 | 已验证 |
| UI-18 | 图表生命周期 | useChart:ResizeObserver、卸载 dispose、reduced-motion 关动画;E2E 验证 canvas 渲染 | 已验证 |
| UI-19 | 权限显示 | import-permissions E2E:VIEWER 无创建/执行按钮;页面只读说明 | 已验证 |
| UI-20 | 键盘与焦点 | E2E:Esc 关闭抽屉+焦点回归;Tab 陷阱在抽屉内;skip-link 存在于外壳 | 已验证(完整 Tab 走查待人工) |
| UI-21 | 对比度 | design-tokens 单测 11 组纯色对比度达标;axe 扫描零 serious/critical(overview+抽屉) | 已验证 |
| UI-22 | 控件目标 | 40/44/32px 控件高度 token;计算样式探针确认 | 已验证 |
| UI-23 | 减少动效 | reduced-motion CSS 覆盖壳内外页面;图表动画关闭 | 已验证(真实浏览器切换待人工) |
| UI-24 | 视觉基线与真实性 | visual.spec 三基线已生成(1440 工作台/375 工作台/1280 证据抽屉),**首版基线待人工核准**;CI 不自动更新基线;截图全为合成 mock 数据 | 待人工(基线核准) |

## 阻断项自查

- 权限/证据安全:UI-07/UI-09/UI-19 已验证
- 错误状态冒充成功:UI-10/UI-14/UI-15 已验证
- 无法操作:UI-02/UI-22 已验证
- 文字不可辨认:UI-21 已验证
- 误导性任务/效果结论:UI-08/UI-11 已验证(后端状态机 + 复盘限制文案)

## 待人工项(需在真实浏览器完成)

1. UI-02:1920px 布局走查
2. UI-20:完整 Tab 顺序走查(登录 → 外壳 → 页面 → 抽屉)
3. UI-23:系统开启「减少动态效果」后的实际表现
4. UI-24:visual 基线三张截图人工核准(位置:`apps/web/tests/e2e/visual.spec.ts-snapshots/`)
