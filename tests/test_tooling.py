import importlib.util
import json
from pathlib import Path
import subprocess
import sys
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


class PipelineTests(unittest.TestCase):
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
            output = base / "output"
            report = base / "report.json"
            subprocess.run([sys.executable, str(ROOT / "tools/apply-overlay.py"),
                            "--upstream", str(source), "--output", str(output),
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
            (runtime / "playground.html").write_text("<!doctype html><title>文派</title>")
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


if __name__ == "__main__":
    unittest.main()
