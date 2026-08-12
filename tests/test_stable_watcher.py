import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]


def git(*args, cwd, env=None):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   text=True, env=env)


class PullHandler(http.server.BaseHTTPRequestHandler):
    samples = 0

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length))
        type(self).samples += 1
        response = json.dumps({"html_url": "http://fixture/pr/1", "body": body}).encode()
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, *_args):
        pass


class StableWatcherTests(unittest.TestCase):
    def test_real_new_annotated_tag_candidate_updates_every_coupled_field(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            canonical = base / "canonical"
            canonical.mkdir()
            env = os.environ | {
                "GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.test",
                "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.test",
            }
            git("init", cwd=canonical, env=env)
            (canonical / "payload.txt").write_text("old")
            git("add", ".", cwd=canonical, env=env)
            first_env = env | {"GIT_AUTHOR_DATE": "1700000000 +0000",
                               "GIT_COMMITTER_DATE": "1700000000 +0000"}
            git("commit", "-m", "old", cwd=canonical, env=first_env)
            git("tag", "-a", "v1.0.0", "-m", "old", cwd=canonical, env=first_env)
            old_commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=canonical, text=True).strip()
            (canonical / "payload.txt").write_text("new")
            git("commit", "-am", "new", cwd=canonical,
                env=env | {"GIT_AUTHOR_DATE": "1700001234 +0000",
                           "GIT_COMMITTER_DATE": "1700001234 +0000"})
            git("tag", "-a", "v1.0.1", "-m", "new", cwd=canonical, env=env)
            new_commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=canonical, text=True).strip()
            new_tag_object = subprocess.check_output(
                ["git", "rev-parse", "v1.0.1"], cwd=canonical, text=True).strip()

            mirror = base / "mirror.git"
            subprocess.run(["git", "clone", "--mirror", str(canonical), str(mirror)],
                           check=True, capture_output=True)
            source = base / "source"
            subprocess.run(["git", "clone", "--branch", "v1.0.1", str(mirror), str(source)],
                           check=True, capture_output=True)

            product = base / "product"
            shutil.copytree(ROOT, product, ignore=shutil.ignore_patterns(".git", "dist", "evidence"))
            (product / "evidence").mkdir()
            lock_path = product / "upstream-lock.json"
            lock = json.loads(lock_path.read_text())
            lock["upstream"].update({"tag": "v1.0.0", "commit": old_commit})
            lock["downstream"]["version"] = "1.0.0.1"
            lock_path.write_text(json.dumps(lock, indent=2) + "\n")
            git("init", cwd=product, env=env)
            git("add", ".", cwd=product, env=env)
            git("commit", "-m", "product base", cwd=product, env=env)
            product_remote = base / "product.git"
            git("init", "--bare", str(product_remote), cwd=base, env=env)
            git("remote", "add", "origin", str(product_remote), cwd=product, env=env)
            git("push", "origin", "HEAD:main", cwd=product, env=env)

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), PullHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                result = subprocess.run(
                    [sys.executable, "tools/stable-watcher.py",
                     "--canonical", str(canonical), "--mirror", str(mirror),
                     "--lock", str(lock_path), "--source-dir", str(source),
                     "--output", "evidence/upstream-watch.json", "--create-candidate",
                     "--product-remote", "origin", "--api-base",
                     f"http://127.0.0.1:{server.server_port}/api/v1", "--repo", "owner/repo"],
                    cwd=product, env=env | {"FEICODE_TOKEN": "fixture-token"},
                    text=True, capture_output=True,
                )
            finally:
                server.shutdown()
                thread.join()
                server.server_close()
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            candidate = base / "candidate"
            subprocess.run(["git", "clone", "--branch", "bot/upstream-v1.0.1",
                            str(product_remote), str(candidate)], check=True, capture_output=True)
            updated = json.loads((candidate / "upstream-lock.json").read_text())
            self.assertEqual(new_commit, updated["upstream"]["commit"])
            self.assertEqual(new_tag_object, updated["upstream"]["tag_object"])
            self.assertEqual(1700001234, updated["upstream"]["commit_timestamp"])
            self.assertEqual(1700001234, updated["toolchain"]["source_date_epoch"])
            self.assertEqual("1.0.1.1", updated["downstream"]["version"])
            inventory = json.loads(
                (candidate / "docs/licenses/third-party-inventory.json").read_text())
            self.assertEqual(new_commit, inventory["upstream_commit"])
            self.assertEqual("BLOCKED", inventory["review_status"])
            self.assertGreater(len(inventory["review_blockers"]), 0)
            self.assertRegex(updated["downstream"]["transform_sha256"], r"^[0-9a-f]{64}$")
            report = json.loads((candidate / "evidence/upstream-watch.json").read_text())
            self.assertEqual(new_commit, report["candidate"]["inventory_upstream_commit"])
            self.assertEqual("BLOCKED", report["candidate"]["license_review_status"])
            self.assertFalse(report["candidate"]["release_eligible"])
            self.assertGreaterEqual(PullHandler.samples, 1)


if __name__ == "__main__":
    unittest.main()
