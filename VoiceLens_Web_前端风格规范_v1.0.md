# 诉源镜 VoiceLens Web 前端风格规范

> 版本：Frontend Style v1.1（与 Web Engineering Plan v1.1 配套）  
> 日期：2026-09-12（v1.0 为 2026-09-09）  
> 状态：用户已确认主方向；本文件冻结工程实现规则，不代表前端页面已经实现或通过测试。  
> 适用范围：Vue 3 Web；不包含小程序、原生 App、官网营销页或新一轮品牌重命名。  
> 配套工程计划：[VoiceLens_Web_工程开发计划_v1.1.md](VoiceLens_Web_工程开发计划_v1.1.md)

**设计方向：现代极简工作台为底，概览与复盘采用克制的 Bento 模块布局，加入温和的品牌表达。**

> **v1.1 变更记录（按第 14.3 节变更流程）**
>
> 变更项：主色由青绿改为**浅橙**，中性色改为 Apple 式近白/分层灰，图表扩为 6 个可辨识色相；
> 圆角（面板 12→16px、控件 8→10px、弹窗 16→20px）、阴影改为更柔的分层阴影、页面标题字距收紧。
>
> 理由：用户评审后判定 v1.0 的暖绿灰基调"发闷"，要求参考 Apple 设计风格并以浅橙为主色。
>
> 影响：本文件第 3.1/3.2 节色表、第 14.2 节对比度校核表已同步更新；`tokens.css` 与
> `tests/unit/design-tokens.spec.ts` 同步；UI-21（对比度）在 11 组纯色对上重新通过。
> **不变项**：浅色主题、外壳尺寸（224/64）、正文 14px / 证据 16px、行动优先首页、
> 桌面证据侧栏 / 窄屏抽屉、明确的数据范围与人工操作边界。
>
> 实现约束：亮橙（如 `#FF9500`）与白字仅约 2.2∶1，**不得**用作承载白字的实底；
> 实底使用 `--vl-color-brand: #C2410C`（白字 5.18∶1），浅橙用于表面、选中态与图形。

读者：前端开发者、产品设计者、测试人员，以及执行前端任务的开发代理。本文不仅说明“长什么样”，还规定结构、组件、状态、数据表达、交互和验收。

## 目录

1. [设计依据、权威边界与禁止事项](#f1)
2. [设计语言与页面气质](#f2)
3. [颜色与设计变量](#f3)
4. [字体、尺寸、间距与图标](#f4)
5. [布局、断点与工作台结构](#f5)
6. [组件行为与视觉规格](#f6)
7. [逐页设计要求](#f7)
8. [AI、证据、数据与文案](#f8)
9. [加载、空态、错误、权限和并发](#f9)
10. [动效、键盘、焦点与可访问性](#f10)
11. [Vue、Element Plus 与 ECharts 接入](#f11)
12. [测试、视觉审查与交付门禁](#f12)
13. [前端执行顺序与开发代理指令](#f13)
14. [来源、数值校核与变更管理](#f14)

<a id="f1"></a>
## 1. 设计依据、权威边界与禁止事项

### 1.1 哪些来自项目，哪些是本次设计决定

| 依据 | 本文件保留或增加的内容 |
|---|---|
| 原项目计划书第 4、5、11 节 | 授权导入、问题主题、风险与证据、人工整改、效果复盘；不是自动客服机器人。[R1] |
| 当前 Web 工程计划 v1.0 | Vue 3、TypeScript、Element Plus、ECharts；原有路由、权限、证据快照和任务状态机。[E1] |
| 用户本轮确认的 A＋B 方向 | 极简工作台、Bento 概览、暖中性色与品牌强调；深色后置，玻璃不进入业务内容层。[U1]（v1.1：主色改为浅橙） |
| 本次工程设计补充 | 色值、尺寸、组件接口、响应式规则、首页指标顺序、测试定位符和视觉门禁。它们是本项目的决定，不是某家公司官方参数。[D1] |
| 官方参考 | Element Plus 主题能力、ECharts 可访问性、W3C 与 Playwright 的相关方法；见第 14 节。[S1—S12] |

### 1.2 两份文件如何一起使用

工程计划负责业务范围、接口、字段、权限、统计和排期；本文负责视觉 tokens、组件状态、布局和交互呈现。**颜色/尺寸的唯一规格源是本文第 3—5 节；运行代码的唯一变量源是 `apps/web/src/styles/tokens.css`。** 工程计划只列摘要，不复制另一套完整配色。

仓库内建议分别保存为 `docs/engineering-plan.md` 和 `docs/frontend-style.md`。本文和配套文件之间的下载链接为交付文件名；复制进仓库时同步修改这一个相对链接。

旧 PNG/SVG 是业务演示参考，**不再作为新 Web 外观的逐像素验收标准**。旧稿中的数字、宽度、圆角和颜色与本文冲突时，以新规范为准；旧稿中的业务动作仍须服从工程计划。未经业务规格支持，前端不得为了好看增加服务端字段的含义、假数据或自动操作。

### 1.3 首版禁止事项

不采用全站玻璃卡片、霓虹渐变、发光边框、3D 机器人、自动播放背景、营销式巨大标题或满屏圆环仪表。不得照抄其他产品的商标、图标组合、文案和完整页面。

不因参考 Linear/shadcn 的视觉结构而迁移到 React、替换 Element Plus、额外安装第二套 UI 组件库或引入大型后台模板。首版不开发主题切换器、可拖拽卡片编排、拖拽任务状态、聊天悬浮球和全局命令面板。

**首版只有一种浅色主题。** tokens 使用语义命名，为未来主题保留结构，但不交付半完成的深色模式。玻璃效果首版不实施；以后仅在非核心导航/品牌区域另行评估。

<a id="f2"></a>
## 2. 设计语言与页面气质

### 2.1 一句话目标

让客服主管和运营负责人先看清“现在要处理什么”，再核对“判断依据是什么”，最后明确“谁来做、做到哪一步”。

| 关键词 | 具体做法 | 不要做成 |
|---|---|---|
| 理性 | 对齐、稳定导航、清晰的列、固定的操作位置 | 仿金融交易大屏 |
| 温和 | 近白背景、少量浅橙、自然的文字节奏 | 高饱和撞色、文艺手写字体 |
| 证据优先 | 引文能定位、来源清楚、缺失显式提示 | 只有 AI 总结没有源反馈 |
| 行动优先 | 待复核、逾期与下一步动作靠前 | 总量指标占据整个首屏 |
| 低噪声 | 少量边框、层级明确、一处强调服务一个目的 | 一页多种渐变、多种阴影、多种强调色 |

### 2.2 品牌表达

品牌沿用“诉源镜 VoiceLens”。沿用已有品牌资产时仅检查清晰度与授权，不在本任务重新设计 Logo。品牌图形建议占 24—28px，不压过导航文字；“镜”的概念通过证据聚焦、选中高亮、可回溯入口表达，不通过折射特效表达。

后台页面标题使用“工作台”“主题洞察”“风险复核”“整改任务”“效果复盘”。“从分散的声音，到有依据的行动”仅用于登录页或首次欢迎内容，不每页重复为大标题。空状态插画最多一种轻量原创线稿风格，无插画也能完成首版。

### 2.3 装饰预算

一个页面只保留一个明显的主操作；数据卡片不用四种饱和背景区分。品牌橙用于选中/主要动作，不代表所有指标都在改善。红色仅用于危险操作、高严重度提示和错误；大段正文不使用彩色。

<a id="f3"></a>
## 3. 颜色与设计变量

### 3.1 语义色表

| 用途 | 变量 | 色值 | 使用限制 |
|---|---|---|---|
| 页面背景 | `--vl-color-bg` | `#FBFBFD` | 近白；不叠背景图片 |
| 内容表面 | `--vl-color-surface` | `#FFFFFF` | 表格、证据、表单、指标卡 |
| 次级表面 | `--vl-color-subtle` | `#F5F5F7` | 表头、只读元信息、禁用底色 |
| 悬停表面 | `--vl-color-hover` | `#F1F1F4` | 列表悬停；不暗示选中 |
| 主文字 | `--vl-color-text` | `#1D1D1F` | 标题、正文、核心数字 |
| 次文字 | `--vl-color-text-secondary` | `#515154` | 标签、说明、坐标 |
| 辅助文字 | `--vl-color-text-muted` | `#6E6E73` | 时间/来源；不是浅到看不清的灰 |
| 主品牌色 | `--vl-color-brand` | `#C2410C` | 主按钮、当前导航、关键链接（白字可读） |
| 品牌悬停 | `--vl-color-brand-hover` | `#9A3412` | 可交互主操作悬停 |
| 品牌按下 | `--vl-color-brand-active` | `#7C2D12` | 主操作按下 |
| 品牌浅底 | `--vl-color-brand-soft` | `#FFF4EC` | 选中项、证据聚焦底色 |
| 品牌装饰线 | `--vl-color-brand-line` | `#FDBA74` | 仅装饰，不独立承担控件识别 |
| 品牌图形色 | `--vl-color-brand-vivid` | `#F97316` | 图标、条形、描边等图形强调；**不承载文字** |
| 分隔边线 | `--vl-color-border` | `#E5E5EA` | 卡片/表格细线，不作唯一输入框边界 |
| 控件边界 | `--vl-color-border-control` | `#8E8E93` | 必须靠边界识别的输入框/复选框 |
| 成功文字/底色 | `--vl-color-success` / `--vl-color-success-bg` | `#2E7D32` / `#EDF7ED` | 已保存、执行验收通过；不表示因果改善 |
| 警告文字/底色 | `--vl-color-warning` / `--vl-color-warning-bg` | `#B45309` / `#FEF3E2` | 待复核、数据不完整 |
| 危险文字/底色 | `--vl-color-danger` / `--vl-color-danger-bg` | `#B3261E` / `#FDECEA` | 错误、破坏性操作、严重候选提示 |
| 信息文字/底色 | `--vl-color-info` / `--vl-color-info-bg` | `#0B5EA8` / `#EAF3FD` | 分析中、信息说明 |

色值是本项目设计选择。具体文字/背景组合的静态对比度结果见第 14.2 节；透明度、图片、第三方组件状态变化后须重新测试。

### 3.2 可复制的 `tokens.css`

```css
/* apps/web/src/styles/tokens.css — Frontend Style v1.1 */
:root {
  color-scheme: light;
  --vl-color-bg: #FBFBFD;
  --vl-color-surface: #FFFFFF;
  --vl-color-subtle: #F5F5F7;
  --vl-color-hover: #F1F1F4;
  --vl-color-text: #1D1D1F;
  --vl-color-text-secondary: #515154;
  --vl-color-text-muted: #6E6E73;
  --vl-color-brand: #C2410C;
  --vl-color-brand-hover: #9A3412;
  --vl-color-brand-active: #7C2D12;
  --vl-color-brand-soft: #FFF4EC;
  --vl-color-brand-line: #FDBA74;
  --vl-color-brand-vivid: #F97316;
  --vl-color-border: #E5E5EA;
  --vl-color-border-control: #8E8E93;
  --vl-color-success: #2E7D32;
  --vl-color-success-bg: #EDF7ED;
  --vl-color-warning: #B45309;
  --vl-color-warning-bg: #FEF3E2;
  --vl-color-danger: #B3261E;
  --vl-color-danger-bg: #FDECEA;
  --vl-color-info: #0B5EA8;
  --vl-color-info-bg: #EAF3FD;
  --vl-color-overlay: rgba(29, 29, 31, 0.4);

  --vl-chart-1: #EA580C;
  --vl-chart-2: #0071E3;
  --vl-chart-3: #2E7D32;
  --vl-chart-4: #5856D6;
  --vl-chart-5: #AF52DE;
  --vl-chart-6: #0E7490;

  --vl-font-sans: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display",
    system-ui, "PingFang SC", "Helvetica Neue", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
  --vl-tracking-tight: -0.015em; /* 标题字距收紧 */
  --vl-font-mono: ui-monospace, SFMono-Regular, Consolas, monospace;
  --vl-text-xs: 0.75rem;    /* 12px：仅辅助信息 */
  --vl-text-sm: 0.875rem;   /* 14px：正文、表格 */
  --vl-text-md: 1rem;      /* 16px：证据原文、区块标题 */
  --vl-text-lg: 1.25rem;   /* 20px：二级页标题 */
  --vl-text-xl: 1.625rem;  /* 26px：页面标题 */
  --vl-text-metric: 2rem;  /* 32px：指标值 */
  --vl-leading-body: 1.5714286;
  --vl-leading-evidence: 1.625;

  --vl-space-1: 0.25rem;
  --vl-space-2: 0.5rem;
  --vl-space-3: 0.75rem;
  --vl-space-4: 1rem;
  --vl-space-5: 1.25rem;
  --vl-space-6: 1.5rem;
  --vl-space-8: 2rem;
  --vl-space-10: 2.5rem;
  --vl-space-12: 3rem;

  --vl-radius-sm: 0.5rem;
  --vl-radius-control: 0.625rem;
  --vl-radius-panel: 1rem;
  --vl-radius-dialog: 1.25rem;
  --vl-control-height: 2.5rem;
  --vl-control-height-touch: 2.75rem;
  --vl-control-height-compact: 2rem;
  --vl-sidebar-width: 14rem;
  --vl-header-height: 4rem;
  --vl-evidence-width: 22.5rem;
  --vl-content-max: 100rem;

  --vl-shadow-panel: 0 1px 2px rgba(0, 0, 0, 0.04), 0 1px 3px rgba(0, 0, 0, 0.03);
  --vl-shadow-float: 0 12px 32px rgba(0, 0, 0, 0.12), 0 2px 8px rgba(0, 0, 0, 0.06);
  --vl-motion-fast: 120ms;
  --vl-motion-normal: 180ms;
  --vl-ease: cubic-bezier(0.2, 0, 0, 1);
  --vl-z-sticky: 20;
  --vl-z-popover: 1000;
  --vl-z-modal: 2000;
  --vl-z-message: 3000;
}
```

`rem` 的标注像素值以浏览器默认 16px 根字号为参考，不通过把 `html` 字号改成 10px/62.5%“方便计算”。不设置 `user-scalable=no`，不限制用户缩放。

### 3.3 旧变量迁移

旧工程计划的 `--vl-ink/brand/bg/muted/line/mint/amber/red/white` 与 `--vl-radius-card/button` 不再作为新代码命名。已有页面实际使用时可短期加入下列别名；新组件不能继续新增旧名称。

```css
/* 仅在仓库已存在旧样式时加入 tokens.css 末尾 */
:root {
  --vl-ink: var(--vl-color-text);
  --vl-muted: var(--vl-color-text-muted);
  --vl-brand: var(--vl-color-brand);
  --vl-bg: var(--vl-color-bg);
  --vl-mint: var(--vl-color-brand-soft);
  --vl-line: var(--vl-color-border);
  --vl-amber: var(--vl-color-warning);
  --vl-red: var(--vl-color-danger);
  --vl-white: var(--vl-color-surface);
  --vl-radius-card: var(--vl-radius-panel);
  --vl-radius-button: var(--vl-radius-control);
  --vl-font-body: var(--vl-text-sm);
  --vl-font-title: var(--vl-text-xl);
  --vl-font-family: var(--vl-font-sans);
}
```

样式的十六进制颜色、RGB/HSL 颜色只允许出现在 `tokens.css`；图表从计算后的 CSS 变量读取颜色。源代码扫描排除图片、SVG 品牌源文件、测试快照与第三方依赖。组件内不得写新的“差不多一样的绿色”。

<a id="f4"></a>
## 4. 字体、尺寸、间距与图标

### 4.1 排版标尺

| 内容 | 字号/参考行高 | 字重 | 限制 |
|---|---|---|---|
| 页面标题 | 26/36px | 600 | 一个页面一个 h1；不用 48px 营销标题 |
| 二级页标题 | 20/28px | 600 | 详情页内主要章节 |
| 面板标题 | 16/24px | 600 | 标题旁说明用 14px |
| 正文/表格 | 14/22px | 400 | 高风险理由、操作说明不得降成 12px |
| 脱敏证据原文 | 16/26px | 400 | 不用等宽字体排中文正文 |
| 辅助元信息 | 12/18px | 400 | 时间、版本、小型编号；必须可读 |
| 指标数字 | 30/36px | 600 | `font-variant-numeric: tabular-nums` |
| 按钮 | 14/20px | 500 | 显示完整动作，不只写“确定” |

长标题换行，不能让溢出省略隐藏风险级别或任务状态。表格可截断主题名，但要提供键盘可达的详情链接；风险原文详情始终可展开全文。数值右对齐，中文名称左对齐；不要对中文正文使用大字距和全大写效果。

### 4.2 间距与触达尺寸

常用间距为 4/8/12/16/20/24/32/40/48px。页面外边距桌面 24px、窄屏 16px；面板内边距 20px、窄屏 16px；面板间距 16px；标题与说明 8px；表单字段组间距 20px。

主要按钮、输入、下拉框高 40px；触摸/窄屏目标至少 44px；密集表格行内次要按钮可为 32px。图标按钮的命中区域按按钮尺寸，不是图标本身 16px。WCAG 的 24px 最小目标条款有例外，**本项目的一般控件采用更宽裕的尺寸，不把 24px 当默认设计目标**。[S4]

表格标准行至少 52px；紧凑模式不在首版提供切换器，可仅在数据导入预览中用 44px。多行内容允许撑高，不用固定高度裁掉正文。表头参考 44px，行内两个操作至少间隔 8px。

### 4.3 图标

首版沿用 `@element-plus/icons-vue`，统一 16/20px 尺寸，同一导航层级不得混用表情符号、填充 3D 图标和另一套图标库。装饰图标 `aria-hidden=true`；独立图标按钮必须有中文可访问名称。危险状态必须同时有文字，不只靠红点或感叹号。

<a id="f5"></a>
## 5. 布局、断点与工作台结构

### 5.1 外壳

桌面为 224px 左侧导航＋64px 顶部栏＋自适应内容区。顶部放项目切换、当前位置、合成演示/只读提示和用户菜单；具体页面的主操作放页面标题区，不重复塞入顶部栏。

主内容最大宽度 1600px；宽屏居中，不无限拉长证据正文。普通页面以文档为主滚动区域，不制造三个并列的纵向滚动容器。复杂表格仅在自己容器内横滚，不能靠给整个 `body` 加 `overflow-x:hidden` 掩盖布局缺陷。

导航名称固定为：工作台、数据导入、主题洞察、风险复核、整改任务、效果复盘；设置置底。分析进度作为导入/分析详情路径，不新增“AI 中心”导航。当前项有品牌浅底＋明显文字状态（v1.1 起可加左侧品牌指示条）；非当前项不铺满彩色底。

### 5.2 断点矩阵

| CSS 视口宽度 | 导航 | 概览指标 | 快速证据 | 主体布局 |
|---|---|---|---|---|
| ≥1440px | 224px 带文字侧栏 | 四列 | 360px 非模态侧栏 | 主列＋侧列；12 列网格用于概览排版 |
| 1024—1439px | 224px 带文字侧栏 | 两列 | 480px 模态抽屉，受视口限制 | 表格/趋势纵向；待办区可放下方 |
| 768—1023px | 菜单按钮打开模态导航 | 两列 | 480px 模态抽屉，受视口限制 | 无常驻左栏，保留筛选文字 |
| 320—767px | 菜单按钮 | 一列 | 全宽模态抽屉 | 表单单列、按钮换行、表格局部横滚 |

页面支持窄屏是 Web 响应式要求，不是另做 App。普通内容在等效 320px 下必须重排；数据表这类需要二维关系的内容可局部滚动，但表格标题、搜索和分页不能一起被挤出屏幕。[S7]

### 5.3 首页信息布局

从上到下：页面标题与“导入客户反馈” → 分析/时间/渠道/产品筛选 → 四个行动指标 → 优先处理主题 → 反馈趋势 → 待办/最近导入辅助区。

桌面使用右侧辅助列承载待办与最近批次。点击主题证据时，该辅助列切换为证据侧栏；关闭后恢复原辅助内容。指标区横跨主列与侧列，不因查看证据而缩成四个狭窄方块。窄屏不做辅助列替换，证据进入抽屉。

首页指标顺序固定：

| 顺序/文案 | 字段 | 统计范围/点击行为 |
|---|---|---|
| 1 待复核风险 | `insight_metrics.pending_risk_feedback_count` | 所选分析及反馈筛选；进入风险页并带相同条件与 PENDING |
| 2 逾期整改 | `action_metrics.overdue_task_count` | 本项目所有分析；进入 `tasks?overdue=true` |
| 3 未关闭任务 | `action_metrics.active_task_count` | 本项目所有分析；进入任务页并选“未关闭”组合 |
| 4 有效反馈 | `insight_metrics.valid_feedback_count` | 所选分析及反馈筛选；进入同条件主题洞察；不虚构“反馈总表”新路由 |

接口范围值固定：`insight_metrics.scope="selected_analysis"`；`action_metrics.scope="project_all_runs"`。前者绑定所选分析和反馈条件，后者仅绑定当前项目。读取未知 scope 时显示契约错误，不猜测指标口径。

“待复核风险”不是“已确认事故”；使用全 severity 的 pending 反馈去重数，不能把它写成仅 high/critical 的数量。high/critical 候选用独立文字标签在列表/提醒区突出。两组指标分别常显“所选分析与筛选”和“本项目·所有分析”，任务指标不受顶部反馈时间窗口影响；详见工程计划第 7.7 节。主题数量保留在主题表标题摘要，不删除业务指标，也不为了凑四张卡创造新含义。

### 5.4 可复制布局基础

```css
/* apps/web/src/styles/base.css 的布局节选 */
* { box-sizing: border-box; }
html { color-scheme: light; }
body {
  margin: 0;
  color: var(--vl-color-text);
  background: var(--vl-color-bg);
  font-family: var(--vl-font-sans);
  font-size: var(--vl-text-sm);
  line-height: var(--vl-leading-body);
}
button, input, select, textarea { font: inherit; }
.vl-shell { min-height: 100dvh; }
.vl-main { min-width: 0; }
.vl-page {
  width: 100%;
  max-width: var(--vl-content-max);
  margin-inline: auto;
  padding: var(--vl-space-6);
}
.vl-panel {
  min-width: 0;
  border: 1px solid var(--vl-color-border);
  border-radius: var(--vl-radius-panel);
  background: var(--vl-color-surface);
  padding: var(--vl-space-5);
  box-shadow: var(--vl-shadow-panel);
}
.vl-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--vl-space-4);
}
.vl-overview-grid { display: grid; gap: var(--vl-space-4); }
.vl-overview-primary { min-width: 0; display: grid; gap: var(--vl-space-4); }
.vl-table-scroll { min-width: 0; max-width: 100%; overflow-x: auto; }
.vl-evidence-text {
  font-size: var(--vl-text-md);
  line-height: var(--vl-leading-evidence);
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
.vl-number { font-variant-numeric: tabular-nums; }
@media (min-width: 1024px) {
  .vl-shell { display: grid; grid-template-columns: var(--vl-sidebar-width) minmax(0, 1fr); }
}
@media (min-width: 1440px) {
  .vl-metrics { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .vl-overview-grid { grid-template-columns: minmax(0, 1fr) var(--vl-evidence-width); }
}
@media (max-width: 767px) {
  .vl-page { padding: var(--vl-space-4); }
  .vl-panel { padding: var(--vl-space-4); }
  .vl-metrics { grid-template-columns: minmax(0, 1fr); }
}
```

不使用 CSS `order` 把实际阅读顺序完全改写；小屏与键盘顺序必须仍符合工作流程。Bento 不是瀑布流，不随机改变卡片大小，不让相邻表单的提交按钮上下错位。

<a id="f6"></a>
## 6. 组件行为与视觉规格

### 6.1 基础组件

| 组件/路径（`src/components/common/`） | 视觉/尺寸 | 必须行为 |
|---|---|---|
| `PageHeader.vue` | 标题 26px，说明 14px；标题区下距 24px | 一个 h1；右侧主操作；窄屏操作换行 |
| `VlButton.vue` | 40px 高，8px 圆角；primary/secondary/ghost/danger | 原生 button 语义；loading 不变宽；有文字动作 |
| `VlPanel.vue` | 白底、1px 边框、12px 圆角 | 标题/说明/正文/操作插槽；不嵌套三层白卡 |
| `FilterBar.vue` | 输入默认 40px，间距 12px | 显示已生效条件、清除入口；文本筛选 300ms 去抖，离散选择即时应用 |
| `MetricCard.vue` | 主数字 30px，标签 14px，范围说明至少 12px | null 显示“—”；0 显示 0；错误不显示 0；点击是可访问链接/按钮 |
| `StatusBadge.vue` | 文字＋可选图标，圆角 6px | severity、任务状态、来源状态分别传入，禁止混为一个 enum |
| `AsyncState.vue` | 与内容高度接近的骨架或状态区域 | 首次加载/空/错误/content 互斥；刷新过期数据显式标记 |
| `DemoNotice.vue` | 小型蓝灰信息条，不做红色警报 | 始终区分合成演示、预计算演示和真实项目 |

组件名称是目标文件，不代表已经存在。样式变体用 TypeScript union 限定；props 不开放任意主色、字体和圆角，让各页任意改品牌。

### 6.2 按钮与表单

主要动作使用品牌深橙实底白字；次要动作用白底控件边框；文本操作使用品牌橙并有可辨认的链接/按钮语义；删除为深红实底或危险描边，仅放在真正危险操作上。

`VlButton` 必须支持 `type='button'|'submit'`、`variant`、`loading`、`disabled`、`aria-label` 和透传事件。readonly 原因通过邻近说明显示，不能藏在无法悬停/聚焦的 disabled 按钮上。

字段必须有可见 label，placeholder 只给示例。前端校验报错后聚焦第一个错误字段，并显示汇总/内联信息；不要清空其他字段。可修复的“负责人未选”保留提交按钮可点击以触发校验；无权限、请求进行中、来源失效时才禁用相关动作，并说明原因。该决定与原工程任务 E2E 的“点确认后看到字段错误”一致。

### 6.3 表格

主题、风险、任务列表均用表格/列表，不全部改成大卡片。主题表基本列：主题、反馈 n/N、占比、趋势、CPI、复核状态、查看证据。排序优先遵循后端；critical 风险的置顶不能被“美观排序”覆盖。

文字列左对齐；数值列右对齐且使用等宽数字；状态不只用颜色。表头包含列名和排序状态。行内首要动作有明显入口；整行点击可作为增强，但不得成为唯一操作方式，也不能把包含其他按钮的整行设为一个嵌套按钮。

分页默认 20，允许 20/50/100；沿用服务端上限。切换条件后页码回 1，保留已选择的项目和 run。`未关闭` 是对 OPEN/IN_PROGRESS/PENDING_REVIEW 的筛选组合，不是新任务状态。首版任务表不提供拖拽。

### 6.4 证据区

`EvidencePanel.vue` 负责内容；`EvidenceDrawer.vue` 负责窄屏模态容器；`EvidenceQuote.vue` 负责安全引文。面板顺序：主题和版本 → AI/人工来源 → 摘要 → CPI 分项 → 原文/源行号/渠道/可信时间 → 操作。

证据高亮只针对服务端给出的脱敏原文和 offset；禁止 `v-html`、不执行引文中的链接、脚本和指令。若必须在浏览器按 Unicode 字符 offset 切片，先用 `Array.from(text)`，不将 UTF-16 code-unit 索引当作服务端字符索引；还要核对拼回的完整文本与 quote 一致。不能为了视觉截断修改证据原文。

桌面侧栏为非模态 `aside`：不锁背景、不加 `aria-modal`、不陷阱焦点。用户主动打开时可聚焦标题，提供“回到列表”与关闭入口。抽屉为模态：背景不可交互、Tab 在内部循环、Esc 关闭、关闭后回到原触发器。[S6] 改变断点时保留当前记录，不能同时显示两份可交互的证据。

### 6.5 AI 标识与人工确认

`AiProvenanceBadge.vue` 展示“AI 建议”“规则候选”“人工修订”“来源未提供”。点击后打开已存来源与限制；没有模型名称/运行时间就不编造。`needs_review=false` 不是人工确认凭据；“人工已确认”必须有实际审核人、时间和审核记录支持。参考 Carbon 的思路是让标识通向解释，而不是给所有卡片贴一个闪亮 AI 标签。[S10]

`HumanReviewDialog.vue` 的主按钮应写“确认创建任务”“确认风险”“通过执行验收”等具体动作。风险复核必须填写理由；任务确认必须显示负责人、期限、验收标准和来源；版本冲突时保留本地输入，与最新数据并列比较，不能静默覆盖。

一次最多一个业务模态层。需从证据进入长表单时跳转已有详情页，不能在抽屉上再叠三个弹窗。页面编辑离开时的未保存提示替换当前确认层，不叠加多个焦点陷阱。

### 6.6 图表

`TrendChart.vue` 默认折线或柱状图，白底、细坐标、单位清楚；图表区参考 280—320px 高。单一指标使用品牌橙（`--vl-chart-1`），比较窗口使用不同线型/形状和图例；多分类色最多使用 tokens 的 6 色，类别过多优先改为排序表或条形图。

折线不平滑，不用面积渐变制造增长感；缺数据保持断点，`connectNulls=false`；柱状图数值轴从 0 起，比例视图注明轴范围。主题占比可能多标签合计超过 100%，因此不用饼图假装互斥构成。

每张图必须有可见文字摘要、单位、时间范围和“查看数据表”入口。ARIA 自动描述是补充，不能替代可见摘要和表格。[S8] tooltip 不包含未脱敏正文；首版图表 tooltip 用 `renderMode='richText'`，不得将用户正文拼成 HTML formatter。

<a id="f7"></a>
## 7. 逐页设计要求

| 路由 | 布局/最重要动作 | 必须保留的信息 | 首版不要增加 |
|---|---|---|---|
| `/login` | 温和品牌区＋清晰登录表单；主动作“登录” | 数据用途说明、只读合成演示入口、通用错误 | 全屏视频、巨型宣传插画、新注册流程 |
| `/projects` | 简洁项目列表或小卡片 | 角色、项目名、真实/演示身份 | 无权限项目占位、付费套餐卡 |
| `/demo` | 与真实页面一致的只读视觉 | 常驻合成标识；mock/预计算信息 | 可写共享管理账号 |
| `/p/:p/overview` | 行动指标＋优先主题＋趋势＋证据联动 | 指标范围、run/revision、筛选、数据更新时间 | 混合不同 run 结果、虚构收益大数字 |
| `/p/:p/imports` | 批次表＋四步向导：上传/映射/报告/分析 | 授权主动勾选、时间策略、行级错误 | 聊天上传、自动对外发原始文件 |
| `/p/:p/analyses/:r` | 阶段时间线＋真实进度 | 阶段、实际 completed/total、警告、请求编号 | 计时器模拟百分比、无根据倒计时 |
| `/p/:p/topics` | 高效表格，侧栏/抽屉核验 | 待归类、主题数、n/N、筛选和版本 | 卡片瀑布流 |
| `/p/:p/topics/:t` | 主内容＋解释/证据；校正走明确表单 | 原文、人工修改历史、影响范围 | 无记录自动合并、伪造根因 |
| `/p/:p/risks` | 待复核队列＋证据＋裁决区 | 候选/确认/排除、严重度、裁决理由 | 将 critical 候选写为已发生事故 |
| `/p/:p/tasks` | 表格，状态/负责人/逾期筛选 | 截止日期、来源、负责人、下一动作 | 拖拽绕过状态机 |
| `/p/:p/tasks/:t` | 任务内容＋来源＋时间线 | 草稿/派发/执行/提交/验收分离 | “一键全部完成”、自动自验收 |
| `/p/:p/reviews` | 记录表＋清晰创建向导 | 选择 run、revision、目标主题与两窗口 | 名称相同就自动对齐主题 |
| `/p/:p/reviews/:r` | Bento 对照区＋趋势＋限制说明 | n/N、占比、百分点、相对变化、可比性 | 无数据变绿色下降100%、宣称因果 |
| `/p/:p/settings` | 分组表单；危险区置底 | 模型可用性不泄密、规则版本、删除影响 | 常驻醒目红色整页底色 |

Bento 仅用于概览、复盘和少量健康报告信息，不修改全部路由的基本工作模式。日期选择控件上显示项目时区；详细版本/计算时间用说明区，不把每条元数据做成彩色胶囊。

<a id="f8"></a>
## 8. AI、证据、数据与文案

### 8.1 任务状态映射

| 服务端状态 | 中文标签 | 外观/含义 |
|---|---|---|
| DRAFT | 草稿·待确认 | 中性；未派发 |
| OPEN | 待开始 | 信息色；已有人工确认 |
| IN_PROGRESS | 进行中 | 信息色；真实执行中 |
| PENDING_REVIEW | 待验收 | 警告色；不是已完成 |
| CLOSED | 执行已验收 | 成功色；不证明经营效果 |
| CANCELLED | 已取消 | 中性；保留原因 |

`effect_status` 单独显示：NOT_EVALUATED＝尚未复盘，INSUFFICIENT_DATA＝数据不足，OBSERVED_CHANGE＝观察到变化。不得增加“已证实改善”前端枚举。

### 8.2 数字显示

只格式化服务端结果，不重新计算 CPI、分母、复盘统计或任务状态。反馈量用千分位；占比默认 1 位小数；CPI 使用服务端 `display_value`。无值为“—”并说明原因，真实零为“0”；请求失败显示错误，不显示“暂无数据”。

黄金样例沿用工程计划：CPI 67.5 显示 68；168/1000→102/1000 显示 16.8%→10.2%，变化 −6.6 个百分点；相对占比变化显示 −39.3%，需明确“相对”二字。100/1000→80/500 应同时显示数量减少、占比 10.0%→16.0%，不能选择性报喜。[E1]

### 8.3 固定文案

| 场景 | 使用 | 禁止 |
|---|---|---|
| 主题建议 | “AI 建议，需核对原文” | “AI 已确定根本原因” |
| 待复核 | “发现风险候选，请人工核验” | “检测到违法行为” |
| 草稿产生 | “已生成整改草稿，尚未派发” | “AI 已完成整改” |
| 提交材料 | “已提交，等待执行验收” | “整改成功” |
| 复盘变化 | “观察到反馈占比下降，不能据此证明因果关系” | “系统证明本次整改有效” |
| 可比性不足 | “数据不足，暂不输出变化结论” | “下降 100%” |
| 命名失败 | “部分主题待命名，原文证据仍可查看” | “所有分析失败”或伪造正常标题 |
| 空主题 | “暂无已归类主题，仍可查看风险候选与待归类反馈” | “没有任何问题” |

原书涉及“验证效果”的业务目标在当前工程计划中已经限定为描述性比较；本文延续此工程限定，不借视觉宣传重新扩大结论。

<a id="f9"></a>
## 9. 加载、空态、错误、权限和并发

### 9.1 组件状态模型

页面数据至少区分 `idle / loading / success / empty / error / forbidden`；`refreshing` 是已有 success 数据的附加状态。首次 loading 使用形状对应的骨架；刷新保留旧内容时标明“正在更新”，失败后标明“数据未刷新，以下为上次结果”并显示时间，不能当作最新结果。

`empty` 仅在成功响应且记录确为空时出现。未导入、尚未分析、筛选无结果、无权限是不同状态，应提供不同下一步。警告数据正常显示并附 `warning` 提示，不简单覆盖为整页失败。

### 9.2 错误呈现表

| 状态/错误 | 用户看到什么 | 动作 |
|---|---|---|
| 首次无数据 | “还没有导入客户反馈” | 有权限者导入；只读者联系管理员 |
| 筛选为空 | 显示当前筛选与“没有匹配结果” | 清除筛选，不清空整个项目 |
| 401 | 会话过期，登录后可重新进入 | 清空敏感内存；只保留安全路由，不持久化正文 |
| 403 | 当前角色不能执行此操作 | 只读说明，不自动重试 |
| 404 | 资源不存在或不可访问 | 返回本项目安全列表；不暴露外项目存在性 |
| 409 VERSION_CONFLICT | 最新版本与本地未提交修改提示 | 保留本地内存输入；用户决定是否应用到新版本 |
| 422 | 字段或业务规则错误 | 错误映射到字段、聚焦；不清空有效输入 |
| 429 | 操作受限，按服务端提示稍后重试 | 遵守 Retry-After；不每秒自动刷 POST |
| 503/网络断开 | 暂时无法获取，显示请求编号 | 手动重试；旧数据显式标为过期 |
| 证据已删除 | 来源已不可用 | 禁止依此确认新任务；保留必要非正文提示 |
| 分析部分降级 | 部分主题待确认 | 展示真实完成部分与限制，不假装全成功 |

全站状态通知用于成功的短反馈；字段错误放表单内，影响整个操作的失败留在可见内容区。Toast 默认只写“保存成功”等简短提示，不能是查看错误原因的唯一方式。

### 9.3 请求与筛选

项目/run/筛选变化时取消旧请求，并校验响应上下文。筛选 URL 只保存 ID、时间和枚举；不存引文、个人信息、草稿正文或密钥。文本输入 300ms 去抖，选择项目/下拉项不去抖；浏览器后退恢复筛选、页码和选中项。

写操作的幂等键在同一次用户意图的重试中不变。风险裁决、派发、验收、删除采用等待服务端确认的交互，不做会让用户误以为成功的乐观更新。非敏感显示偏好可以本地保存，客诉和表单正文只留当前页面内存。

<a id="f10"></a>
## 10. 动效、键盘、焦点与可访问性

按钮/行 hover 过渡 120ms，抽屉/面板显隐 180ms；仅操作 opacity/transform，不做全屏视差或数据数字跳动。表格加载、图表更新不反复闪屏。`prefers-reduced-motion: reduce` 下去掉非必要动效，图表关闭动画。[D1]

一般文字按至少 4.5∶1 设计；有意义的控件边界和图形按至少 3∶1 检查；品牌浅线仅为装饰，不能独立作唯一输入框识别手段。大文字/禁用控件等规范例外不能用来让普通正文变浅。[S2][S3]

每页有跳到正文链接、合理标题层级、可见焦点。粘性顶栏/底部操作栏不能遮住焦点，给内容保留空间。读屏不每两秒播报轮询百分比，只在阶段改变、完成和失败时用 `aria-live='polite'` 通知。

```css
/* base.css：焦点与动效；Element Plus 内部控件见适配层 */
:where(a, button, input, select, textarea, [tabindex]):focus-visible {
  outline: 2px solid var(--vl-color-brand);
  outline-offset: 2px;
}
:where(a, button, input, select, textarea, [tabindex]) {
  scroll-margin-block: 5rem;
}
.vl-button {
  min-height: var(--vl-control-height);
  border-radius: var(--vl-radius-control);
  transition: background-color var(--vl-motion-fast) var(--vl-ease),
              border-color var(--vl-motion-fast) var(--vl-ease);
}
.vl-skip-link {
  position: fixed;
  inset-inline-start: var(--vl-space-4);
  inset-block-start: var(--vl-space-4);
  z-index: var(--vl-z-message);
  padding: var(--vl-space-3);
  color: var(--vl-color-surface);
  background: var(--vl-color-brand);
  transform: translateY(-200%);
}
.vl-skip-link:focus { transform: translateY(0); }
@media (pointer: coarse), (max-width: 767px) {
  .vl-button { min-height: var(--vl-control-height-touch); }
}
@media (prefers-reduced-motion: reduce) {
  .vl-shell *, .vl-overlay, .vl-overlay * {
    animation: none !important;
    transition: none !important;
    scroll-behavior: auto !important;
  }
}
```

不要用 `outline:none` 消除焦点，除非同一状态提供经过测试的等价可见焦点。Esc 关闭含未保存输入的表单时先进入明确的放弃修改确认流程；请求已发出不应冒充可撤销，允许关闭时告知可在作业页查看状态。

<a id="f11"></a>
## 11. Vue、Element Plus 与 ECharts 接入

### 11.1 目标文件和职责

```text
apps/web/src/
├── styles/
│   ├── tokens.css                 # 唯一原始色值/尺寸源
│   ├── base.css                   # 排版、布局、focus、reduced motion
│   └── element-theme.css          # Element Plus 变量与有限适配
├── layouts/AppShell.vue           # 桌面外壳/窄屏导航
├── components/common/
│   ├── PageHeader.vue / VlPanel.vue / VlButton.vue
│   ├── ProjectSwitcher.vue / FilterBar.vue / DemoNotice.vue
│   ├── MetricCard.vue / StatusBadge.vue / AsyncState.vue
│   ├── EvidencePanel.vue / EvidenceDrawer.vue / EvidenceQuote.vue
│   ├── AiProvenanceBadge.vue / RiskBadge.vue / CpiBreakdown.vue
│   ├── HumanReviewDialog.vue / TaskTimeline.vue / WindowCompare.vue
│   └── ImportHealth.vue / AnalysisProgress.vue
├── composables/useEvidenceSelection.ts
├── composables/useChart.ts
├── lib/chart-theme.ts
├── lib/ui-status.ts               # 中文标签/状态语义，不定义业务转换
└── features/dev/StyleLabPage.vue   # 仅 development/test，合成数据
```

不建立第二个只供截图的组件体系。StyleLab 必须使用业务页真正导入的组件。开发页 `/__dev/style-lab` 通过 `import.meta.env.DEV` 或显式 `import.meta.env.MODE === 'test'` 注册；生产默认构建不注册，不接受 URL 参数解除限制。

### 11.2 样式顺序与主题桥接

保留当前工程的完整导入或按需导入方案；本次不为风格切换更改打包体系。以下示例适用于完整导入，用于说明顺序：

```ts
// apps/web/src/main.ts 的样式导入顺序；其余 app/router/pinia 初始化沿用工程
import 'element-plus/dist/index.css'
import './styles/tokens.css'
import './styles/element-theme.css'
import './styles/base.css'
```

按需组件样式应在同一受控流程中加载，并验证样式懒加载不会覆盖桥接值。弹窗常被 Teleport 到 body，关键主题变量放 `:root`，不能只放 `#app` 或一个 scoped 页面容器。官方支持 CSS variables 定制，不必为全站逐组件重写样式。[S1]

```css
/* apps/web/src/styles/element-theme.css */
:root {
  --el-font-family: var(--vl-font-sans);
  --el-font-size-base: var(--vl-text-sm);
  --el-color-primary: var(--vl-color-brand);
  --el-color-primary-dark-2: var(--vl-color-brand-active);
  --el-color-primary-light-3: var(--vl-color-brand);
  --el-color-primary-light-5: var(--vl-color-brand-line);
  --el-color-primary-light-7: var(--vl-color-brand-soft);
  --el-color-primary-light-8: var(--vl-color-brand-soft);
  --el-color-primary-light-9: var(--vl-color-brand-soft);
  --el-color-success: var(--vl-color-success);
  --el-color-success-light-9: var(--vl-color-success-bg);
  --el-color-warning: var(--vl-color-warning);
  --el-color-warning-light-9: var(--vl-color-warning-bg);
  --el-color-danger: var(--vl-color-danger);
  --el-color-danger-light-9: var(--vl-color-danger-bg);
  --el-color-error: var(--vl-color-danger);
  --el-color-info: var(--vl-color-info);
  --el-color-info-light-9: var(--vl-color-info-bg);
  --el-text-color-primary: var(--vl-color-text);
  --el-text-color-regular: var(--vl-color-text-secondary);
  --el-text-color-secondary: var(--vl-color-text-muted);
  --el-text-color-placeholder: var(--vl-color-text-muted);
  --el-bg-color: var(--vl-color-surface);
  --el-bg-color-page: var(--vl-color-bg);
  --el-bg-color-overlay: var(--vl-color-surface);
  --el-fill-color-blank: var(--vl-color-surface);
  --el-fill-color-light: var(--vl-color-subtle);
  --el-border-color: var(--vl-color-border-control);
  --el-border-color-light: var(--vl-color-border);
  --el-border-radius-base: var(--vl-radius-control);
  --el-component-size: var(--vl-control-height);
  --el-component-size-large: var(--vl-control-height-touch);
  --el-component-size-small: var(--vl-control-height-compact);
}
.vl-button.el-button--primary:not(.is-plain) {
  --el-button-bg-color: var(--vl-color-brand);
  --el-button-border-color: var(--vl-color-brand);
  --el-button-text-color: var(--vl-color-surface);
  --el-button-hover-bg-color: var(--vl-color-brand-hover);
  --el-button-hover-border-color: var(--vl-color-brand-hover);
  --el-button-hover-text-color: var(--vl-color-surface);
  --el-button-active-bg-color: var(--vl-color-brand-active);
  --el-button-active-border-color: var(--vl-color-brand-active);
}
.vl-button.is-disabled {
  opacity: 1;
  --el-button-disabled-bg-color: var(--vl-color-subtle);
  --el-button-disabled-text-color: var(--vl-color-text-muted);
  --el-button-disabled-border-color: var(--vl-color-border);
}
.vl-field .el-input__wrapper:focus-within,
.vl-field .el-select__wrapper:focus-within {
  outline: 2px solid var(--vl-color-brand);
  outline-offset: 2px;
}
```

此桥接是实现基线，厂商变量里的 `light-*` 名称不等于业务颜色角色。primary 按钮 hover 已明确用更深颜色，避免浅底白字。标签使用本项目 StatusBadge 的语义对，不依赖厂商默认调色。W01 在锁定的 Element Plus 版本上检查 Select、DatePicker、Dialog、Drawer、Message 与 Button 的实际 DOM/状态；依赖变化时相应回归，不能仅凭变量存在就声称全部无障碍。

禁止在业务页使用一长串 `:deep(.el-...)` 覆盖。确需覆盖的厂商选择器集中在此桥接文件、注明所服务的公共组件；不要用全局 `!important` 强压控件所有状态。

### 11.3 图表实现契约

`readChartTheme()` 从 `getComputedStyle(document.documentElement)` 读取 `--vl-chart-1` 等已解析变量，返回 palette/text/grid/fontFamily；空值应报开发错误而不是回落到另一套色值。

`useChart.ts` 统一管理 `init/setOption/resize/dispose`。使用 ResizeObserver 监听容器，不仅监听窗口；路由离开时 dispose，重新可见后 resize。按需导入时注册使用的图表、组件、ARIA 与 renderer；Apache ECharts 的按需导入并不会自动带上所有组件。[S8][S9]

```ts
// apps/web/src/lib/chart-theme.ts 的可复用基线
export function readChartTheme() {
  const css = getComputedStyle(document.documentElement)
  const read = (name: string): string => {
    const value = css.getPropertyValue(name).trim()
    if (!value) throw new Error(`Missing design token: ${name}`)
    return value
  }
  return {
    palette: Array.from({ length: 6 }, (_, i) => read(`--vl-chart-${i + 1}`)),
    text: read('--vl-color-text-secondary'),
    grid: read('--vl-color-border'),
    fontFamily: read('--vl-font-sans'),
  }
}
```

图表 options 至少设置 `aria.enabled=true`、`animation` 跟随 reduced motion、`tooltip.renderMode='richText'`，系列 `smooth=false`、`connectNulls=false`。使用 `echarts/core` 时显式注册 `AriaComponent` 和需要的 renderer；不能只设置 enabled 却漏注册。图表文字摘要和数据表从同一 API 结果创建，不解析 canvas 再推算统计。

### 11.4 测试定位符契约

沿用工程计划所有原有 `data-testid`。新增：`app-shell`、`page-title`、`demo-notice`、`metric-pending-risks`、`metric-overdue-tasks`、`metric-active-tasks`、`metric-valid-feedback`、`metric-scope`、`evidence-panel`、`evidence-drawer`、`evidence-close`、`ai-provenance`、`chart-data-toggle`、`chart-data-table`、`async-error`、`async-empty`、`stale-data-notice`。

每个 MetricCard 内 `metric-value` 与 `metric-scope` 可重复，但测试必须先定位外层具体卡片。行元素额外带 `data-resource-id`，不以“第一行”代替指定主题。公开 UI 名称可用 getByRole 验证；业务关键定位符不依赖厂商内部 class。

<a id="f12"></a>
## 12. 测试、视觉审查与交付门禁

### 12.1 要创建的文件

| 文件（`apps/web/` 内） | 目的 | 责任工作包 |
|---|---|---|
| `tests/unit/design-tokens.spec.ts` | 颜色值、关键对比度、tokens 使用 | W01 |
| `tests/unit/ui-status.spec.ts` | 业务 enum 显示与未知来源安全回退 | W14/W16 |
| `tests/unit/metric-card.spec.ts` | 零/缺失/失败/范围说明 | W12 |
| `tests/unit/evidence-quote.spec.ts` | 纯文本、emoji offset、引用重构 | W12/W13 |
| `tests/e2e/ui-fixtures.ts` | 纯合成 UI 状态 fixture 与状态路由拦截 | W01 基础，后续工作包补齐 |
| `tests/e2e/overview-ui.spec.ts` | 指标顺序、范围、加载错误 | W12 |
| `tests/e2e/evidence-ui.spec.ts` | 桌面/窄屏、键盘与返回上下文 | W12/W20 |
| `tests/e2e/accessibility.spec.ts` | axe 自动扫描＋焦点/键盘断言 | W20 |
| `tests/e2e/visual.spec.ts` | 固定数据的截图比较 | W20 |
| `scripts/check-style-tokens.mjs` | 防止业务代码新增硬编码颜色 | W01 |

`ui-fixtures.ts` 与原工程的真实后端 `fixtures.ts` 分开：前者可为纯 UI 测试拦截 API，后者测试真实登录/数据库链路。命名和报告必须区分 `ui-mock` 与 `integration-real`，不能互相背书。

### 12.2 可复制的颜色对比度测试

```ts
// apps/web/tests/unit/design-tokens.spec.ts
import { readFileSync } from 'node:fs'
import { expect, test } from 'vitest'

const css = readFileSync(new URL('../../src/styles/tokens.css', import.meta.url), 'utf8')
function color(token: string): string {
  const value = css.match(new RegExp(`${token}:\\s*(#[0-9a-fA-F]{6})\\s*;`))?.[1]
  if (!value) throw new Error(`Missing hex token: ${token}`)
  return value
}
function luminance(hex: string): number {
  const channels = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
  const linear = channels.map(c => c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
  return linear[0]! * 0.2126 + linear[1]! * 0.7152 + linear[2]! * 0.0722
}
function contrast(fg: string, bg: string): number {
  const a = luminance(color(fg)), b = luminance(color(bg))
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
}
const cases: [string, string, number][] = [
  ['--vl-color-text', '--vl-color-surface', 4.5],
  ['--vl-color-text-secondary', '--vl-color-surface', 4.5],
  ['--vl-color-text-muted', '--vl-color-bg', 4.5],
  ['--vl-color-surface', '--vl-color-brand', 4.5],
  ['--vl-color-surface', '--vl-color-brand-hover', 4.5],
  ['--vl-color-warning', '--vl-color-warning-bg', 4.5],
  ['--vl-color-danger', '--vl-color-danger-bg', 4.5],
  ['--vl-color-success', '--vl-color-success-bg', 4.5],
  ['--vl-color-info', '--vl-color-info-bg', 4.5],
  ['--vl-color-border-control', '--vl-color-surface', 3],
  ['--vl-color-border-control', '--vl-color-bg', 3],
]
test.each(cases)('%s on %s >= %s', (fg, bg, minimum) => {
  expect(contrast(fg, bg)).toBeGreaterThanOrEqual(minimum)
})
```

这是文档内的测试基线，不代表仓库中已存在文件或已经运行 Vitest。数值测试覆盖指定纯色对，不覆盖透明叠加、所有控件、字号、焦点与读屏。

### 12.3 浏览器测试约定

固定时区 `Asia/Shanghai`、语言 `zh-CN`、浏览器版本、操作系统/字体环境、视口与合成数据。截图用 1440×900、768×1024、375×812；另做 320px 重排与真实浏览器 200%/400% 缩放人工检查，不把调 viewport 等同所有缩放行为。

代表截图为工作台、主题证据、复盘详情和 StyleLab 状态页。用 `expect(page).toHaveScreenshot()`，首次基线由人工核准；后续失败不能自动更新截图来“通过”。固定动画、日期和异步数据后再截图；不同系统字体会影响截图，需要在相同 CI 环境生成/比较。[S11]

`accessibility.spec.ts` 使用 `@axe-core/playwright`，扫描首屏与打开抽屉/弹窗后的状态，选择适用的 WCAG 2 A/AA、2.1 AA、2.2 AA 标签。自动扫描不能证明全部 WCAG 合规，仍需手工检查键盘、焦点、长内容与可理解性。[S5]

目标脚本由 W01/W20 创建后使用：

```bash
npm --prefix apps/web run typecheck
npm --prefix apps/web run lint:style
npm --prefix apps/web run test:unit -- --run
npm --prefix apps/web run test:ui
npm --prefix apps/web run test:a11y
npm --prefix apps/web run test:visual
npm --prefix apps/web run build
```

`test:ui` 对应 overview-ui/evidence-ui；`test:a11y` 对应 accessibility；`test:visual` 对应 visual。与原 `test:e2e` 的真实 API 闭环分开运行。UI 测试及组件实验页不向付费模型发送请求。

### 12.4 24 项 UI 验收

以下 UI-01—UI-24 是工程计划第 13.6 节的同编号要求；不得创建另一套不同编号的清单。

| ID | 检查点 | 失败判据 |
|---|---|---|
| UI-01 | 语义 tokens 与浅橙主题 | 业务页硬编码新颜色；旧青绿/蓝色主题泄漏 |
| UI-02 | 外壳与断点 | 320/375/768/1024/1280/1440/1920 任一关键操作不可达 |
| UI-03 | 首页行动顺序与范围 | 四卡顺序错误；项目待办假称受反馈筛选影响 |
| UI-04 | 表格密度与导航 | 全部卡片化、只可鼠标整行点、正文被裁断 |
| UI-05 | 选中与返回上下文 | 查看证据后丢筛选、页码或原触发位置 |
| UI-06 | 侧栏/抽屉语义 | 桌面非模态锁背景；抽屉不锁焦点或显示两份内容 |
| UI-07 | 证据安全 | v-html、注入执行、Unicode offset 错位或引文拼接不一致 |
| UI-08 | 草稿与正式动作 | 生成即派发、负责人缺失却确认成功 |
| UI-09 | 风险/来源标签 | 候选冒充确认；needs_review=false 冒充人工审核 |
| UI-10 | 0/null/失败 | 任意两者被混为一态 |
| UI-11 | CPI/复盘显示 | 指数写概率、百分点写百分比、因果过度结论 |
| UI-12 | 表单校验 | 无 label、报错不定位、清空其他有效字段 |
| UI-13 | 空态分流 | 无数据/无结果/无权限共用假“0”页 |
| UI-14 | 进度与刷新 | 伪百分比、旧内容不标过期、轮询不断播报 |
| UI-15 | 错误与冲突 | 401/403/404/409/422/429/503 无具体分支；409 丢输入 |
| UI-16 | 上下文/隐私 | 快速切项目旧响应覆盖；URL/存储带敏感正文 |
| UI-17 | 图表可读 | 无单位/范围/文字摘要/数据表，仅凭颜色区分 |
| UI-18 | 图表生命周期 | 窄屏后变形、切页未 dispose、缺数据连线 |
| UI-19 | 权限显示 | 只隐藏按钮就视为安全；只读误导可执行 |
| UI-20 | 键盘与焦点 | Tab 到不了、Esc 无效、返回丢焦点、粘性栏遮住焦点 |
| UI-21 | 对比度 | 关键纯色对或实际组件文字/边界低于对应要求 |
| UI-22 | 控件目标 | 默认/触摸/行内按钮不符 40/44/32px 基线，且无评审例外 |
| UI-23 | 减少动效 | 用户要求 reduced motion 仍有非必要位移/图表动画 |
| UI-24 | 视觉基线与真实性 | 自动更新基线掩盖缺陷；mock 截图冒充真实业务验收 |

阻断项：权限/证据安全、错误状态冒充成功、无法操作、文字不可辨认、误导性的任务/效果结论。轻微阴影与间距偏差可记入已知问题，但需产品负责人明确接受，不自动豁免。

<a id="f13"></a>
## 13. 前端执行顺序与开发代理指令

先做 tokens/适配层/StyleLab → AppShell 与基础状态 → 导入向导 → 工作台和证据 → 风险/任务 → 复盘 → 视觉与键盘回归。不要先写完每页各自的 CSS，再最后统一主题。

工程计划中 W01、W05、W12、W14、W16、W18、W20 已增加相应工作量；总估算从 306 调整为 326 人时，并重新分配协作任务。**不能把额外前端规范当成无需工时的装饰要求。** 具体每人容量和剩余缓冲只在工程计划第 12 节维护。

```text
请先阅读 docs/engineering-plan.md 与 docs/frontend-style.md。
本次只实施指定 Web 工作包，不替换 Vue 3/Element Plus，不增加第二套 UI 库。

1. 盘点已有组件、tokens、测试和未提交修改，不覆盖仓库现有实现。
2. tokens.css 是颜色和尺寸唯一源，Element Plus 适配集中管理。
3. 全站是浅色极简工作台；Bento 只用于概览和复盘，不把任务表改成卡片墙。
4. 先确保状态/数据/权限正确，再实现尺寸、排版与视觉细节。
5. AI建议、规则候选、人工修订分开；没有审核事件不显示“人工已确认”。
6. 首页分析指标与项目级待办常显不同统计范围。
7. 不编造 API 字段、证据、百分比、任务完成和企业试点效果。
8. 抽屉、表单、图表必须覆盖错误、窄屏、键盘和减少动效。
9. 按工作包建立测试；截图只能使用合成 fixture，真实闭环用真实 API 测试。
10. 结束报告改了哪些文件、实际执行命令、通过/失败、未验收事项和截图位置。
```

本规范未要求本次对话立即开发前端工程；这些代码和命令是后续实施基线。

<a id="f14"></a>
## 14. 来源、数值校核与变更管理

### 14.1 来源登记

所有尺寸、配色、页面排布和项目阈值属于本次设计决定；以下官方资料只支持注明的能力/准则，不是对诉源镜设计或实际效果的背书。外部链接核对日期：2026-09-09。

| 编号 | 来源与定位 | 本文使用范围 |
|---|---|---|
| R1 | 当前上传《诉源镜 VoiceLens 项目计划书与实施方案 V1.0》，第 6、7、12 页 | 六步流程、证据优先、页面与人工确认 |
| E1 | 当前对话 `VoiceLens_Web_工程开发计划.md` v1.0，第 2、6、7、8、9 节 | 技术栈、枚举、接口、统计、路由 |
| U1 | 当前对话用户“可以，按照你的推荐设计” | 批准现代极简工作台＋Bento 概览＋温和品牌表达 |
| D1 | 本文及配套工程计划 v1.1 | 本次实现决定；不冒称出自原书 |
| S1 | Element Plus Theming：`https://element-plus.org/en-US/guide/theming.html` | CSS variables、主题定制 |
| S2 | W3C 1.4.3：`https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html` | 文本对比度及适用例外 |
| S3 | W3C 1.4.11：`https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html` | 控件/图形非文本对比 |
| S4 | W3C 2.5.8：`https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html` | 指针目标最小尺寸与例外 |
| S5 | Playwright Accessibility：`https://playwright.dev/docs/accessibility-testing` | axe 集成、自动检测局限 |
| S6 | WAI-ARIA Modal Dialog：`https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/` | 模态背景、焦点、关闭与返回 |
| S7 | W3C 1.4.10：`https://www.w3.org/WAI/WCAG22/Understanding/reflow.html` | 320px 等效重排与二维内容例外 |
| S8 | ECharts ARIA：`https://echarts.apache.org/handbook/en/best-practices/aria/` | ARIA 说明与可视区分 |
| S9 | ECharts Import：`https://echarts.apache.org/handbook/en/basics/import/` | 按需注册组件/renderer |
| S10 | IBM Carbon AI label：`https://carbondesignsystem.com/components/ai-label/usage/` | AI 来源标识应连接解释，不作装饰 |
| S11 | Playwright Visual comparisons：`https://playwright.dev/docs/test-snapshots` | 截图基线与环境影响 |
| S12 | Linear Design Refresh：`https://linear.app/now/behind-the-latest-design-refresh` | 降低视觉噪声的方向参考；不复制页面或尺寸 |

### 14.2 本次做过的数值校核

采用 sRGB 相对亮度公式计算下列**不透明纯色**组合；结果保留三位小数用于阅读，是否通过按未四舍五入值判断。此表由本次文档生成过程计算，不是浏览器整站可访问性测试，也不是已完成 WCAG 认证。

| 组合 | 前景/背景 | 对比度 | 检查阈值 | 数值结果 |
|---|---|---:|---:|---|
| 主正文/白底 | `#1D1D1F` / `#FFFFFF` | 16.830∶1 | 4.5∶1 | 达标 |
| 次正文/白底 | `#515154` / `#FFFFFF` | 7.910∶1 | 4.5∶1 | 达标 |
| 辅助文字/页面底 | `#6E6E73` / `#FBFBFD` | 4.907∶1 | 4.5∶1 | 达标 |
| 辅助文字/次级底 | `#6E6E73` / `#F5F5F7` | 4.658∶1 | 4.5∶1 | 达标 |
| 白字/主按钮 | `#FFFFFF` / `#C2410C` | 5.178∶1 | 4.5∶1 | 达标 |
| 白字/主按钮hover | `#FFFFFF` / `#9A3412` | 7.307∶1 | 4.5∶1 | 达标 |
| 白字/主按钮active | `#FFFFFF` / `#7C2D12` | 9.370∶1 | 4.5∶1 | 达标 |
| 成功标签 | `#2E7D32` / `#EDF7ED` | 4.670∶1 | 4.5∶1 | 达标 |
| 警告标签 | `#B45309` / `#FEF3E2` | 4.575∶1 | 4.5∶1 | 达标 |
| 危险标签 | `#B3261E` / `#FDECEA` | 5.716∶1 | 4.5∶1 | 达标 |
| 信息标签 | `#0B5EA8` / `#EAF3FD` | 5.891∶1 | 4.5∶1 | 达标 |
| 控件边界/白底 | `#8E8E93` / `#FFFFFF` | 3.261∶1 | 3∶1 | 达标 |
| 控件边界/页面底 | `#8E8E93` / `#FBFBFD` | 3.155∶1 | 3∶1 | 达标 |
| 图表系列1/白底 | `#EA580C` / `#FFFFFF` | 3.560∶1 | 3∶1 | 达标 |
| 图表系列2/白底 | `#0071E3` / `#FFFFFF` | 4.697∶1 | 3∶1 | 达标 |
| 图表系列3/白底 | `#2E7D32` / `#FFFFFF` | 5.127∶1 | 3∶1 | 达标 |
| 图表系列4/白底 | `#5856D6` / `#FFFFFF` | 5.650∶1 | 3∶1 | 达标 |
| 图表系列5/白底 | `#AF52DE` / `#FFFFFF` | 4.130∶1 | 3∶1 | 达标 |
| 图表系列6/白底 | `#0E7490` / `#FFFFFF` | 5.358∶1 | 3∶1 | 达标 |

> v1.1:上表为浅橙主题下重新计算的结果(2026-09-12),19 组全部达标;与 `tests/unit/design-tokens.spec.ts` 的 11 组断言一致。

正文与控件必须在真实页面重新检查 normal/hover/active/focus/disabled、popover、teleport、缩放与强制颜色模式；本次没有产品源码，因此没有声称这些浏览器测试已经通过。

### 14.3 变更流程

tokens 或关键组件变化时，同步更新本文版本、工程计划第 16.4 节、受影响工作包和 UI 验收。先改变量与组件，再改页面，不用局部补丁长期维持两套设计语言。

本版规范与工程计划共同冻结：浅色主题、224/64 外壳、12/8 圆角、14px 正文/16px 证据、行动优先首页、桌面证据侧栏/窄屏抽屉、明确的数据范围与人工操作边界。后续改变其中任一项，应写出理由和影响，不能以“最新流行”直接覆盖。
