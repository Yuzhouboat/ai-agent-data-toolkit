"""Test unified agent selection and install/uninstall behavior."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

INSTALLER = Path(__file__).resolve().parents[1] / "install.sh"


class UnifiedInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="both-agent-kit-")
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)

    def install(self, *args, success=True):
        result = subprocess.run(["bash", str(INSTALLER), *args, str(self.project)], capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.project), *args], capture_output=True, text=True, check=True).stdout

    def test_default_installs_both_and_reinstalls_without_duplicates(self):
        result = self.install()
        self.assertIn("Configured agent selection: both.", result.stdout)
        self.assertIn("rerun this installer --uninstall", result.stdout)
        self.assertTrue((self.project / ".claude/settings.local.json").exists())
        self.assertTrue((self.project / ".mcp.json").exists())
        self.assertTrue((self.project / ".codex/config.toml").exists())
        settings = (self.project / ".claude/settings.local.json").read_text()
        codex = (self.project / ".codex/config.toml").read_text()
        self.install()
        self.assertEqual(settings, (self.project / ".claude/settings.local.json").read_text())
        self.assertEqual(codex, (self.project / ".codex/config.toml").read_text())
        self.install("--uninstall")
        self.assertEqual(list(self.project.iterdir()), [])

    def test_claude_selector_only_installs_claude(self):
        self.install("--claude")
        self.assertTrue((self.project / ".claude/settings.local.json").exists())
        self.assertFalse((self.project / ".codex").exists())
        self.install("--uninstall")  # missing Codex is skipped
        self.assertEqual(list(self.project.iterdir()), [])

    def test_codex_selector_only_installs_codex(self):
        self.install("--codex")
        self.assertTrue((self.project / ".codex/config.toml").exists())
        self.assertFalse((self.project / ".claude").exists())
        self.assertFalse((self.project / ".mcp.json").exists())
        self.install("--uninstall")  # missing Claude is skipped
        self.assertEqual(list(self.project.iterdir()), [])

    def test_selected_uninstall_preserves_other_agent(self):
        self.install()
        self.install("--claude", "--uninstall")
        self.assertFalse((self.project / ".claude").exists())
        self.assertTrue((self.project / ".codex/config.toml").exists())
        self.install("--codex", "--uninstall")
        self.assertEqual(list(self.project.iterdir()), [])

    def test_default_local_hides_both_and_uninstalls(self):
        self.git("init")
        self.install()
        self.assertTrue((self.project / ".claude/settings.local.json").exists())
        self.assertTrue((self.project / ".codex/config.toml").exists())
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.install("--uninstall")
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertFalse((self.project / ".claude").exists())
        self.assertFalse((self.project / ".codex").exists())

    def test_default_preserves_tracked_claude_settings_and_gitignore(self):
        self.git("init")
        settings = self.project / ".claude/settings.json"
        settings.parent.mkdir()
        original_settings = '{"env": {"PROJECT_SETTING": "keep"}}\n'
        settings.write_text(original_settings)
        ignore = self.project / ".gitignore"
        original_ignore = "build/\n"
        ignore.write_text(original_ignore)
        self.git("add", ".claude/settings.json", ".gitignore")
        before = self.git("status", "--porcelain")
        self.install()
        self.assertEqual(settings.read_text(), original_settings)
        self.assertEqual(ignore.read_text(), original_ignore)
        self.assertEqual(self.git("status", "--porcelain"), before)
        self.install("--uninstall")
        self.assertEqual(settings.read_text(), original_settings)
        self.assertEqual(ignore.read_text(), original_ignore)
        self.assertEqual(self.git("status", "--porcelain"), before)

    def test_codex_conflict_leaves_claude_untouched(self):
        folder = self.project / ".codex"
        folder.mkdir()
        (folder / "config.toml").write_text('notify = ["existing"]\n')
        self.install(success=False)
        self.assertFalse((self.project / ".claude").exists())

    def test_invalid_argument_combinations_do_not_install(self):
        for flags in (("--claude", "--codex"), ("--local",), ("--unknown",)):
            with self.subTest(flags=flags):
                self.install(*flags, success=False)
                self.assertEqual(list(self.project.iterdir()), [])

    def test_process_substitution_downloads_selected_templates(self):
        # Simulate curl installation through /dev/fd, without network access.
        with tempfile.TemporaryDirectory(prefix="kit-curl-") as tmp:
            fake_curl = Path(tmp) / "curl"
            fake_curl.write_text(
                f"#!{sys.executable}\n"
                "import os, shutil, sys\n"
                "from pathlib import Path\n"
                "url = sys.argv[2]\n"
                "relative = url.split('/main/', 1)[1]\n"
                "shutil.copyfile(Path(os.environ['KIT_SOURCE']) / relative, sys.argv[4])\n"
                "with open(os.environ['KIT_FETCH_LOG'], 'a') as log: log.write(relative + '\\n')\n"
            )
            fake_curl.chmod(0o755)
            log = Path(tmp) / "fetch.log"
            env = dict(os.environ, PATH=tmp + os.pathsep + os.environ["PATH"],
                       KIT_SOURCE=str(INSTALLER.parent), KIT_FETCH_LOG=str(log), AI_KIT_BRANCH="main")
            result = subprocess.run(
                ["bash", "-c", 'bash <(cat "$1") --codex "$2"', "_", str(INSTALLER), str(self.project)],
                env=env, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(log.read_text().splitlines(), ["codex/config.toml", "codex/mlflow-tracing.json"])
            self.assertTrue((self.project / ".codex/config.toml").exists())
            self.assertFalse((self.project / ".claude").exists())

    def test_local_install_refuses_different_tracked_hook(self):
        self.git("init")
        hook = self.project / ".claude/hooks/install-plugins.py"
        hook.parent.mkdir(parents=True)
        original = "# existing project hook\n"
        hook.write_text(original)
        self.git("add", ".claude/hooks/install-plugins.py")
        self.install("--claude", success=False)
        self.assertEqual(hook.read_text(), original)
        self.assertFalse((self.project / ".claude/settings.local.json").exists())

    def test_uninstall_preserves_preexisting_identical_hook(self):
        hook = self.project / ".claude/hooks/install-plugins.py"
        hook.parent.mkdir(parents=True)
        original = (INSTALLER.parent / ".claude/hooks/install-plugins.py").read_text()
        hook.write_text(original)
        self.install("--claude")
        self.install("--claude", "--uninstall")
        self.assertTrue(hook.exists())
        self.assertEqual(hook.read_text(), original)

    def test_codex_rejects_symlinked_configuration_directory(self):
        with tempfile.TemporaryDirectory(prefix="external-codex-") as tmp:
            target = Path(tmp)
            config = target / "config.toml"
            config.write_text('model = "personal"\n')
            (self.project / ".codex").symlink_to(target, target_is_directory=True)
            self.install("--codex", success=False)
            self.assertEqual(config.read_text(), 'model = "personal"\n')
            self.assertFalse((target / "ai-kit.json").exists())

    def test_codex_rejects_symlinked_config_file(self):
        with tempfile.TemporaryDirectory(prefix="external-config-") as tmp:
            target = Path(tmp) / "config.toml"
            target.write_text('model = "personal"\n')
            folder = self.project / ".codex"
            folder.mkdir()
            (folder / "config.toml").symlink_to(target)
            self.install("--codex", success=False)
            self.assertEqual(target.read_text(), 'model = "personal"\n')

    def test_claude_local_keeps_existing_local_mcp_registration(self):
        self.git("init")
        (self.project / ".mcp.json").write_text('{"mcpServers": {}}\n')
        self.git("add", ".mcp.json")
        with tempfile.TemporaryDirectory(prefix="fake-claude-") as tmp:
            cli = Path(tmp) / "claude"
            log = Path(tmp) / "calls.log"
            cli.write_text(
                f"#!{sys.executable}\n"
                "import os, sys\n"
                "with open(os.environ['CLAUDE_TEST_LOG'], 'a') as log: log.write(' '.join(sys.argv[1:]) + '\\n')\n"
                "# Simulate add-json refusing an existing local registration.\n"
                "sys.exit(1)\n"
            )
            cli.chmod(0o755)
            with patch.dict(os.environ, PATH=tmp + os.pathsep + os.environ["PATH"], CLAUDE_TEST_LOG=str(log)):
                result = self.install("--claude")
                self.assertIn("couldn't add MCP server", result.stdout)
                self.install("--claude", "--uninstall")
            calls = log.read_text()
            self.assertIn("mcp add-json", calls)
            self.assertNotIn("mcp remove", calls)

    def test_hook_update_restores_original_even_when_first_install_was_identical(self):
        with tempfile.TemporaryDirectory(prefix="updated-kit-") as tmp:
            kit = Path(tmp)
            for relative in ("install.sh", ".mcp.json", ".claude/settings.json", ".claude/hooks/install-plugins.py"):
                target = kit / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(INSTALLER.parent / relative, target)
            original = (kit / ".claude/hooks/install-plugins.py").read_text()
            hook = self.project / ".claude/hooks/install-plugins.py"
            hook.parent.mkdir(parents=True)
            hook.write_text(original)
            def run(*args):
                result = subprocess.run(["bash", str(kit / "install.sh"), "--claude", *args, str(self.project)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            run()
            updated = original + "\n# Updated kit hook\n"
            (kit / ".claude/hooks/install-plugins.py").write_text(updated)
            run()
            self.assertEqual(hook.read_text(), updated)
            run("--uninstall")
            self.assertEqual(hook.read_text(), original)

    def test_uninstall_without_records_is_noop(self):
        self.install("--uninstall")
        self.assertEqual(list(self.project.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
