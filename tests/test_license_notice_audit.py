import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "tools" / "license-notice-audit.py"
SPEC = importlib.util.spec_from_file_location("license_notice_audit", MODULE_PATH)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class LicenseNoticeAuditTests(unittest.TestCase):
    def test_node_notice_resolves_exact_legacy_exception_and_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package-lock.json").write_text(json.dumps({
                "lockfileVersion": 3,
                "packages": {
                    "": {},
                    "node_modules/example": {"version": "1.0.0", "license": "ISC"},
                    "node_modules/legacy": {"version": "2.0.0"},
                    "node_modules/workspace": {"link": True, "resolved": "packages/workspace"},
                    "packages/published-workspace": {"version": "3.1.49"},
                },
            }))
            notices, unknown = AUDIT.node_notice(root, {
                "node_license_exceptions": {"legacy@2.0.0": "MIT"}
            })
            self.assertEqual([], unknown)
            self.assertEqual(4, notices["package_samples"])
            self.assertEqual(1, notices["license_counts"]["MIT"])
            self.assertEqual(2, notices["license_counts"]["GPL-2.0-or-later"])

    def test_node_notice_fails_closed_on_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package-lock.json").write_text(json.dumps({
                "lockfileVersion": 3,
                "packages": {"node_modules/unknown": {"version": "9.9.9"}},
            }))
            _, unknown = AUDIT.node_notice(root, {"node_license_exceptions": {}})
            self.assertEqual(["unknown@9.9.9"], unknown)

    def test_rollup_changes_with_content_not_mtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            file = root / "asset.wasm"
            file.write_bytes(b"one")
            first = AUDIT.rollup(root, [file])
            file.touch()
            self.assertEqual(first, AUDIT.rollup(root, [file]))
            file.write_bytes(b"two")
            self.assertNotEqual(first, AUDIT.rollup(root, [file]))

    def test_runtime_patterns_are_component_specific_nonzero_and_hashed(self):
        records = [
            {"path": "php-next/asyncify/8_6_0-dev/php_8_6.wasm",
             "sha256": "a" * 64},
            {"path": "unrelated/php_8_6.wasm", "sha256": "a" * 64},
        ]
        component = {
            "id": "php-next",
            "runtime_patterns": [{
                "pattern": "php-next/asyncify/8_6_0-dev/php_8_6.wasm",
                "min_samples": 1,
                "sha256": ["a" * 64],
            }],
        }
        results, failures = AUDIT.audit_runtime_patterns(component, records)
        self.assertEqual([], failures)
        self.assertEqual(1, results[0]["samples"])
        component["runtime_patterns"][0]["sha256"] = ["b" * 64]
        _, failures = AUDIT.audit_runtime_patterns(component, records)
        self.assertIn("SHA-256 mismatch", failures[0])

    def test_runtime_entrypoint_mapping_audits_final_namespace_and_fails_closed(self):
        records = [
            {"path": "index.html", "name": "index.html", "suffix": ".html", "sha256": "a" * 64},
            {"path": "remote.html", "name": "remote.html", "suffix": ".html", "sha256": "b" * 64},
        ]
        mapped = AUDIT.apply_runtime_path_mapping(records, ["index.html=playground.html"])
        self.assertEqual(["playground.html", "remote.html"], [item["path"] for item in mapped])
        with self.assertRaisesRegex(ValueError, "sources missing"):
            AUDIT.apply_runtime_path_mapping(records, ["missing.html=playground.html"])
        with self.assertRaisesRegex(ValueError, "collision"):
            AUDIT.apply_runtime_path_mapping(records, ["index.html=remote.html"])

    def test_required_runtime_components_declare_explicit_patterns_and_notice(self):
        root = Path(__file__).parents[1]
        inventory = json.loads((root / "docs/licenses/third-party-inventory.json").read_text())
        required = [component for component in inventory["components"]
                    if component.get("required_in") in {"runtime", "php-next"}]
        self.assertGreater(len(required), 0)
        for component in required:
            self.assertEqual(component["notice"], component["runtime_notice"])
            self.assertGreater(len(component["runtime_patterns"]), 0)
            for rule in component["runtime_patterns"]:
                self.assertGreaterEqual(rule["min_samples"], 1)
                self.assertNotRegex(rule["pattern"], r"^\*\.[A-Za-z0-9]+$")

    def test_human_notice_contract_uses_full_component_values(self):
        root = Path(__file__).parents[1]
        inventory = json.loads((root / "docs/licenses/third-party-inventory.json").read_text())
        lock = json.loads((root / "upstream-lock.json").read_text())
        notices = (root / "docs/licenses/THIRD_PARTY_NOTICES.md").read_text()
        self.assertEqual("PASS", inventory["review_status"])
        self.assertEqual([], inventory["review_blockers"])
        self.assertEqual(lock["upstream"]["commit"], inventory["upstream_commit"])
        self.assertEqual(
            lock["generated_assets"]["php_next"]["commit"],
            inventory["external_assets"]["php_next"]["commit"],
        )
        self.assertEqual(
            lock["generated_assets"]["php_next"]["wasm_sha256"],
            inventory["external_assets"]["php_next"]["wasm_sha256"],
        )
        self.assertEqual(
            set(inventory["policy"]["required_license_texts"]),
            set(inventory["policy"]["license_text_sha256"]),
        )
        self.assertGreater(len(inventory["components"]), 0)
        for component in inventory["components"]:
            for field in ("name", "license", "source", "notice"):
                self.assertIn(component[field], notices, f"{component['id']}:{field}")


if __name__ == "__main__":
    unittest.main()
