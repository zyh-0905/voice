"""Validate the Compose contract used by local and CI deployments."""
from pathlib import Path
import sys

import yaml


def main() -> int:
    path = Path(__file__).resolve().parents[1] / "compose.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    services = data.get("services") if isinstance(data, dict) else None
    required = {"api", "web", "postgres", "redis", "worker"}
    if not isinstance(services, dict) or not required <= services.keys():
        raise SystemExit("compose.yaml must define api, web, postgres, redis and worker services")
    web = services["web"]
    if web.get("build", {}).get("dockerfile") != "apps/web/Dockerfile":
        raise SystemExit("web Dockerfile is invalid")
    if web.get("ports") != ["8080:8080"]:
        raise SystemExit("web must expose port 8080")
    if web.get("depends_on", {}).get("api", {}).get("condition") != "service_healthy":
        raise SystemExit("web must depend on healthy api")
    for name in ("api", "worker"):
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
