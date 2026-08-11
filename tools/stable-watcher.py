#!/usr/bin/env python3
"""Detect the latest stable semver tag and optionally open a fail-closed candidate PR."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.request
from manifest import normalized_manifest, write_json

SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")

def ls_remote_details(url: str) -> tuple[dict[str, str], dict[str, str]]:
    output = subprocess.check_output(["git", "ls-remote", "--tags", url], text=True, timeout=60)
    direct, peeled = {}, {}
    for line in output.splitlines():
        commit, ref = line.split("\t", 1)
        if ref.endswith("^{}"):
            peeled[ref.removesuffix("^{}")] = commit
        else:
            direct[ref] = commit
    return direct, {ref: peeled.get(ref, commit) for ref, commit in direct.items()}


def ls_remote(url: str) -> dict[str, str]:
    return ls_remote_details(url)[1]


def blocked(report_path: Path, report: dict, reason: str) -> "None":
    report.update({"status": "BLOCKED", "reason": reason})
    write_json(report_path, report)
    print(f"BLOCKED {reason}")
    raise SystemExit(2)


def downstream_version(tag: str, previous_tag: str, previous_version: str) -> str:
    """Map x.y.z upstream to x.y.z.1, but only from a known-safe prior map."""
    old = previous_tag.removeprefix("v") + ".1"
    if previous_version != old:
        raise ValueError(
            f"downstream mapping is not safely automatable: {previous_tag}->{previous_version}"
        )
    return tag.removeprefix("v") + ".1"

def stable_tags(refs: dict[str, str]) -> list[tuple[tuple[int, int, int], str, str]]:
    result = []
    for ref, commit in refs.items():
        tag = ref.removeprefix("refs/tags/")
        match = SEMVER.fullmatch(tag)
        if match:
            result.append((tuple(map(int, match.groups())), tag, commit))
    return sorted(result)

parser = argparse.ArgumentParser()
parser.add_argument("--canonical", default="https://github.com/WordPress/wordpress-playground.git")
parser.add_argument("--mirror", default="https://feicode.com/WPFork/wordpress-playground-upstream.git")
parser.add_argument("--lock", type=Path, default=Path(__file__).resolve().parents[1] / "upstream-lock.json")
parser.add_argument("--source-dir", type=Path, help="exact candidate tree; required to update lock")
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--create-candidate", action="store_true")
parser.add_argument("--product-remote", default="origin")
parser.add_argument("--api-base", default="https://feicode.com/api/v1")
parser.add_argument("--repo", default="WenPai-org/wordpress-playground")
parser.add_argument("--sync-mirror", action="store_true",
                    help="shallow-sync canonical trunk and latest stable tag before reconciliation")
parser.add_argument("--mirror-push-url", default="https://feicode.com/WPFork/wordpress-playground-upstream.git")
parser.add_argument("--sync-output", type=Path)
args = parser.parse_args()

canonical_direct, canonical = ls_remote_details(args.canonical)
stable = stable_tags(canonical)
if not stable:
    raise SystemExit("BLOCKED no stable canonical semver tags returned")
version_tuple, tag, commit = stable[-1]

if args.sync_mirror:
    token = os.environ.get("FEICODE_TOKEN")
    if not token:
        raise SystemExit("BLOCKED FEICODE_TOKEN is absent; mirror mutation is forbidden")
    canonical_heads = subprocess.check_output(
        ["git", "ls-remote", "--heads", args.canonical, "refs/heads/trunk"],
        text=True, timeout=60,
    ).strip().split()
    if len(canonical_heads) != 2 or canonical_heads[1] != "refs/heads/trunk":
        raise SystemExit("BLOCKED canonical trunk ref is missing or ambiguous")
    canonical_trunk = canonical_heads[0]
    before_direct, before = ls_remote_details(args.mirror)
    tag_ref = f"refs/tags/{tag}"
    if tag_ref in before and before[tag_ref] != commit:
        raise SystemExit("BLOCKED existing mirror stable tag target differs; tags are immutable")
    if tag_ref in before_direct and before_direct[tag_ref] != canonical_direct[tag_ref]:
        raise SystemExit("BLOCKED existing mirror stable tag object differs; tags are immutable")
    before_heads = subprocess.check_output(
        ["git", "ls-remote", "--heads", args.mirror, "refs/heads/trunk"],
        text=True, timeout=60,
    ).strip().split()
    before_trunk = before_heads[0] if len(before_heads) == 2 else None
    auth_env = os.environ.copy()
    auth_env.update({
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.extraHeader",
        "GIT_CONFIG_VALUE_0": f"Authorization: token {token}",
    })
    with tempfile.TemporaryDirectory(prefix="wenpai-upstream-sync-") as directory:
        subprocess.run(["git", "init", "--bare", directory], check=True,
                       stdout=subprocess.DEVNULL)
        subprocess.run(["git", "-C", directory, "remote", "add", "canonical", args.canonical], check=True)
        subprocess.run(["git", "-C", directory, "fetch", "--depth=1", "--no-tags", "canonical",
                        "refs/heads/trunk:refs/heads/trunk"], check=True)
        subprocess.run(["git", "-C", directory, "fetch", "--depth=1", "--no-tags", "canonical",
                        f"refs/tags/{tag}:refs/tags/{tag}"], check=True)
        if tag_ref not in before:
            subprocess.run(["git", "-C", directory, "push", args.mirror_push_url,
                            f"{tag_ref}:{tag_ref}"], check=True, env=auth_env)
        lease = f"--force-with-lease=refs/heads/trunk:{before_trunk}" if before_trunk else "--force-with-lease=refs/heads/trunk:"
        subprocess.run(["git", "-C", directory, "push", lease, args.mirror_push_url,
                        "refs/heads/trunk:refs/heads/trunk"], check=True, env=auth_env)
    after_direct, after = ls_remote_details(args.mirror)
    after_heads = subprocess.check_output(
        ["git", "ls-remote", "--heads", args.mirror, "refs/heads/trunk"],
        text=True, timeout=60,
    ).strip().split()
    after_trunk = after_heads[0] if len(after_heads) == 2 else None
    if (after.get(tag_ref) != commit or after_direct.get(tag_ref) != canonical_direct[tag_ref]
            or after_trunk != canonical_trunk):
        raise SystemExit("BLOCKED shallow mirror post-push reconciliation failed")
    sync_report = {
        "schema": "wenpai-upstream-mirror-sync/v1",
        "strategy": "shallow-layered-stable-tag-and-trunk",
        "canonical_trunk": canonical_trunk,
        "previous_mirror_trunk": before_trunk,
        "mirror_trunk": after_trunk,
        "stable_tag": tag,
        "canonical_stable_commit": commit,
        "mirror_stable_commit": after.get(tag_ref),
        "canonical_stable_tag_object": canonical_direct[tag_ref],
        "mirror_stable_tag_object": after_direct.get(tag_ref),
        "tag_mutation_policy": "fail-closed-no-force",
        "trunk_mutation_policy": "force-with-lease-exact-observed-ref",
    }
    if args.sync_output:
        write_json(args.sync_output, sync_report)
    print(json.dumps(sync_report, sort_keys=True))

mirror_direct, mirror = ls_remote_details(args.mirror)
mirror_commit = mirror.get(f"refs/tags/{tag}")
mirror_tag_object = mirror_direct.get(f"refs/tags/{tag}")
status = "UNCHANGED"
reason = "current lock already records latest stable tag"
lock = json.loads(args.lock.read_text())
if mirror_commit is None:
    status, reason = "BLOCKED", "mirror has not received canonical stable tag"
elif mirror_commit != commit:
    status, reason = "BLOCKED", "canonical and mirror peeled tag targets differ"
elif mirror_tag_object != canonical_direct.get(f"refs/tags/{tag}"):
    status, reason = "BLOCKED", "canonical and mirror tag objects differ"
elif lock["upstream"]["tag"] != tag or lock["upstream"]["commit"] != commit:
    status, reason = "CANDIDATE", "new stable exact tag is mirrored"

report = {"schema": "wenpai-upstream-watch/v1", "status": status, "reason": reason,
          "canonical": args.canonical, "mirror": args.mirror, "tag": tag,
          "canonical_commit": commit, "mirror_commit": mirror_commit,
          "canonical_tag_object": canonical_direct.get(f"refs/tags/{tag}"),
          "mirror_tag_object": mirror_tag_object,
          "previous_tag": lock["upstream"]["tag"], "previous_commit": lock["upstream"]["commit"]}
write_json(args.output, report)
print(json.dumps(report, sort_keys=True))

if status == "BLOCKED":
    raise SystemExit(2)
if not args.create_candidate or status == "UNCHANGED":
    print(f"PASS watcher samples={len(stable)} status={status}")
    raise SystemExit(0)
if not args.source_dir:
    blocked(args.output, report, "--source-dir is required for candidate lock update")
source_dir = args.source_dir.resolve(strict=True)
head = subprocess.check_output(["git", "-C", str(source_dir), "rev-parse", "HEAD"], text=True).strip()
dirty = subprocess.check_output(
    ["git", "-C", str(source_dir), "status", "--porcelain", "--untracked-files=all"],
    text=True,
).strip()
if head != commit:
    blocked(args.output, report, f"candidate source HEAD {head} differs from stable commit {commit}")
if dirty:
    blocked(args.output, report, "candidate source checkout is not clean")
try:
    commit_timestamp = int(subprocess.check_output(
        ["git", "-C", str(source_dir), "show", "-s", "--format=%ct", commit], text=True,
    ).strip())
except (ValueError, subprocess.SubprocessError):
    blocked(args.output, report, "candidate commit timestamp cannot be resolved exactly")
tag_object = canonical_direct.get(f"refs/tags/{tag}")
if not tag_object:
    blocked(args.output, report, "canonical stable tag object is absent")
try:
    product_version = downstream_version(
        tag, lock["upstream"]["tag"], lock["downstream"]["version"]
    )
except (KeyError, ValueError) as error:
    blocked(args.output, report, str(error))
source = normalized_manifest(source_dir, symlinks="record")
lock["upstream"].update({"tag": tag, "tag_object": tag_object, "commit": commit,
                         "commit_timestamp": commit_timestamp,
                         "source_sha256": source["manifest_sha256"],
                         "source_manifest_entries": source["entry_count"]})
lock["toolchain"]["source_date_epoch"] = commit_timestamp
lock["downstream"].update({"version": product_version,
                            "artifact_sha256": "SIDECAR: authoritative after deterministic archive creation and anonymous Release readback",
                            "product_commit": "SELF: resolved from the immutable tag commit by exact-SHA CI"})
repo_root = args.lock.resolve().parent
inventory_path = repo_root / "docs/licenses/third-party-inventory.json"
metadata_path = repo_root / "docs/licenses/sbom-notice-metadata.json"
try:
    inventory = json.loads(inventory_path.read_text())
    metadata = json.loads(metadata_path.read_text())
    playground = next(item for item in inventory["components"]
                      if item["id"] == "wordpress-playground")
    metadata_playground = next(item for item in metadata["components"]
                               if item["id"] == "wordpress-playground")
except (OSError, KeyError, StopIteration, json.JSONDecodeError) as error:
    blocked(args.output, report, f"license inventory cannot be safely updated: {error}")
inventory["upstream_commit"] = commit
inventory["review_status"] = "BLOCKED"
inventory["review_blockers"] = [
    f"Human license, dependency, font, WASM and generated-asset review required for {tag}@{commit}"
]
playground["version"] = tag
playground["source"] = f"https://github.com/WordPress/wordpress-playground/tree/{commit}"
metadata["upstream_commit"] = commit
metadata["review_status"] = inventory["review_status"]
metadata["review_blockers"] = inventory["review_blockers"]
metadata_playground["version"] = tag
metadata_playground["source"] = playground["source"]
branch = f"bot/upstream-{tag}"
# The watcher report is intentionally written before candidate creation. Refuse
# unrelated workspace mutations while allowing only that report to differ.
try:
    allowed_report = args.output.resolve().relative_to(repo_root).as_posix()
except ValueError:
    allowed_report = None
if allowed_report is None:
    blocked(args.output, report, "candidate report path must be inside the product repository")
unexpected = []
for line in subprocess.check_output(
        ["git", "-C", str(repo_root), "status", "--porcelain", "--untracked-files=all"],
        text=True).splitlines():
    path = line[3:].split(" -> ")[-1]
    if path != allowed_report:
        unexpected.append(line)
if unexpected:
    raise SystemExit("BLOCKED unrelated product worktree mutations: " + "; ".join(unexpected))
subprocess.run(["git", "-C", str(repo_root), "checkout", "-b", branch], check=True)
write_json(args.lock, lock)
write_json(inventory_path, inventory)
write_json(metadata_path, metadata)
write_json(args.lock.parent / "evidence" / f"source-manifest-{tag}.json", source)
# Recalculate after every candidate-controlled lock/inventory mutation.  The
# transform tool canonicalizes its own output field, so this is stable.
transform = subprocess.run(
    ["python3", str(repo_root / "tools/transform-hash.py"), "--root", str(repo_root)],
    text=True, capture_output=True,
)
if transform.returncode != 0:
    blocked(args.output, report, "candidate transform digest could not be recalculated")
match = re.search(r"(?m)^([0-9a-f]{64})$", transform.stdout)
if not match:
    blocked(args.output, report, "candidate transform digest output is malformed")
lock["downstream"]["transform_sha256"] = match.group(1)
write_json(args.lock, lock)
report.update({"candidate": {"tag_object": tag_object,
                              "commit_timestamp": commit_timestamp,
                              "source_date_epoch": commit_timestamp,
                              "downstream_version": product_version,
                              "inventory_upstream_commit": commit,
                              "license_review_status": "BLOCKED",
                              "release_eligible": False,
                              "transform_sha256": match.group(1)}})
write_json(args.output, report)
subprocess.run(["git", "-C", str(repo_root), "add", str(args.lock), str(inventory_path),
                str(metadata_path), f"evidence/source-manifest-{tag}.json", str(args.output)], check=True)
subprocess.run(["git", "-C", str(repo_root), "commit", "-m",
                f"chore: prepare upstream {tag} candidate"], check=True)
subprocess.run(["git", "-C", str(repo_root), "push", args.product_remote,
                f"HEAD:refs/heads/{branch}"], check=True)

token = os.environ.get("FEICODE_TOKEN")
if not token:
    raise SystemExit("BLOCKED candidate branch pushed but FEICODE_TOKEN is absent; PR not created")
payload = json.dumps({"title": f"Upstream {tag} candidate", "head": branch, "base": "main",
                      "body": f"Automated stable candidate. Exact upstream: {tag}@{commit}. License/dependency review is BLOCKED pending human reconciliation; public Release and production deployment remain gated."}).encode()
request = urllib.request.Request(f"{args.api_base}/repos/{args.repo}/pulls", data=payload,
                                 headers={"Authorization": f"token {token}", "Content-Type": "application/json"}, method="POST")
with urllib.request.urlopen(request, timeout=30) as response:
    created = json.load(response)
print(f"PASS watcher samples={len(stable)} candidate_pr={created.get('html_url', 'created')}")
