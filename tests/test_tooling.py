import importlib.util
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from manifest import UnsafeTree, digest_inputs, normalized_manifest


class ManifestTests(unittest.TestCase):
    def test_nonzero_manifest_and_content_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "a.txt").write_text("one")
            first = normalized_manifest(root)
            (root / "a.txt").write_text("two")
            second = normalized_manifest(root)
            self.assertEqual(first["entry_count"], 1)
            self.assertNotEqual(first["manifest_sha256"], second["manifest_sha256"])

    def test_rejects_symlink_and_case_collision(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "a").write_text("x")
            (root / "link").symlink_to("a")
            with self.assertRaises(UnsafeTree):
                normalized_manifest(root)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "Readme").write_text("x")
            (root / "README").write_text("y")
            if len(list(root.iterdir())) < 2:
                self.skipTest("host filesystem is case-insensitive")
            with self.assertRaises(UnsafeTree):
                normalized_manifest(root)

    def test_transform_digest_covers_multiple_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config").mkdir()
            (root / "config" / "a.json").write_text("{}")
            (root / "rule.py").write_text("pass")
            result = digest_inputs(root, ["config", "rule.py"])
            self.assertEqual(result["input_count"], 2)
            self.assertEqual(len(result["transform_sha256"]), 64)

    def test_python_bytecode_does_not_change_governed_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "rules").mkdir()
            (root / "rules" / "rule.py").write_text("pass\n")
            first = digest_inputs(root, ["rules"])
            cache = root / "rules" / "__pycache__"
            cache.mkdir()
            (cache / "rule.cpython-311.pyc").write_bytes(b"generated")
            second = digest_inputs(root, ["rules"])
            self.assertEqual(first["transform_sha256"], second["transform_sha256"])


class PipelineTests(unittest.TestCase):
    def test_wp_cli_is_prefetched_once_and_runtime_normalization_is_offline(self):
        normalize = (ROOT / "tools/normalize-runtime.py").read_text()
        self.assertIn('parser.add_argument("--wp-cli-payload"', normalize)
        self.assertNotIn("urlopen", normalize)
        for workflow_name in ("ci.yml", "release.yml"):
            workflow = (ROOT / ".forgejo/workflows" / workflow_name).read_text()
            self.assertIn("tools/prefetch-wp-cli.py", workflow)
            self.assertIn("--wp-cli-payload .ci-work/generated-assets/wp-cli.phar", workflow)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = b"exact wp-cli test payload\n"
            commit = "1" * 40
            lock = root / "lock.json"
            lock.write_text(json.dumps({"generated_assets": {"wp_cli": {
                "repository": "https://example.invalid/wp-cli/builds",
                "commit": commit,
                "url": f"https://example.invalid/{commit}/wp-cli.phar",
                "sha256": hashlib.sha256(payload).hexdigest(),
                "gzip_sha256": "2" * 64,
            }}}))
            bin_dir = root / "bin"
            bin_dir.mkdir()
            curl = bin_dir / "curl"
            fixture = root / "fixture"
            fixture.write_bytes(payload)
            curl.write_text("""#!/bin/sh
while [ "$#" -gt 0 ]; do
  if [ "$1" = "--output" ]; then shift; output=$1; fi
  shift
done
cp "$FAKE_CURL_SOURCE" "$output"
""")
            curl.chmod(0o755)
            output = root / "generated" / "wp-cli.phar"
            report = root / "report.json"
            env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}",
                       FAKE_CURL_SOURCE=str(fixture))
            subprocess.run([
                sys.executable, str(ROOT / "tools/prefetch-wp-cli.py"),
                "--lock", str(lock), "--output", str(output), "--report", str(report),
            ], check=True, capture_output=True, text=True, env=env)
            self.assertEqual(payload, output.read_bytes())
            self.assertEqual("PASS", json.loads(report.read_text())["status"])

    def test_generated_asset_fetch_uses_source_volume_not_system_tmpfs(self):
        tool = (ROOT / "tools/sync-generated-assets.py").read_text()
        self.assertIn('dir=source.parent', tool)
        self.assertIn('php-next exact commit fetch failed', tool)

    def test_default_transform_digest_covers_attribution_audit_and_normalization(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "transform.json"
            subprocess.run(
                [sys.executable, str(ROOT / "tools/transform-hash.py"),
                 "--root", str(ROOT), "--output", str(output)],
                check=True, capture_output=True, text=True,
            )
            paths = {item["path"] for item in json.loads(output.read_text())["inputs"]}
            required = {
                "LICENSE", "NOTICE", "UPSTREAM.md", "docs/licenses",
                "tools/license-notice-audit.py", "tools/release.py",
                "tools/stable-watcher.py", "tools/normalize-runtime.py",
                "tools/prefetch-wp-cli.py",
                "tools/restore-upstream-generated-assets.py",
                "tools/normalize-blueprint-validator.py", "upstream-lock.json#downstream.transform_sha256=SELF",
            }
            self.assertEqual(set(), required - paths)

    def test_deterministic_node_build_preload_is_scoped_and_repeatable(self):
        preload = ROOT / "tools/deterministic-node-build.cjs"
        script = "console.log(process.pid,Date.now(),Math.random(),Math.random())"
        missing = subprocess.run(["node", "-r", str(preload), "-e", script],
                                 capture_output=True, text=True)
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("SOURCE_DATE_EPOCH", missing.stderr)
        env = dict(os.environ, SOURCE_DATE_EPOCH="1786355284")
        first = subprocess.run(["node", "-r", str(preload), "-e", script], env=env,
                               check=True, capture_output=True, text=True).stdout
        second = subprocess.run(["node", "-r", str(preload), "-e", script], env=env,
                                check=True, capture_output=True, text=True).stdout
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("4242 1786355284000 "))

    def test_apply_overlay_forces_no_index_inside_parent_repository(self):
        tool = (ROOT / "tools/apply-overlay.py").read_text()
        self.assertIn('"apply", "--no-index"', tool)
        with tempfile.TemporaryDirectory() as temporary:
            outer = Path(temporary) / "outer"
            nested = outer / "nested"
            nested.mkdir(parents=True)
            subprocess.run(["git", "init", str(outer)], check=True, capture_output=True)
            target = nested / "contract.txt"
            target.write_text("English\n")
            patch = outer / "contract.patch"
            patch.write_text("""diff --git a/contract.txt b/contract.txt
--- a/contract.txt
+++ b/contract.txt
@@ -1 +1 @@
-English
+中文
""")
            env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(nested.parent))
            subprocess.run(["git", "apply", "--no-index", "--check", str(patch)],
                           cwd=nested, env=env, check=True, capture_output=True)
            subprocess.run(["git", "apply", "--no-index", str(patch)],
                           cwd=nested, env=env, check=True, capture_output=True)
            self.assertEqual(target.read_text(), "中文\n")

    def test_apply_overlay_runs_localization_apply_check_and_scan(self):
        catalog = json.loads((ROOT / "overlays/localization/replacements.json").read_text())
        grouped = {}
        for entry in catalog["entries"]:
            grouped.setdefault(entry["path"], []).extend([entry["old"]] * entry["expectedCount"])
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source"
            for relative, fragments in grouped.items():
                target = source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("\n".join(fragments))
            # Patch applicability has its own exact-source contract test. This
            # synthetic fixture exercises localization injection only and does
            # not pretend to contain the four upstream unit-test files.
            overlay = base / "overlay"
            overlay.mkdir()
            output = base / "output"
            report = base / "report.json"
            subprocess.run([sys.executable, str(ROOT / "tools/apply-overlay.py"),
                            "--upstream", str(source), "--output", str(output),
                            "--overlay", str(overlay),
                            "--report", str(report)], check=True, capture_output=True, text=True)
            result = json.loads(report.read_text())
            self.assertGreaterEqual(result["changed_count"], 40)
            scan = subprocess.run([sys.executable, str(ROOT / "tools/localization_scan.py"),
                                   "--source-root", str(output)], check=True, capture_output=True, text=True)
            self.assertEqual(json.loads(scan.stdout)["status"], "PASS")

    def test_runtime_archive_is_reproducible(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source"
            runtime = source / "runtime"
            runtime.mkdir(parents=True)
            (runtime / "index.html").write_text("<!doctype html><title>文派</title>")
            (runtime / "remote.html").write_text("<!doctype html><title>Remote</title>")
            hashes = []
            for number in (1, 2):
                out = base / f"out-{number}"
                subprocess.run([sys.executable, str(ROOT / "tools/build-runtime.py"),
                                "--source", str(source), "--runtime-dir", "runtime",
                                "--out-dir", str(out), "--version", "1.0.0.1",
                                "--source-sha", "a" * 64, "--transform-sha", "b" * 64,
                                "--product-commit", "c" * 40, "--source-date-epoch", "1700000000"],
                               check=True, capture_output=True, text=True)
                hashes.append((out / "wenpai-wordpress-playground-1.0.0.1.tar.gz").read_bytes())
            self.assertEqual(hashes[0], hashes[1])
            artifact = base / "out-1/wenpai-wordpress-playground-1.0.0.1.tar.gz"
            with tarfile.open(artifact, "r:gz") as archive:
                names = set(archive.getnames())
            self.assertIn("runtime/playground.html", names)
            self.assertIn("runtime/remote.html", names)
            self.assertNotIn("runtime/index.html", names)
            self.assertIn("NOTICE", names)
            self.assertIn("docs/licenses/THIRD_PARTY_NOTICES.md", names)
            self.assertIn("docs/licenses/third-party-inventory.json", names)
            self.assertIn("docs/licenses/texts/PHP-3.01.txt", names)
            manifest = json.loads((base / "out-1/runtime-manifest.json").read_text())
            self.assertEqual(manifest["entrypoint_mapping"], {"index.html": "playground.html"})

    def test_runtime_archive_parts_reassemble_exact_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source"
            runtime = source / "runtime"
            runtime.mkdir(parents=True)
            (runtime / "index.html").write_text("<title>文派</title>")
            (runtime / "payload.bin").write_bytes(bytes(range(256)) * 32)
            out = base / "out"
            subprocess.run([sys.executable, str(ROOT / "tools/build-runtime.py"),
                            "--source", str(source), "--runtime-dir", "runtime",
                            "--out-dir", str(out), "--version", "1.0.0.1",
                            "--source-sha", "a" * 64, "--transform-sha", "b" * 64,
                            "--product-commit", "c" * 40, "--source-date-epoch", "1700000000",
                            "--max-attachment-bytes", "256"],
                           check=True, capture_output=True, text=True)
            artifact_set = json.loads((out / "artifact-set.json").read_text())
            self.assertGreater(artifact_set["part_count"], 1)
            reassembled = b"".join((out / part["name"]).read_bytes()
                                   for part in artifact_set["parts"])
            artifact = (out / artifact_set["artifact"]).read_bytes()
            self.assertEqual(reassembled, artifact)

    def test_compare_runtime_builds_fails_closed_on_payload_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime_a = base / "runtime-a"
            runtime_b = base / "runtime-b"
            runtime_a.mkdir()
            runtime_b.mkdir()
            (runtime_a / "playground.html").write_text("one")
            (runtime_b / "playground.html").write_text("two")
            manifest_a = base / "a.json"
            manifest_b = base / "b.json"
            manifest_a.write_text(json.dumps(normalized_manifest(runtime_a)))
            manifest_b.write_text(json.dumps(normalized_manifest(runtime_b)))
            result = subprocess.run(
                [sys.executable, str(ROOT / "tools/compare-runtime-builds.py"),
                 "--manifest-a", str(manifest_a), "--manifest-b", str(manifest_b)],
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("playground.html", result.stdout)

    def test_blueprint_validator_aliases_are_canonical_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            validator = source / "packages/playground/blueprints/public/blueprint-v2-schema-validator.js"
            validator.parent.mkdir(parents=True)
            schema = validator.with_name("blueprint-schema.json")
            schema.write_text('{"$ref":"#/definitions/alias-10-20-30",'
                              '"definitions":{"alias-10-20-30":{}}}')
            validator.write_text(
                'const schema={"$ref":"#/definitions/alias-10-20-30",'
                '"definitions":{"alias-10-20-30":{},"alias-99-88":{}}};'
            )
            first = source / "first.json"
            second = source / "second.json"
            subprocess.run(
                [sys.executable, str(ROOT / "tools/normalize-blueprint-validator.py"),
                 "--source", str(source), "--output", str(first)],
                check=True, capture_output=True, text=True,
            )
            canonical = validator.read_text()
            self.assertEqual(canonical.count("alias-wenpai-0001"), 2)
            self.assertEqual(canonical.count("alias-wenpai-0002"), 1)
            self.assertNotIn("alias-10-20-30", canonical)
            self.assertNotIn("alias-10-20-30", schema.read_text())
            subprocess.run(
                [sys.executable, str(ROOT / "tools/normalize-blueprint-validator.py"),
                 "--source", str(source), "--output", str(second)],
                check=True, capture_output=True, text=True,
            )
            self.assertEqual(validator.read_text(), canonical)
            self.assertEqual(json.loads(second.read_text())["result"], "already-normalized")


class ExportIgnoredAssetRestoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.repository = self.base / "upstream"
        self.repository.mkdir()
        files = {
            "packages/playground/wordpress-builds/src/wordpress/wp-beta.tar.zst": b"tar-zst",
            "packages/playground/wordpress-builds/public/wp-beta/wordpress-remote-asset-paths": b"remote",
            "packages/playground/wordpress-builds/public/wp-beta/wordpress-static.zip": b"zip",
            "packages/playground/wordpress-builds/public/wp-beta/wp-admin/css/deep/admin.css": b"css",
            "packages/php-wasm/web-builds/8-5/asyncify/8_5_8/php_8_5.wasm": b"web-wasm",
            "packages/php-wasm/node-builds/8-5/jspi/8_5_8/php_8_5.wasm": b"node-wasm",
            "packages/playground/website/demos/index.html": b"<title>demo</title>",
        }
        for relative, payload in files.items():
            target = self.repository / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        (self.repository / ".gitattributes").write_text(
            "packages/playground/wordpress-builds/public/**/* export-ignore\n"
            "packages/playground/wordpress-builds/src/wordpress/**/*.tar.zst export-ignore\n"
            "packages/php-wasm/web-builds/**/*.wasm export-ignore\n"
            "packages/php-wasm/node-builds/**/*.wasm export-ignore\n"
            "packages/playground/website/demos/* export-ignore\n"
        )
        subprocess.run(["git", "init", "-q"], cwd=self.repository, check=True)
        subprocess.run(["git", "add", "."], cwd=self.repository, check=True)
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                        "commit", "-qm", "fixture"], cwd=self.repository, check=True)
        self.commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repository,
                                              text=True).strip()
        self.lock = self.base / "lock.json"
        self.lock.write_text(json.dumps({"upstream": {"commit": self.commit}, "generated_assets": {}}))
        candidate = self.base / "candidate.json"
        subprocess.run([sys.executable, str(ROOT / "tools/restore-upstream-generated-assets.py"),
                        "--repository", str(self.repository), "--lock", str(self.lock),
                        "--inventory-output", str(candidate)], check=True, capture_output=True, text=True)
        locked = json.loads(self.lock.read_text())
        locked["generated_assets"]["upstream_export_ignored"] = json.loads(candidate.read_text())
        self.lock.write_text(json.dumps(locked))
        archive = subprocess.check_output(["git", "archive", self.commit], cwd=self.repository)
        self.destination = self.base / "archive"
        self.destination.mkdir()
        subprocess.run(["tar", "-x", "-C", str(self.destination)], input=archive, check=True)

    def tearDown(self):
        self.temporary.cleanup()

    def run_restore(self, *, check=True):
        return subprocess.run(
            [sys.executable, str(ROOT / "tools/restore-upstream-generated-assets.py"),
             "--repository", str(self.repository), "--destination", str(self.destination),
             "--lock", str(self.lock)], check=check, capture_output=True, text=True)

    def test_restores_all_seven_nonzero_tracked_groups_idempotently(self):
        result = self.run_restore()
        report = json.loads(result.stdout.splitlines()[0])
        self.assertEqual(report["entry_count"], 7)
        self.assertEqual(report["restored"], 7)
        self.assertEqual(set(report["groups"]), {
            "wordpress_tar_zst", "wordpress_remote_asset_paths", "wordpress_static_zip",
            "wordpress_public_tree", "php_wasm_web", "php_wasm_node", "website_demos",
        })
        self.assertTrue(all(group["entry_count"] == 1 for group in report["groups"].values()))
        second = self.run_restore()
        self.assertEqual(json.loads(second.stdout.splitlines()[0])["already_present"], 7)

    def test_rejects_tracked_symlink_in_whitelisted_tree(self):
        link = self.repository / "packages/playground/wordpress-builds/public/wp-beta/tracked-link"
        link.symlink_to("wordpress-static.zip")
        subprocess.run(["git", "add", str(link.relative_to(self.repository))],
                       cwd=self.repository, check=True)
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                        "commit", "-qm", "symlink fixture"], cwd=self.repository, check=True)
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repository,
                                         text=True).strip()
        locked = json.loads(self.lock.read_text())
        locked["upstream"]["commit"] = commit
        self.lock.write_text(json.dumps(locked))
        failed = subprocess.run(
            [sys.executable, str(ROOT / "tools/restore-upstream-generated-assets.py"),
             "--repository", str(self.repository), "--lock", str(self.lock),
             "--inventory-output", str(self.base / "invalid.json")],
            check=False, capture_output=True, text=True,
        )
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("non-regular tracked entry rejected", failed.stderr)

    def test_rejects_deep_extra_and_deep_symlink(self):
        self.run_restore()
        extra = self.destination / "packages/playground/wordpress-builds/public/wp-beta/wp-admin/deep/extra.js"
        extra.parent.mkdir(parents=True, exist_ok=True)
        extra.write_text("extra")
        failed = self.run_restore(check=False)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("untracked/extra governed destination file", failed.stderr)
        extra.unlink()
        target = self.destination / "packages/playground/wordpress-builds/public/wp-beta/wp-admin/css/deep/admin.css"
        target.unlink()
        target.symlink_to("../../../../wordpress-static.zip")
        failed = self.run_restore(check=False)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("symlink rejected", failed.stderr)


if __name__ == "__main__":
    unittest.main()
