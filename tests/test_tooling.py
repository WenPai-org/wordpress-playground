import importlib.util
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


if __name__ == "__main__":
    unittest.main()
