import importlib.util
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).parents[1] / "tools" / "release.py"
SPEC = importlib.util.spec_from_file_location("wenpai_release", MODULE_PATH)
RELEASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RELEASE)


class ReleaseTests(unittest.TestCase):
    def args(self, artifact):
        return types.SimpleNamespace(
            api_base="https://forge.test/api/v1", repo="owner/repo",
            git_url="https://forge.test/owner/repo.git", tag="v1.0.0",
            commit="a" * 40, artifact=[artifact], title=None, body="body",
        )

    def test_new_release_stays_draft_until_all_bytes_verified_then_public_readback(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifact = Path(temporary) / "runtime.tar.gz"
            artifact.write_bytes(b"exact bytes")
            digest = RELEASE.sha256_file(artifact)
            state = {"draft": True, "assets": [], "patches": []}

            def request_json(url, token=None, data=None, method=None):
                if method == "POST":
                    return 201, {"id": 7, **state}
                return 200, {"id": 7, **state}

            def upload(*_args):
                state["assets"] = [{"name": artifact.name,
                                    "browser_download_url": "https://public.test/runtime"}]

            def patch(_api, _repo, _id, _token, **changes):
                state["patches"].append(changes)
                state.update(changes)
                return {"id": 7, **state}

            with mock.patch.object(RELEASE.subprocess, "check_output",
                                   return_value=f"{'a' * 40}\trefs/tags/v1.0.0\n"), \
                 mock.patch.object(RELEASE, "request_json", side_effect=request_json), \
                 mock.patch.object(RELEASE, "upload_asset", side_effect=upload), \
                 mock.patch.object(RELEASE, "patch_release", side_effect=patch), \
                 mock.patch.object(RELEASE, "download_sha", return_value=digest) as download:
                RELEASE.publish(self.args(artifact), "secret")
            self.assertFalse(state["draft"])
            self.assertEqual(False, state["patches"][-1]["draft"])
            self.assertEqual(["secret", None], [call.args[1] for call in download.call_args_list])

    def test_streaming_upload_keeps_token_out_of_argv(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifact = Path(temporary) / "large.bin"
            artifact.write_bytes(b"payload")
            with mock.patch.object(RELEASE.subprocess, "run") as run:
                RELEASE.upload_asset("https://forge.test/api/v1", "owner/repo", 1,
                                     "do-not-leak", artifact)
            argv = run.call_args.args[0]
            self.assertNotIn("do-not-leak", " ".join(map(str, argv)))
            self.assertIn(b"do-not-leak", run.call_args.kwargs["input"])
            self.assertIs(RELEASE.subprocess.DEVNULL, run.call_args.kwargs["stdout"])

    def test_complete_public_release_is_mutation_free_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifact = Path(temporary) / "runtime.tar.gz"
            artifact.write_bytes(b"same")
            release = {"id": 8, "draft": False, "assets": [{
                "name": artifact.name, "browser_download_url": "https://public.test/runtime"
            }]}
            with mock.patch.object(RELEASE.subprocess, "check_output",
                                   return_value=f"{'a' * 40}\trefs/tags/v1.0.0\n"), \
                 mock.patch.object(RELEASE, "request_json", return_value=(200, release)), \
                 mock.patch.object(RELEASE, "download_sha",
                                   return_value=RELEASE.sha256_file(artifact)), \
                 mock.patch.object(RELEASE, "patch_release") as patch:
                RELEASE.publish(self.args(artifact), "secret")
            patch.assert_not_called()

    def test_partial_public_release_is_closed_completed_and_republished(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifact = Path(temporary) / "runtime.tar.gz"
            artifact.write_bytes(b"same")
            state = {"id": 9, "draft": False, "assets": []}

            def request_json(*_args, **_kwargs):
                return 200, dict(state)

            def patch(_api, _repo, _id, _token, **changes):
                state.update(changes)
                return dict(state)

            def upload(*_args):
                state["assets"] = [{
                    "name": artifact.name,
                    "browser_download_url": "https://public.test/runtime",
                }]

            with mock.patch.object(RELEASE.subprocess, "check_output",
                                   return_value=f"{'a' * 40}\trefs/tags/v1.0.0\n"), \
                 mock.patch.object(RELEASE, "request_json", side_effect=request_json), \
                 mock.patch.object(RELEASE, "patch_release", side_effect=patch), \
                 mock.patch.object(RELEASE, "upload_asset", side_effect=upload), \
                 mock.patch.object(RELEASE, "download_sha",
                                   return_value=RELEASE.sha256_file(artifact)):
                RELEASE.publish(self.args(artifact), "secret")
            self.assertFalse(state["draft"])
            self.assertEqual([artifact.name], [item["name"] for item in state["assets"]])

    def test_anonymous_readback_failure_closes_new_release_to_draft(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifact = Path(temporary) / "runtime.tar.gz"
            artifact.write_bytes(b"exact")
            asset = {"name": artifact.name, "browser_download_url": "https://asset.test/file"}
            draft = {"id": 10, "draft": True, "assets": [asset]}
            public = {"id": 10, "draft": False, "assets": [asset]}
            calls = iter([(200, draft), (200, draft), (404, None)])
            patches = []

            def patch(_api, _repo, _id, _token, **changes):
                patches.append(changes)
                return public if changes["draft"] is False else draft

            with mock.patch.object(RELEASE.subprocess, "check_output",
                                   return_value=f"{'a' * 40}\trefs/tags/v1.0.0\n"), \
                 mock.patch.object(RELEASE, "request_json", side_effect=lambda *_a, **_k: next(calls)), \
                 mock.patch.object(RELEASE, "download_sha",
                                   return_value=RELEASE.sha256_file(artifact)), \
                 mock.patch.object(RELEASE, "patch_release", side_effect=patch):
                with self.assertRaises(SystemExit):
                    RELEASE.publish(self.args(artifact), "secret")
            self.assertEqual(False, patches[-2]["draft"])
            self.assertEqual(True, patches[-1]["draft"])


if __name__ == "__main__":
    unittest.main()
