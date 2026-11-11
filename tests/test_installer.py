"""Test unified agent selection and install/uninstall behavior."""
import os
import json
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
                "relative = url.split('/v1.1.0/', 1)[1]\n"
                "shutil.copyfile(Path(os.environ['KIT_SOURCE']) / relative, sys.argv[4])\n"
                "with open(os.environ['KIT_FETCH_LOG'], 'a') as log: log.write(url + '\\n')\n"
            )
            fake_curl.chmod(0o755)
            log = Path(tmp) / "fetch.log"
            env = dict(os.environ, PATH=tmp + os.pathsep + os.environ["PATH"],
                       KIT_SOURCE=str(INSTALLER.parent), KIT_FETCH_LOG=str(log), AI_KIT_BRANCH="main")
            for selection, files in (
                ("--codex", ["codex/config.toml", "codex/mlflow-tracing.json", "codex/AGENTS.md"]),
                ("--claude", ["claude/settings.json", "claude/hooks/install-plugins.py", "claude/CLAUDE.md", ".mcp.json"]),
            ):
                with self.subTest(selection=selection):
                    log.write_text("")
                    result = subprocess.run(
                        ["bash", "-c", 'bash <(cat "$1") "$2" "$3"', "_", str(INSTALLER), selection, str(self.project)],
                        env=env, capture_output=True, text=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    base = "https://raw.githubusercontent.com/Yuzhouboat/ai-agent-data-toolkit/v1.1.0/"
                    self.assertEqual(log.read_text().splitlines(), [base + f for f in ["skills/check-connectors/SKILL.md", *files]])
                    folder = ".codex" if selection == "--codex" else ".claude"
                    manifest = json.loads((self.project / folder / "ai-kit.json").read_text())
                    self.assertEqual(manifest["version"], "v1.1.0")
                    self.assertIn("v1.1.0", result.stdout)
                    self.install(selection, "--uninstall")

    def test_version_upgrade_preserves_settings_and_uninstall_history(self):
        for unversioned in (False, True):
            with self.subTest(unversioned=unversioned), tempfile.TemporaryDirectory(prefix="release-kit-") as tmp:
                kit = Path(tmp)
                for relative in ("install.sh", ".mcp.json", "claude/settings.json",
                                 "claude/hooks/install-plugins.py", "codex/config.toml", "codex/mlflow-tracing.json",
                                 "skills/check-connectors/SKILL.md", "claude/CLAUDE.md", "codex/AGENTS.md"):
                    target = kit / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(INSTALLER.parent / relative, target)
                claude = self.project / ".claude/settings.local.json"
                codex = self.project / ".codex/config.toml"
                originals = {claude: '{"env": {"PERSONAL_SETTING": "keep"}}\n',
                             codex: 'model = "personal"\n'}
                for path, text in originals.items():
                    path.parent.mkdir(exist_ok=True)
                    path.write_text(text)
                self.install()
                records = [self.project / folder / "ai-kit.json" for folder in (".claude", ".codex")]
                if unversioned:
                    for record in records:
                        manifest = json.loads(record.read_text())
                        manifest.pop("version")
                        record.write_text(json.dumps(manifest))
                script = kit / "install.sh"
                script.write_text(script.read_text().replace('KIT_VERSION="v1.1.0"', 'KIT_VERSION="v1.2.0"'))
                template = kit / "codex/config.toml"
                template.write_text(template.read_text().replace("startup_timeout_sec = 120", "startup_timeout_sec = 150"))
                template = kit / "claude/settings.json"
                data = json.loads(template.read_text())
                data.setdefault("env", {})["RELEASE_TEST"] = "new"
                template.write_text(json.dumps(data))
                template = kit / "skills/check-connectors/SKILL.md"
                template.write_text(template.read_text() + "\nNew release instructions.\n")
                result = subprocess.run(["bash", str(script), str(self.project)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                for record in records:
                    self.assertEqual(json.loads(record.read_text())["version"], "v1.2.0")
                self.assertIn('model = "personal"', codex.read_text())
                self.assertIn("startup_timeout_sec = 150", codex.read_text())
                self.assertEqual(json.loads(claude.read_text())["env"]["PERSONAL_SETTING"], "keep")
                self.assertEqual(json.loads(claude.read_text())["env"]["RELEASE_TEST"], "new")
                for root in (".claude", ".agents"):
                    self.assertIn("New release instructions.", (self.project / root / "skills/check-connectors/SKILL.md").read_text())
                self.install("--uninstall")
                for path, text in originals.items():
                    self.assertEqual(path.read_text(), text)
                    path.unlink()
                    path.parent.rmdir()

    def test_remote_template_failure_leaves_project_untouched(self):
        with tempfile.TemporaryDirectory(prefix="failed-release-") as tmp:
            curl = Path(tmp) / "curl"
            curl.write_text("#!/bin/sh\nexit 22\n")
            curl.chmod(0o755)
            env = dict(os.environ, PATH=tmp + os.pathsep + os.environ["PATH"])
            result = subprocess.run(
                ["bash", "-c", 'bash <(cat "$1") "$2"', "_", str(INSTALLER), str(self.project)],
                env=env, capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(list(self.project.iterdir()), [])

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
        original = (INSTALLER.parent / "claude/hooks/install-plugins.py").read_text()
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
            for relative in ("install.sh", ".mcp.json", "claude/settings.json", "claude/hooks/install-plugins.py",
                             "skills/check-connectors/SKILL.md", "claude/CLAUDE.md", "codex/AGENTS.md"):
                target = kit / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(INSTALLER.parent / relative, target)
            original = (kit / "claude/hooks/install-plugins.py").read_text()
            hook = self.project / ".claude/hooks/install-plugins.py"
            hook.parent.mkdir(parents=True)
            hook.write_text(original)
            def run(*args):
                result = subprocess.run(["bash", str(kit / "install.sh"), "--claude", *args, str(self.project)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            run()
            updated = original + "\n# Updated kit hook\n"
            (kit / "claude/hooks/install-plugins.py").write_text(updated)
            run()
            self.assertEqual(hook.read_text(), updated)
            run("--uninstall")
            self.assertEqual(hook.read_text(), original)

    def test_uninstall_without_records_is_noop(self):
        self.install("--uninstall")
        self.assertEqual(list(self.project.iterdir()), [])

    def test_project_instructions_append_once_and_restore_existing_guidance(self):
        for selector, filename, source in (("--claude", "CLAUDE.md", "claude/CLAUDE.md"),
                                           ("--codex", "AGENTS.md", "codex/AGENTS.md")):
            with self.subTest(selector=selector):
                path = self.project / filename
                original = "# Project guidance\n\nKeep the user's coding conventions."
                path.write_text(original)
                expected = original + "\n\n" + (INSTALLER.parent / source).read_text()
                self.install(selector)
                self.assertEqual(path.read_text(), expected)
                self.install(selector)
                self.assertEqual(path.read_text(), expected)
                self.install(selector, "--uninstall")
                self.assertEqual(path.read_text(), original)
                path.unlink()

    def test_tracked_project_instructions_stay_unchanged_and_print_manual_step(self):
        self.git("init")
        for selector, filename in (("--claude", "CLAUDE.md"), ("--codex", "AGENTS.md")):
            with self.subTest(selector=selector):
                path = self.project / filename
                original = "# Shared guidance\n"
                path.write_text(original)
                self.git("add", filename)
                before = self.git("status", "--porcelain")
                result = self.install(selector)
                self.assertIn("instruction manually", result.stdout)
                self.assertIn("check-connectors", result.stdout)
                self.assertEqual(path.read_text(), original)
                self.assertEqual(self.git("status", "--porcelain"), before)
                self.install(selector, "--uninstall")
                self.assertEqual(path.read_text(), original)
                self.assertEqual(self.git("status", "--porcelain"), before)

    def test_edited_project_instructions_block_update_and_survive_uninstall(self):
        for selector, filename in (("--claude", "CLAUDE.md"), ("--codex", "AGENTS.md")):
            with self.subTest(selector=selector):
                self.install(selector)
                path = self.project / filename
                edited = path.read_text() + "\nMy later edit.\n"
                path.write_text(edited)
                self.install(selector, success=False)
                self.install(selector, "--uninstall")
                self.assertEqual(path.read_text(), edited)
                path.unlink()

    def test_new_claude_instructions_keep_existing_agents_guidance_visible(self):
        agents = self.project / "AGENTS.md"
        original = "# Existing shared project guidance\n"
        agents.write_text(original)
        self.install("--claude")
        claude = self.project / "CLAUDE.md"
        self.assertTrue(claude.read_text().startswith("@AGENTS.md\n"))
        first = claude.read_text()
        self.install("--claude")
        self.assertEqual(claude.read_text(), first)
        self.assertEqual(agents.read_text(), original)
        self.install("--claude", "--uninstall")
        self.assertFalse(claude.exists())
        self.assertEqual(agents.read_text(), original)

    def test_project_instruction_symlinks_are_refused(self):
        for selector, filename in (("--claude", "CLAUDE.md"), ("--codex", "AGENTS.md")):
            with self.subTest(selector=selector), tempfile.TemporaryDirectory(prefix="external-instructions-") as tmp:
                target = Path(tmp) / filename
                target.write_text("# External guidance\n")
                path = self.project / filename
                path.symlink_to(target)
                self.install(selector, success=False)
                self.assertEqual(target.read_text(), "# External guidance\n")
                path.unlink()
                self.install(selector)
                original = path.read_text()
                path.unlink()
                path.symlink_to(target)
                self.install(selector, "--uninstall", success=False)
                self.assertEqual(target.read_text(), "# External guidance\n")
                path.unlink()
                path.write_text(original)
                self.install(selector, "--uninstall")

    def test_connector_skill_installs_only_for_selected_agent_and_preserves_edits(self):
        source = (INSTALLER.parent / "skills/check-connectors/SKILL.md").read_text()
        for selector, root, other in (("--claude", ".claude", ".agents"), ("--codex", ".agents", ".claude")):
            with self.subTest(selector=selector):
                result = self.install(selector)
                skill = self.project / root / "skills/check-connectors/SKILL.md"
                self.assertEqual(skill.read_text(), source)
                self.assertFalse((self.project / other).exists())
                self.assertIn("check-connectors", result.stdout)
                edited = source + "\nPersonal instructions.\n"
                skill.write_text(edited)
                self.install(selector, success=False)
                self.assertEqual(skill.read_text(), edited)
                self.install(selector, "--uninstall")
                self.assertEqual(skill.read_text(), edited)
                shutil.rmtree(self.project / root)

    def test_connector_skill_conflict_is_detected_before_agent_config_is_written(self):
        for selector, root in (("--claude", ".claude"), ("--codex", ".agents")):
            with self.subTest(selector=selector):
                skill = self.project / root / "skills/check-connectors/SKILL.md"
                skill.parent.mkdir(parents=True)
                skill.write_text("My existing connector skill.\n")
                self.install(selector, success=False)
                self.assertEqual(skill.read_text(), "My existing connector skill.\n")
                self.assertFalse((self.project / ".claude/settings.local.json").exists())
                self.assertFalse((self.project / ".codex/config.toml").exists())
                shutil.rmtree(self.project / root)

    def test_existing_identical_connector_skill_and_neighbor_survive_uninstall(self):
        for selector, root in (("--claude", ".claude"), ("--codex", ".agents")):
            with self.subTest(selector=selector):
                skill = self.project / root / "skills/check-connectors/SKILL.md"
                skill.parent.mkdir(parents=True)
                original = (INSTALLER.parent / "skills/check-connectors/SKILL.md").read_text()
                skill.write_text(original)
                neighbor = skill.parent.parent / "personal.txt"
                neighbor.write_text("keep\n")
                self.install(selector)
                self.install(selector, "--uninstall")
                self.assertEqual(skill.read_text(), original)
                self.assertEqual(neighbor.read_text(), "keep\n")
                shutil.rmtree(self.project / root)

    def test_connector_skill_symlinks_are_refused_on_install_and_uninstall(self):
        for selector, root in (("--claude", ".claude"), ("--codex", ".agents")):
            with self.subTest(selector=selector), tempfile.TemporaryDirectory(prefix="external-skill-") as tmp:
                external = Path(tmp) / "SKILL.md"
                external.write_text("external skill\n")
                skill = self.project / root / "skills/check-connectors/SKILL.md"
                skill.parent.mkdir(parents=True)
                skill.symlink_to(external)
                self.install(selector, success=False)
                self.assertEqual(external.read_text(), "external skill\n")
                skill.unlink()
                self.install(selector)
                skill.unlink()
                skill.symlink_to(external)
                self.install(selector, "--uninstall", success=False)
                self.assertEqual(external.read_text(), "external skill\n")
                skill.unlink()
                skill.write_text((INSTALLER.parent / "skills/check-connectors/SKILL.md").read_text())
                self.install(selector, "--uninstall")
                shutil.rmtree(self.project / root)

    def test_upgrade_install_without_skill_metadata_adds_connector_skill(self):
        self.install()
        # Reproduce the manifests and paths from before connector skills were included.
        claude_record = self.project / ".claude/ai-kit.json"
        manifest = json.loads(claude_record.read_text())
        rel = ".claude/skills/check-connectors/SKILL.md"
        manifest["copied"].pop(rel)
        manifest["dirs"] = [d for d in manifest["dirs"] if not d.startswith(".claude/skills")]
        manifest.pop("version")
        claude_record.write_text(json.dumps(manifest))
        shutil.rmtree(self.project / ".claude/skills")
        codex_record = self.project / ".codex/ai-kit.json"
        manifest = json.loads(codex_record.read_text())
        for key in ("skill_original", "skill_set", "skill_dirs", "version"):
            manifest.pop(key, None)
        codex_record.write_text(json.dumps(manifest))
        shutil.rmtree(self.project / ".agents")
        self.install()
        for root in (".claude", ".agents"):
            self.assertTrue((self.project / root / "skills/check-connectors/SKILL.md").exists())
        self.install("--uninstall")
        self.assertEqual(list(self.project.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
