"""Validate the Compose contract used by local and CI deployments."""
from pathlib import Path
import sys

import yaml


def main() -> int:
    path = Path(__file__).resolve().parents[1] / "compose.yaml"
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
    print("compose.yaml validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())


