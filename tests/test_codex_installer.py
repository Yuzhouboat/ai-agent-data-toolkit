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
        self.assertNotIn("notify", data)
        hooks = json.loads((self.folder / "hooks.json").read_text())
        self.assertIn("mlflow_stop.py", hooks["hooks"]["Stop"][0]["hooks"][0]["command"])
        self.run_install()
        self.assertEqual(first, (self.folder / "config.toml").read_text())
        self.run_install("--uninstall")
        self.assertEqual(original, (self.folder / "config.toml").read_text())
        self.assertEqual(list(self.folder.iterdir()), [self.folder / "config.toml"])

    def test_clean_project_uninstall_removes_created_directory(self):
        self.run_install()
        self.run_install("--uninstall")
        self.assertFalse(self.folder.exists())

    def test_conflicting_server_does_not_write(self):
        for original in ('[mcp_servers.mysql]\ncommand = "other"\n',):
            with self.subTest(original=original):
                self.folder.mkdir(exist_ok=True)
                (self.folder / "config.toml").write_text(original)
                self.run_install(success=False)
                self.assertEqual((self.folder / "config.toml").read_text(), original)
                self.assertFalse((self.folder / "ai-kit.json").exists())

    def test_existing_notify_is_preserved(self):
        original = 'notify = ["other"]\n'
        self.existing_config(original)
        self.run_install()
        self.assertEqual(tomllib.loads((self.folder / "config.toml").read_text())["notify"], ["other"])
        self.run_install("--uninstall")
        self.assertEqual((self.folder / "config.toml").read_text(), original)

    def test_existing_hooks_are_preserved_and_restored(self):
        self.folder.mkdir()
        hooks = self.folder / "hooks.json"
        original = '{"description":"mine","hooks":{"Stop":[{"hooks":[{"type":"command","command":"echo keep"}]}]}}\n'
        hooks.write_text(original)
        self.run_install()
        first = hooks.read_text()
        self.assertEqual(len(json.loads(first)["hooks"]["Stop"]), 2)
        self.run_install()
        self.assertEqual(hooks.read_text(), first)
        data = json.loads(first)
        data["hooks"]["SessionStart"] = [{"hooks": [{"type": "command", "command": "echo added"}]}]
        hooks.write_text(json.dumps(data))
        self.run_install("--uninstall")
        remaining = json.loads(hooks.read_text())
        self.assertEqual(remaining["hooks"]["Stop"], json.loads(original)["hooks"]["Stop"])
        self.assertIn("SessionStart", remaining["hooks"])

    def test_existing_hook_file_is_restored_byte_for_byte(self):
        self.folder.mkdir()
        path = self.folder / "hooks.json"
        original = '{ "hooks": { "Stop": [] } }\n'
        path.write_text(original)
        self.run_install()
        self.run_install("--uninstall")
        self.assertEqual(path.read_text(), original)

    def test_edited_adapter_blocks_update_and_survives_uninstall(self):
        self.run_install()
        path = self.folder / "hooks/mlflow_stop.py"
        edited = path.read_text() + '\n# personal change\n'
        path.write_text(edited)
        self.run_install(success=False)
        self.run_install("--uninstall")
        self.assertEqual(path.read_text(), edited)

    def test_hook_paths_with_spaces_and_quotes(self):
        import shlex
        self.project = self.project / "project with spaces and 'quote'"
        self.project.mkdir()
        self.folder = self.project / ".codex"
        self.run_install()
        hook = json.loads((self.folder / "hooks.json").read_text())["hooks"]["Stop"][0]["hooks"][0]
        self.assertEqual(shlex.split(hook["command"]), ["python3", str(self.folder / "hooks/mlflow_stop.py")])

    def test_legacy_notify_block_migrates_to_stop_hook(self):
        self.run_install()
        path = self.folder / "config.toml"
        record = self.folder / "ai-kit.json"
        data = json.loads(record.read_text())
        legacy = '# BEGIN AI data kit: notify\nnotify = ["npx", "-y", "@mlflow/codex@latest", "notify-hook"]\n# END AI data kit: notify\n'
        path.write_text(legacy + path.read_text())
        data["blocks"].insert(0, legacy)
        for key in ["hook_entry", "hooks_original", "adapter_original", "adapter_set", "hooks_dir_created"]:
            data.pop(key)
        record.write_text(json.dumps(data))
        (self.folder / "hooks.json").unlink()
        (self.folder / "hooks/mlflow_stop.py").unlink()
        (self.folder / "hooks").rmdir()
        self.run_install()
        self.assertNotIn("notify", tomllib.loads(path.read_text()))
        self.assertEqual(len(json.loads((self.folder / "hooks.json").read_text())["hooks"]["Stop"]), 1)
        self.run_install("--uninstall")
        self.assertFalse(self.folder.exists())

    def test_symlinked_hook_paths_are_rejected_without_writes(self):
        self.folder.mkdir()
        target = self.project / "outside"
        target.write_text("untouched")
        (self.folder / "hooks.json").symlink_to(target)
        self.run_install(success=False)
        self.assertEqual(target.read_text(), "untouched")
        self.assertFalse((self.folder / "config.toml").exists())

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
