"""Validate the Compose contract used by local and CI deployments."""
from pathlib import Path
import sys

import yaml


def main() -> int:
    path = Path(__file__).resolve().parents[1] / "compose.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    services = data.get("services") if isinstance(data, dict) else None
    required = {"api", "postgres", "redis", "worker"}
    if not isinstance(services, dict) or not required <= services.keys():
        raise SystemExit("compose.yaml must define api, postgres, redis and worker services")
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
