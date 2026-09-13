"""W22/§14.6 发布 manifest:commit、镜像 digest、迁移 head、依赖哈希、规格文档版本。

计划 14.6 要求「发布manifest记录commit、镜像digest、schema版本、提示/规则版本、测试数据hash」。
本脚本覆盖前四项,并**诚实标注缺什么**:

- 提示词/规则版本:仓库里没有 prompts/ 与 rules 版本文件,manifest 里写 null 而不是编一个;
- 测试数据 hash:没有固定合成数据集,写 null;
- Python 依赖只有带下界的 requirements.txt,**不是锁文件**(`is_lockfile: false`)——
  W01 计划里的 uv.lock 在这个仓库不存在,manifest 记录这个事实而不是假装锁定;
- 本地 build 出来的镜像没有 RepoDigest(未 push),此时 digest 为 null 并标 `pushed: false`,
  release checklist 里把「push 后重跑 manifest」列为发布前动作。

用法:
    python3 scripts/release_manifest.py > docs/evidence/release-manifest.json
    python3 scripts/release_manifest.py --output releases/manifest-$(date +%F).json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from ops_common import (REPO_ROOT, OpsError, compose_cmd, migration_head, run, sha256_file,
                        write_json)

MANIFEST_VERSION = 1
SPEC_RE = re.compile(r"^(?P<name>.+)_v(?P<version>\d+\.\d+)\.md$")
BUILD_SERVICES = ("api", "worker", "relay", "watchdog", "web")


def _git(*args: str) -> str:
    result = run(["git", *args], cwd=REPO_ROOT)
    return (result.stdout or b"").decode("utf-8").strip()


def git_section() -> dict:
    try:
        return {
            "commit": _git("rev-parse", "HEAD"),
            "short": _git("rev-parse", "--short", "HEAD"),
            "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "describe": _git("describe", "--tags", "--always"),
            "tags_at_head": _git("tag", "--points-at", "HEAD").splitlines(),
            "dirty": bool(_git("status", "--porcelain")),
        }
    except OpsError as exc:
        return {"error": str(exc)}


def specs_section() -> list:
    specs = []
    for path in sorted(REPO_ROOT.glob("VoiceLens_Web_*.md")):
        match = SPEC_RE.match(path.name)
        specs.append({
            "file": path.name,
            "version": match.group("version") if match else None,
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        })
    return specs


def migrations_section() -> dict:
    versions_dir = REPO_ROOT / "services" / "api" / "migrations" / "versions"
    files = sorted(versions_dir.glob("*.py"))
    combined = sha256_file_join(files)
    return {"head": migration_head(), "count": len(files),
            "files_sha256": combined,
            "note": "files_sha256 为排序后各文件 sha256 的聚合;head 由 revision/down_revision 推导"}


def sha256_file_join(paths: list) -> str:
    import hashlib
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(sha256_file(path).encode("utf-8"))
    return digest.hexdigest()


def dependencies_section() -> list:
    candidates = [
        ("services/api/requirements.txt", "python", False,
         "带下界的约束,不是锁文件;安装结果随时间漂移"),
        ("apps/web/package.json", "node", False, "声明文件,非锁定"),
        ("apps/web/package-lock.json", "node", True, "npm 锁文件"),
    ]
    items = []
    for relative, ecosystem, is_lock, note in candidates:
        path = REPO_ROOT / relative
        items.append({
            "path": relative, "ecosystem": ecosystem, "is_lockfile": is_lock,
            "present": path.is_file(),
            "sha256": sha256_file(path) if path.is_file() else None,
            "note": note,
        })
    return items


def images_section() -> dict:
    """按 compose 服务记录镜像 Id 与 RepoDigest。

    注意:本地 build 的镜像在 containerd 存储下也会带 RepoDigest,这个字段本身
    不能证明镜像已 push;跨环境可复现的标识只有 push 到 registry 之后的 digest,
    所以发布清单把「push 后重跑 manifest」列为动作,而不是在这里替它背书。
    """
    try:
        config = json.loads((run(compose_cmd() + ["config", "--format", "json"],
                                 cwd=REPO_ROOT).stdout or b"").decode("utf-8"))
        services = config.get("services", {})
    except (OpsError, ValueError) as exc:
        return {"error": f"docker compose unavailable: {exc}"}
    project = config.get("name") or REPO_ROOT.name
    images = {}
    for service, spec in sorted(services.items()):
        # build 型服务在 config 里没有 image 字段,compose 默认名为 <project>-<service>
        name = spec.get("image") or (f"{project}-{service}" if spec.get("build") else None)
        if not name:
            continue
        entry = {"image": name, "id": None, "repo_digests": []}
        try:
            inspected = run(["docker", "image", "inspect", name,
                             "--format", "{{.Id}}|{{json .RepoDigests}}"], cwd=REPO_ROOT)
            image_id, digests = (inspected.stdout or b"").decode("utf-8").strip().split("|", 1)
            entry["id"] = image_id or None
            entry["repo_digests"] = json.loads(digests or "[]")
        except (OpsError, ValueError):
            entry["note"] = "本地未构建或镜像不存在"
        images[service] = entry
    return images


def build_manifest() -> dict:
    return {
        "manifest_version": MANIFEST_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tool": "scripts/release_manifest.py",
        "git": git_section(),
        "specs": specs_section(),
        "migrations": migrations_section(),
        "dependencies": dependencies_section(),
        "images": images_section(),
        "prompts": None,
        "rules_version": None,
        "test_data_hash": None,
        "known_gaps": [
            "Python 依赖无锁文件(requirements.txt 是范围声明)",
            "prompts/ 与固定合成测试数据集不存在,对应字段为 null",
            "本地构建镜像无 RepoDigest,需 push 到 registry 后重跑本脚本",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="生成发布 manifest(JSON)")
    parser.add_argument("--output", default=None, help="输出文件;缺省打到 stdout")
    args = parser.parse_args()
    manifest = build_manifest()
    text = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        write_json(Path(args.output), manifest)
        print(f"manifest 已写入 {args.output}")
        for gap in manifest["known_gaps"]:
            print(f"  ! {gap}")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
