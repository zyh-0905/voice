# VoiceLens Web MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a runnable Vue 3 + TypeScript MVP slice with the VoiceLens workbench shell, project selection, overview metrics, evidence drawer, and replaceable mock API contracts.

**Architecture:** A Vite SPA uses Vue Router and Pinia with a small typed API client. Mock data is isolated behind the same client interface so FastAPI `/api/v1` can replace it later. Tokens and Element Plus adaptation live in global CSS; feature views consume semantic components and explicit loading/error/empty states.

**Tech Stack:** Vue 3, TypeScript, Vite, Vue Router, Pinia, Element Plus, Vitest.

**Spec:** `VoiceLens_Web_工程开发计划_v1.1.md`, `VoiceLens_Web_前端风格规范_v1.0.md`

## Global Constraints

- Use Vue 3 Composition API with `<script setup>` and strict TypeScript.
- Keep a light, warm green workbench theme; use CSS tokens as the single source of color and spacing values.
- Keep Bento layout for overview cards only; task lists remain tables/lists.
- Every async surface exposes loading, empty, error, and stale-data states.
- Evidence text is rendered as plain text with safe offsets; no `v-html`.
- Mock/demo content is visibly labeled and never presented as confirmed human review.

### Task 1: Scaffold the web application

**Files:** `apps/web/package.json`, `apps/web/index.html`, `apps/web/src/main.ts`, `apps/web/src/App.vue`, `apps/web/src/router/index.ts`, `apps/web/src/styles/tokens.css`, `apps/web/src/styles/base.css`, `apps/web/src/styles/element-theme.css`, `apps/web/src/stores/session.ts`, `apps/web/src/stores/project.ts`.

- [ ] Create the Vite project files and install scripts for `dev`, `build`, `typecheck`, `test:unit`.
- [ ] Define typed session/project stores with a demo user and selectable demo project.
- [ ] Add global tokens for colors, spacing, radii, typography, focus, and chart palette; adapt Element Plus variables from those tokens.
- [ ] Add router routes `/login`, `/projects`, `/overview`, redirecting `/` to `/overview`.
- [ ] Run `npm --prefix apps/web install`, then `npm --prefix apps/web run build`.

### Task 2: Implement the application shell and navigation

**Files:** `apps/web/src/layouts/AppShell.vue`, `apps/web/src/components/common/PageHeader.vue`, `apps/web/src/components/common/StatusBadge.vue`, `apps/web/src/views/LoginView.vue`, `apps/web/src/views/ProjectsView.vue`.

- [ ] Build responsive sidebar/header shell with `data-testid="app-shell"` and accessible navigation.
- [ ] Add login/demo notice and project picker flow; preserve selected project in Pinia.
- [ ] Add keyboard-visible focus styles and 320px reflow behavior.
- [ ] Verify with a unit test for route/store behavior.

### Task 3: Build overview dashboard and evidence interaction

**Files:** `apps/web/src/api/client.ts`, `apps/web/src/api/mock.ts`, `apps/web/src/types/domain.ts`, `apps/web/src/views/OverviewView.vue`, `apps/web/src/components/common/MetricCard.vue`, `apps/web/src/components/evidence/EvidencePanel.vue`, `apps/web/src/components/evidence/EvidenceDrawer.vue`.

- [ ] Define typed `Overview`, `Metric`, and `EvidenceQuote` contracts and mock client methods.
- [ ] Render four ordered overview metrics with explicit scope labels and pending/error/empty states.
- [ ] Add evidence panel and drawer with open/close, Escape handling, focus return, and plain-text quote highlighting.
- [ ] Display `data-testid="demo-notice"`, `metric-pending-risks`, `metric-overdue-tasks`, `metric-active-tasks`, `metric-valid-feedback`, `evidence-panel`, `evidence-drawer`, `evidence-close`, and `ai-provenance`.
- [ ] Add Vitest coverage for metric state mapping and safe quote rendering.

### Task 4: Verify and document the slice

**Files:** `apps/web/tests/unit/*.spec.ts`, `README.md`.

- [ ] Add tests for token presence/contrast, status fallback, metric states, and evidence quote offsets.
- [ ] Run `npm --prefix apps/web run typecheck`, `npm --prefix apps/web run test:unit -- --run`, and `npm --prefix apps/web run build`.
- [ ] Document startup commands, demo-mode limitations, and the `/api/v1` replacement boundary.
