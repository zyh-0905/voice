"""W22/§14.6 发布 manifest:commit、镜像 digest、迁移 head、依赖哈希、规格文档版本。

计划 14.6 要求「发布manifest记录commit、镜像digest、schema版本、提示/规则版本、测试数据hash」。
本脚本覆盖前四项,并**诚实标注缺什么**:

- 提示词/规则版本/测试数据:三者都在仓库里,逐个记录 sha256 与版本标识;
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

# `from ops_common import ...` 只在以脚本方式运行时成立(`scripts/` 在 sys.path 上)。
# 被当模块导入时(pytest、将来的打包入口)会 ModuleNotFoundError——而报错发生在
# 导入这一行,看起来像「脚本不见了」。把补路径这一步写在导入之前,两种用法都成立。
# 无条件补一次:直接运行时 `__package__` 是 None,被当模块导入时是 'scripts'
# ——两种情况下 `ops_common` 都不在 sys.path 上,所以不能按 `__package__` 分支。
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from ops_common import (REPO_ROOT, OpsError, compose_cmd, migration_head, run, sha256_file,
                        write_json)

MANIFEST_VERSION = 1
SPEC_RE = re.compile(r"^(?P<name>.+)_v(?P<version>\d+\.\d+)\.md$")
BUILD_SERVICES = ("api", "worker", "relay", "watchdog", "web")


def _git(*args: str) -> str:
    result = run(["git", *args], cwd=REPO_ROOT)
    return (result.stdout or b"").decode("utf-8").strip()


def git_section() -> dict:
    """提交与 tag。git 不可用时**降级记录**,不抛异常。

    发布流水线里这个脚本可能跑在没有 git 的环境(精简镜像、从 tarball 解出来的
    工作区)。那时抛 FileNotFoundError 会让整份 manifest 生成不出来——而它能记的
    其余七项(规格文档、迁移、依赖、镜像、提示词、规则、测试数据)都还在。
    `available: false` 明确说明这一项为什么缺,而不是留一个空字段让人猜。
    """
    try:
        return {
            "available": True,
            "commit": _git("rev-parse", "HEAD"),
            "short": _git("rev-parse", "--short", "HEAD"),
            "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "describe": _git("describe", "--tags", "--always"),
            "tags_at_head": _git("tag", "--points-at", "HEAD").splitlines(),
            "dirty": bool(_git("status", "--porcelain")),
        }
    except OSError as exc:  # 二进制不存在:FileNotFoundError 是 OSError 的子类
        return {"available": False, "reason": f"git 不可用: {exc.strerror or exc}"}
    except OpsError as exc:
        return {"available": False, "reason": str(exc)}


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


def prompts_section() -> dict:
    """提示模板与规则策略的版本(8.5 / 8.4 / 14.6)。

    此前这里写死 null,并声称「仓库里没有 prompts/ 与 rules 版本文件」——而那些文件
    一直都在(`services/api/prompts/topic_v1.txt`、`configs/industry/ecommerce.yaml`)。
    manifest 因此说「提示模板无版本」,而 8.5 恰恰要求记录提示模板版本,且每次命名
    都用它。记录的准确性是这份产物唯一的用处。
    """
    prompt_files = sorted((REPO_ROOT / 'services' / 'api' / 'prompts').glob('*'))
    policy_path = REPO_ROOT / 'services' / 'api' / 'configs' / 'industry' / 'ecommerce.yaml'
    policy_id = None
    if policy_path.is_file():
        # policy_id 是规则集自己的版本标识(8.4):它随产物落库,所以 manifest 也要记
        for line in policy_path.read_text(encoding='utf-8').splitlines():
            if line.startswith('policy_id:'):
                policy_id = line.split(':', 1)[1].strip()
                break
    return {
        'files': [{'file': str(path.relative_to(REPO_ROOT)), 'bytes': path.stat().st_size,
                   'sha256': sha256_file_join([path])} for path in prompt_files if path.is_file()],
        'combined_sha256': sha256_file_join(prompt_files) if prompt_files else None,
        'rules': {
            'file': str(policy_path.relative_to(REPO_ROOT)),
            'policy_id': policy_id,
            'sha256': sha256_file_join([policy_path]) if policy_path.is_file() else None,
        },
    }


def test_data_section() -> dict:
    """固定合成测试数据集的 hash(13.1 / 14.6)。

    它是评估与黄金断言的输入,所以「这一版用的是哪份数据」必须可追溯。
    """
    path = REPO_ROOT / 'services' / 'api' / 'evaluation' / 'fixtures.json'
    if not path.is_file():
        return {'file': None, 'sha256': None}
    return {'file': str(path.relative_to(REPO_ROOT)), 'bytes': path.stat().st_size,
            'sha256': sha256_file_join([path])}


def _base_gaps() -> list:
    """环境相关的缺口写在最前面:它们随运行环境变化,不该和固定缺口混在一起。"""
    git = git_section()
    if git.get("available") is False:
        return [f"git 不可用,commit/tag 未记录({git.get('reason')})"]
    return []


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
        "prompts": prompts_section(),
        "rules_version": prompts_section()['rules'],
        "test_data": test_data_section(),
        "known_gaps": _base_gaps() + [
            "Python 依赖无锁文件(requirements.txt 是范围声明)",
            "本地构建镜像无 RepoDigest,需 push 到 registry 后重跑本脚本",
            "无固定的人工标注评估集(13.1 要求的约 300 条);现有 fixtures.json 只作路径冒烟",
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
