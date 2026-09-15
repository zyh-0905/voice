"""Validate the Compose contract used by local and CI deployments."""
from pathlib import Path
import re
import sys

import yaml

REPO = Path(__file__).resolve().parents[1]

# 生产闸门(settings.py)读的开关。compose 里钉成字面量 = 焊死 .env 的覆盖入口,
# VOICELENS_ENV=production 永远到不了容器,全部闸门旁路(2026-09 的真实事故)。
GATE_SWITCHES = ("VOICELENS_ENV", "NAMING_MODE", "EMBEDDING_MODE",
                 "AUTH_INSECURE_DEV", "LOCAL_ACCOUNTS")
# 14.1:模型密钥只在 worker 进程;api 容器不得持有。
WORKER_ONLY_SECRETS = ("MODEL_API_KEY", "EMBEDDING_API_KEY")
# provider 在 worker 的流水线里读取;compose 不注入 = NAMING_MODE=provider 也拿不到,
# llm.py 静默降级 manual。
WORKER_PROVIDER_VARS = ("NAMING_MODE", "EMBEDDING_MODE", "MODEL_ENDPOINT", "MODEL_ID",
                        "MODEL_BASE_URL", "MODEL_PRICE_IN", "MODEL_PRICE_OUT")


def _readers_corpus() -> str:
    """compose.yaml + 后端/脚本源码的拼接文本(供「键有读者」检查)。

    validate-compose.py 自身除外:检查器源码里出现的键名不应算作读者。
    """
    parts = [(REPO / "compose.yaml").read_text(encoding="utf-8")]
    parts.extend(p.read_text(encoding="utf-8") for p in REPO.glob("services/api/app/**/*.py"))
    parts.extend(p.read_text(encoding="utf-8") for p in REPO.glob("scripts/*.py")
                 if p.name != "validate-compose.py")
    parts.extend(p.read_text(encoding="utf-8") for p in REPO.glob("apps/web/src/**/*.ts"))
    return "\n".join(parts)


def _parse_env_keys(path: Path) -> list[str]:
    keys = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        keys.append(line.split("=", 1)[0].strip())
    return keys


def main() -> int:
    path = REPO / "compose.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    services = data.get("services") if isinstance(data, dict) else None
    # §14.2 的目标服务集合;relay/watchdog 漏掉会让部署少了 outbox 投递与租约恢复
    required = {"api", "web", "postgres", "redis", "worker", "migrate", "relay", "watchdog"}
    if not isinstance(services, dict) or not required <= services.keys():
        raise SystemExit(
            "compose.yaml must define api, web, postgres, redis, worker, migrate, relay and watchdog services"
        )
    # 迁移必须先行:模型新增列不会被 create_all 补上
    for name in ("api", "worker", "relay", "watchdog"):
        if services[name].get("depends_on", {}).get("migrate", {}).get("condition") != "service_completed_successfully":
            raise SystemExit(f"{name} must wait for the migrate service to complete")
    web = services["web"]
    if web.get("build", {}).get("dockerfile") != "apps/web/Dockerfile":
        raise SystemExit("web Dockerfile is invalid")
    if web.get("ports") != ["8080:8080"]:
        raise SystemExit("web must expose port 8080")
    if web.get("depends_on", {}).get("api", {}).get("condition") != "service_healthy":
        raise SystemExit("web must depend on healthy api")
    # §14.2:api/worker/relay/watchdog 复用同一 Python 镜像
    for name in ("api", "worker", "relay", "watchdog"):
        build = services[name].get("build", {})
        if build.get("context") != "." or build.get("dockerfile") != "services/api/Dockerfile":
            raise SystemExit(f"{name} build context/dockerfile is invalid")
    for name in ("api", "postgres", "redis"):
        if not services[name].get("healthcheck", {}).get("test"):
            raise SystemExit(f"{name} must define a healthcheck")

    # —— 闸门开关必须可覆盖 ——
    api_env = services["api"].get("environment", {}) or {}
    for key in GATE_SWITCHES:
        value = str(api_env.get(key, ""))
        if not value.startswith("${"):
            raise SystemExit(
                f"api service must configure {key} as an interpolated ${{VAR:-default}}, "
                f"not the literal {value!r}: a literal pins the value and bypasses "
                "every production gate in app/settings.py"
            )
    # —— 14.1 密钥隔离 ——
    worker_env = services["worker"].get("environment", {}) or {}
    for key in WORKER_ONLY_SECRETS:
        if key in api_env:
            raise SystemExit(f"api service must not hold {key}: model secrets go only to the worker (14.1)")
        if key not in worker_env:
            raise SystemExit(f"worker service must inject {key} (14.1: providers run in the worker)")
    for key in WORKER_PROVIDER_VARS:
        if key not in worker_env:
            raise SystemExit(
                f"worker service must inject {key}: the pipeline reads it in the worker; "
                "NAMING_MODE=provider silently degrades to manual without it"
            )
    # —— web 构建模式必须是显式开关 ——
    build_args = (web.get("build", {}) or {}).get("args", {}) or {}
    if "VITE_USE_MOCK" not in build_args:
        raise SystemExit(
            "web build must pass VITE_USE_MOCK: without it the image silently defaults "
            "to the mock client and never calls the backend"
        )
    # —— 哑配置检查:样例文件里的每个键必须有读者 ——
    # 零读者的键配了不生效——「改了有效」的错觉比缺失更糟(MODEL_REVISION 前例:
    # 出现在 .env.example 注释里,全仓没有任何代码读它)。
    corpus = _readers_corpus()
    for name in (".env.example", ".env.production.example", "apps/web/.env.example"):
        for key in _parse_env_keys(REPO / name):
            if not re.search(rf"\b{re.escape(key)}\b", corpus):
                raise SystemExit(
                    f"{name} defines {key} but nothing reads it "
                    "(searched compose.yaml, services/api/app, scripts, apps/web/src): "
                    "remove the key or wire a reader"
                )
    print("compose.yaml validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
