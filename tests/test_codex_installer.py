"""Exercise installs in disposable projects; no MCP servers or credentials needed."""
import json
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path

INSTALLER = Path(__file__).resolve().parents[1] / "install.sh"


class CodexInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="codex-kit-")
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.folder = self.project / ".codex"

    def run_install(self, *args, success=True):
        result = subprocess.run(
            ["bash", str(INSTALLER), "--codex", *args, str(self.project)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def existing_config(self, text):
        self.folder.mkdir()
        (self.folder / "config.toml").write_text(text)

    def test_local_install_update_and_uninstall_preserve_original(self):
        original = '# personal settings\nmodel = "example"\n[mcp_servers.other]\ncommand = "example"'
        self.existing_config(original)
        self.run_install()
        first = (self.folder / "config.toml").read_text()
        data = tomllib.loads(first)
        self.assertEqual(set(data["mcp_servers"]), {"mysql", "aws-mcp", "github", "other"})
        self.assertEqual(data["notify"][-1], "notify-hook")
        self.run_install()
        self.assertEqual(first, (self.folder / "config.toml").read_text())
        self.run_install("--uninstall")
        self.assertEqual(original, (self.folder / "config.toml").read_text())
        self.assertEqual(list(self.folder.iterdir()), [self.folder / "config.toml"])

    def test_clean_project_uninstall_removes_created_directory(self):
        self.run_install()
        self.run_install("--uninstall")
        self.assertFalse(self.folder.exists())

    def test_conflicting_notify_or_server_does_not_write(self):
        for original in ('notify = ["other"]\n', '[mcp_servers.mysql]\ncommand = "other"\n'):
            with self.subTest(original=original):
                self.folder.mkdir(exist_ok=True)
                (self.folder / "config.toml").write_text(original)
                self.run_install(success=False)
                self.assertEqual((self.folder / "config.toml").read_text(), original)
                self.assertFalse((self.folder / "ai-kit.json").exists())

    def test_modified_managed_block_blocks_update_and_uninstall(self):
        self.run_install()
        path = self.folder / "config.toml"
        edited = path.read_text().replace('startup_timeout_sec = 120', 'startup_timeout_sec = 90')
        path.write_text(edited)
        self.run_install(success=False)
        self.run_install("--uninstall", success=False)
        self.assertEqual(path.read_text(), edited)
        self.assertTrue((self.folder / "ai-kit.json").exists())

    def test_uninstall_preserves_user_settings_and_edited_tracing(self):
        self.run_install()
        path = self.folder / "config.toml"
        path.write_text('model = "personal"\n' + path.read_text())
        tracing = self.folder / "mlflow-tracing.json"
        tracing.write_text(json.dumps({"trackingUri": "http://localhost:5000", "experimentId": "3"}))
        self.run_install("--uninstall")
        self.assertEqual(tomllib.loads(path.read_text()), {"model": "personal"})
        self.assertEqual(json.loads(tracing.read_text())["experimentId"], "3")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.project), *args], check=True, capture_output=True, text=True).stdout

    def test_local_install_hides_files_and_restores_exclude(self):
        self.git("init")
        exclude = self.project / ".git/info/exclude"
        original = exclude.read_text()
        self.run_install()
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.run_install("--uninstall")
        self.assertEqual(exclude.read_text(), original)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_local_refuses_tracked_config(self):
        self.git("init")
        self.existing_config('model = "personal"\n')
        self.git("add", ".codex/config.toml")
        self.run_install(success=False)
        self.assertEqual((self.folder / "config.toml").read_text(), 'model = "personal"\n')

    def test_legacy_shared_install_requires_uninstall_before_local_install(self):
        self.run_install()
        record = self.folder / "ai-kit.json"
        manifest = json.loads(record.read_text())
        manifest["mode"] = "shared"
        record.write_text(json.dumps(manifest))
        result = self.run_install(success=False)
        self.assertIn("Older shared Codex install", result.stderr)
        self.run_install("--uninstall")
        self.run_install()
        self.assertEqual(json.loads(record.read_text())["mode"], "local")


if __name__ == "__main__":
    unittest.main()
