#!/usr/bin/env bash
# 一条命令跑完全部门禁(工程计划 §14.3;发布清单 docs/release-checklist.md §2)。
#
# 为什么要这个脚本:门禁命令散在三处——CI 的 ci.yml、发布清单的表格、README——
# 而它们用的是**不同的路径**(CI 在 runner 上装依赖,清单用 Docker 镜像)。跑的人
# 每次都要拼一遍,拼错的典型后果不是报错而是**静默少跑**:比如忘了给
# DATABASE_URL,需要真库的 15 条用例会 skip,而套件整体仍然是绿的。
#
# 所以本脚本的规矩是:**跳过要显式说出来**。任何 skip 都在末尾计入「未验证」,
# 并以非零码退出——「没跑」和「跑过且通过」不能长成同一个样子。
#
# 用法:
#     bash scripts/check-all.sh              # 全部
#     bash scripts/check-all.sh backend      # 只跑后端(另有 schema/frontend/e2e/
#                                            #        real_api/production_render)
#     FAST=1 bash scripts/check-all.sh       # 跳过需要浏览器的 E2E
#
# 前置:
#   - 后端:`.venv`(见下)或 Docker
#   - 真库用例、schema 闸门与 real-api 套件:需要一个可达的 PostgreSQL:
#       docker compose -f compose.yaml -f compose.e2e.yaml up -d postgres
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ONLY="${1:-}"
FAST="${FAST:-0}"
FAILED=()
UNVERIFIED=()
PG_PORT="${PG_PORT:-5433}"

say()  { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }
ok()   { printf '\033[32m  ✓ %s\033[0m\n' "$*"; }
bad()  { printf '\033[31m  ✗ %s\033[0m\n' "$*"; FAILED+=("$*"); }
skip() { printf '\033[33m  ⊘ %s\033[0m\n' "$*"; UNVERIFIED+=("$*"); }

want() { [ -z "$ONLY" ] || [ "$ONLY" = "$1" ]; }

# —— 后端解释器:优先本地 venv,没有就回落到 Docker ——
#
# Docker 路径**必须重新 build**:api 镜像烘焙源码、没有 volume 挂载,不重建就会
# 用旧代码跑出绿色的结果(这条踩过不止一次)。本地 venv 没有这个问题,也快得多
# (整套 20 秒 vs 构建镜像数分钟),所以有 venv 就用 venv。
PY=""
if [ -x "$REPO_ROOT/.venv/bin/python" ]; then
  PY="$REPO_ROOT/.venv/bin/python"
elif [ -x /usr/bin/python3 ]; then
  if /usr/bin/python3 -c 'import fastapi' 2>/dev/null; then
    PY="$(command -v python3)"
  fi
fi

backend() {
  say "后端 pytest"
  local pg_url="postgresql+psycopg://voicelens:voicelens@127.0.0.1:${PG_PORT}/voicelens"
  if ! docker compose -f compose.yaml -f compose.e2e.yaml exec -T postgres \
       pg_isready -U voicelens >/dev/null 2>&1; then
    skip "真库用例(PostgreSQL 不可达;起库见本脚本头部说明)"
    pg_url=""
  fi

  # 环境变量用数组拼:`${var:+A="x"}` 这类展开会原样带上引号,传给 pytest 的
  # DATABASE_URL 就成了 `"postgresql://…"`(带字面引号),连不上且报错难懂。
  local out
  if [ -n "$PY" ]; then
    local -a cmd=(env PYTHONPATH=services/api:. AUTH_REQUIRED=false USE_DATABASE=0)
    [ -n "$pg_url" ] && cmd+=("DATABASE_URL=$pg_url")
    cmd+=("$PY" -m pytest services/api/tests -q)
  else
    say "  本地 .venv 不存在,回落到 Docker(需先重建镜像)"
    docker compose build api >/dev/null 2>&1 || { bad "docker compose build api"; return; }
    local -a cmd=(docker compose run --rm -e AUTH_REQUIRED=false -e USE_DATABASE=0)
    [ -n "$pg_url" ] && cmd+=(-e 'DATABASE_URL=postgresql+psycopg://voicelens:voicelens@postgres:5432/voicelens')
    cmd+=(api sh -c 'PYTHONPATH=/app/services/api python -m pytest services/api/tests -q')
  fi

  if out="$("${cmd[@]}" 2>&1 | tail -3)"; then echo "$out" | tail -2; ok "后端套件"; else echo "$out"; bad "后端套件"; fi
}

frontend() {
  say "前端门禁"
  # 失败时必须把输出打出来:此前一律丢进 /dev/null,于是只知道「typecheck 挂了」,
  # 还得手动重跑一次才知道挂在哪儿。少打的那几行,换来的是一次多余的往返。
  local gate out status
  for gate in lint:style typecheck build; do
    out="$(npm --prefix apps/web run "$gate" 2>&1)"
    status=$?
    if [ "$status" -eq 0 ]; then
      ok "$gate"
    else
      printf '%s\n' "$out" | grep -vE '^\s*$' | tail -15
      bad "$gate"
    fi
  done
  # 判定用退出码,用例数只作展示。**不要**用 `grep -E 'Tests +[0-9]'` 当判定:
  # vitest 的计数行里夹着 ANSI 转义(`Tests \e[22m\e[1m\e[32m112 passed`),
  # 数字前面不是空格而是转义序列,正则匹配不到 → grep 非零 → 明明全过却报失败。
  local unit status n
  unit="$(npm --prefix apps/web run test:unit -- --run 2>&1)"
  status=$?
  if [ "$status" -ne 0 ]; then
    printf '%s\n' "$unit" | tail -15
    bad "test:unit"
  else
    n="$(printf '%s\n' "$unit" | sed 's/\x1b\[[0-9;]*m//g' | grep -oE 'Tests +[0-9]+ passed' | head -1)"
    ok "test:unit — ${n:-通过}"
  fi
}

e2e() {
  if [ "$FAST" = "1" ]; then skip "E2E 与视觉基线(FAST=1)"; return; fi
  say "E2E(mock)+ 视觉基线"
  local out
  # 视觉基线**不得**自动覆盖:失败就人工核准,不给 --update-snapshots 的捷径
  if out="$(npm --prefix apps/web run test:e2e -- --project=chromium --workers=1 2>&1 | tail -3)"; then
    echo "$out" | tail -1; ok "E2E"
  else
    echo "$out"; bad "E2E(视觉基线需人工核准,不要 --update-snapshots)"
  fi
}

real_api() {
  if [ "$FAST" = "1" ]; then skip "real-api 闭环(FAST=1)"; return; fi
  say "真实 API 闭环(真 PostgreSQL)"
  # 镜像烘焙源码:改了 services/api 就必须重建,否则测的是旧代码
  docker compose build api >/dev/null 2>&1 || true
  docker build -f services/api/Dockerfile -t voice-api:latest . >/dev/null 2>&1 \
    || { skip "real-api(voice-api 镜像构建失败)"; return; }
  local out
  if out="$(npm --prefix apps/web run test:e2e:real 2>&1 | tail -3)"; then
    echo "$out" | tail -1; ok "real-api"
  else
    echo "$out"; bad "real-api"
  fi
}

# 全新库迁移闸门:此前只在 CI 里跑。「模型有列、迁移没有」这类缺陷,内存仓储与
# create_all 都看不见(前者不校验约束,后者直接按模型补表),只有真升一次
# alembic 才会炸——历史上「全新库无法迁移」正是阻断级缺陷,本地一键门禁却是绿的。
schema_gate() {
  say "全新库 schema 闸门(alembic upgrade head)"
  if [ -z "$PY" ]; then skip "schema 闸门(无本地 Python 解释器)"; return; fi
  if ! docker compose -f compose.yaml -f compose.e2e.yaml exec -T postgres \
       pg_isready -U voicelens >/dev/null 2>&1; then
    skip "schema 闸门(PostgreSQL 不可达;起库见本脚本头部说明)"; return
  fi
  local admin="postgresql+psycopg://voicelens:voicelens@127.0.0.1:${PG_PORT}"
  # 库名沿用测试前缀约定(conftest / e2e_server):即使连到不相干的实例也拦得住
  local db="voicelens_test_checkall"
  docker compose -f compose.yaml -f compose.e2e.yaml exec -T postgres \
    psql -U voicelens -d postgres \
    -c "DROP DATABASE IF EXISTS $db" -c "CREATE DATABASE $db" >/dev/null 2>&1 \
    || { bad "schema 闸门:建库失败"; return; }
  local out current
  out="$( (cd services/api && env DATABASE_URL="$admin/$db" "$PY" -m alembic -c alembic.ini upgrade head) 2>&1 )"
  current="$( (cd services/api && env DATABASE_URL="$admin/$db" "$PY" -m alembic -c alembic.ini current) 2>/dev/null )"
  if [ -z "$out" ] && printf '%s' "$current" | grep -q '(head)'; then
    ok "schema 闸门:全新库升到 head"
  else
    printf '%s\n' "$out" | tail -10
    bad "schema 闸门:全新库升不到 head"
  fi
  docker compose -f compose.yaml -f compose.e2e.yaml exec -T postgres \
    psql -U voicelens -d postgres -c "DROP DATABASE IF EXISTS $db" >/dev/null 2>&1 || true
}

# 生产口径渲染冒烟:用 .env.production.example 插值渲染 compose,断言生产闸门
# 真的到达容器。这是「VOICELENS_ENV=development 被钉死、闸门整体旁路」那类
# 缺陷的正向检查——静态看得到开关,渲染才知道值到了哪。
production_render() {
  say "生产渲染冒烟(--env-file .env.production.example)"
  if ! docker compose config --quiet >/dev/null 2>&1; then
    skip "生产渲染(Docker/compose 不可用)"; return
  fi
  local rendered
  rendered="$(docker compose --env-file .env.production.example config --format json 2>/dev/null)" \
    || { bad "生产渲染:docker compose config 失败"; return; }
  if printf '%s' "$rendered" | python3 -c '
import json, sys
cfg = json.load(sys.stdin)
api = cfg["services"]["api"]["environment"]
worker = cfg["services"]["worker"]["environment"]
assert api.get("VOICELENS_ENV") == "production", "api VOICELENS_ENV did not render to production"
assert api.get("NAMING_MODE") == "provider", "api NAMING_MODE did not render to provider"
assert "MODEL_API_KEY" not in api, "api container must not hold the model key (14.1)"
assert "MODEL_API_KEY" in worker, "worker must inject the model key (14.1)"
'; then
    ok "生产渲染:闸门口径到达容器,密钥只在 worker"
  else
    bad "生产渲染:生产口径没有到达容器"
  fi
}

say "compose 契约"
if python3 scripts/validate-compose.py >/dev/null 2>&1 && docker compose config --quiet 2>/dev/null; then
  ok "validate-compose + docker compose config"
else
  bad "compose 契约"
fi

want backend  && backend
want schema   && schema_gate
want frontend && frontend
want e2e      && e2e
want real_api && real_api
want production_render && production_render

say "汇总"
printf '  失败 %d 项' "${#FAILED[@]}"
[ "${#FAILED[@]}" -gt 0 ] && printf ':%s' "${FAILED[@]/#/$'\n'    - }"
printf '\n  未验证 %d 项' "${#UNVERIFIED[@]}"
[ "${#UNVERIFIED[@]}" -gt 0 ] && printf ':%s' "${UNVERIFIED[@]/#/$'\n'    - }"
printf '\n'

# 未验证也算不通过:这套门禁的价值全在「是否真的执行过」
if [ "${#FAILED[@]}" -gt 0 ] || [ "${#UNVERIFIED[@]}" -gt 0 ]; then
  printf '\n\033[31m未全绿\033[0m(未验证项同样不计通过)\n'
  exit 1
fi
printf '\n\033[32m全部通过\033[0m\n'
