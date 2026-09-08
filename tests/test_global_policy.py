from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))

from scripts import global_policy


class GlobalPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.source = root / "source"
        self.home = root / "codex-home"
        self.home.mkdir()
        self._write_source()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write_source(self) -> None:
        text = {
            "policies/GLOBAL_AGENTS.md": "# Global policy\nCODEX_ORCHESTRA_GLOBAL_POLICY_V1\n",
            "scripts/orchestra_telemetry.py": "#!/usr/bin/env python3\nSYNTHETIC_TELEMETRY_FIXTURE\n",
            "scripts/codex_benchmark_launcher.py": "#!/usr/bin/env python3\nSYNTHETIC_BENCHMARK_LAUNCHER\n",
            "launchers/codex-standard.cmd": "@echo off\nSYNTHETIC_STANDARD_LAUNCHER\n",
            "launchers/codex-fast.cmd": "@echo off\nSYNTHETIC_FAST_LAUNCHER\n",
            "config/hooks.json": json.dumps({
                "description": "CODEX ORCHESTRA TELEMETRY V1 lifecycle hooks",
                "hooks": {
                    event: [{"hooks": [{
                        "type": "command",
                        "command": "python3 \"__CODEX_HOME_POSIX__/scripts/orchestra_telemetry.py\" hook",
                        "command_windows": "py -3 \"__CODEX_HOME_WINDOWS__\\\\scripts\\\\orchestra_telemetry.py\" hook",
                        "timeout": 3,
                    }]}]
                    for event in ("SessionStart", "UserPromptSubmit", "Stop", "SubagentStart", "SubagentStop", "Interrupt", "SessionEnd")
                },
            }),
            "skills/astra-decision-orchestrator/SKILL.md": "# Astra\n",
            "skills/luna-orchestra/SKILL.md": "# Luna\n",
            "skills/orchestrate/SKILL.md": "# Orchestrate\n",
            "config/global-astra.config.toml": (
                'developer_instructions = "ASTRA_ROOT MANUAL_EXPERIMENTAL EXPLICIT_USER_OPT_IN CODEX_ORCHESTRA_GLOBAL_POLICY_V1"\n'
                'model = "gpt-6-astra"\n'
                'model_reasoning_effort = "medium"\n'
            ),
            "config/global-astra-low.config.toml": (
                'developer_instructions = "ASTRA_ROOT MANUAL_EXPERIMENTAL EXPLICIT_USER_OPT_IN CODEX_ORCHESTRA_GLOBAL_POLICY_V1 low"\n'
                'model = "gpt-6-astra"\n'
                'model_reasoning_effort = "low"\n'
            ),
            "config/global-astra-medium.config.toml": (
                'developer_instructions = "ASTRA_ROOT MANUAL_EXPERIMENTAL EXPLICIT_USER_OPT_IN CODEX_ORCHESTRA_GLOBAL_POLICY_V1 medium"\n'
                'model = "gpt-6-astra"\n'
                'model_reasoning_effort = "medium"\n'
            ),
            "config/global-luna.config.toml": (
                'developer_instructions = "LUNA_ROOT CODEX_ORCHESTRA_GLOBAL_POLICY_V1"\n'
                'model = "gpt-5.6-luna"\n'
                'model_reasoning_effort = "xhigh"\n'
            ),
            "config/agents/default.toml": (
                'name = "default"\n'
                'description = "default"\n'
                'developer_instructions = "LUNA_WORKER CODEX_ORCHESTRA_GLOBAL_POLICY_V1 default"\n'
                'model = "gpt-5.6-luna"\n'
                'model_reasoning_effort = "xhigh"\n[agents]\nenabled = false\n'
            ),
            "config/agents/worker.toml": (
                'name = "worker"\n'
                'description = "worker"\n'
                'developer_instructions = "LUNA_WORKER CODEX_ORCHESTRA_GLOBAL_POLICY_V1 worker"\n'
                'model = "gpt-5.6-luna"\n'
                'model_reasoning_effort = "xhigh"\n[agents]\nenabled = false\n'
            ),
            "config/agents/explorer.toml": (
                'name = "explorer"\n'
                'description = "explorer"\n'
                'developer_instructions = "LUNA_WORKER CODEX_ORCHESTRA_GLOBAL_POLICY_V1 explorer"\n'
                'model = "gpt-5.6-luna"\n'
                'model_reasoning_effort = "xhigh"\n[agents]\nenabled = false\n'
            ),
        }
        for relative, contents in text.items():
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents, encoding="utf-8")

    def test_telemetry_is_an_explicit_installer_destination(self) -> None:
        self.assertIn(
            ("scripts/orchestra_telemetry.py", "scripts/orchestra_telemetry.py", "text"),
            global_policy._SOURCE_DESTINATIONS,
        )

    def test_telemetry_installs_verifies_and_unrelated_scripts_do_not(self) -> None:
        self._write_config()
        unrelated = self.source / "scripts/not-telemetry.py"
        unrelated.write_text("should not install\n", encoding="utf-8")
        report = global_policy.install(self.home, source_root=self.source)
        target = self.home / "scripts/orchestra_telemetry.py"
        self.assertIn("scripts/orchestra_telemetry.py", report["changed_files"])
        self.assertEqual(target.read_text(encoding="utf-8"), (self.source / "scripts/orchestra_telemetry.py").read_text(encoding="utf-8"))
        self.assertFalse((self.home / "scripts/not-telemetry.py").exists())
        self.assertEqual(global_policy.verify(self.home, source_root=self.source)["verdict"], "PASS")

    def test_telemetry_source_update_propagates_and_backup_is_created(self) -> None:
        self._write_config()
        first = global_policy.install(self.home, source_root=self.source)
        self.assertIn("scripts/orchestra_telemetry.py", first["changed_files"])
        target = self.home / "scripts/orchestra_telemetry.py"
        old = target.read_text(encoding="utf-8")
        updated = old + "SOURCE_UPDATE_V2\n"
        (self.source / "scripts/orchestra_telemetry.py").write_text(updated, encoding="utf-8")
        second = global_policy.install(self.home, source_root=self.source)
        self.assertIn("scripts/orchestra_telemetry.py", second["changed_files"])
        backup = Path(second["backup_dir"])
        self.assertEqual((backup / "scripts/orchestra_telemetry.py").read_text(encoding="utf-8"), old)
        self.assertEqual(target.read_text(encoding="utf-8"), updated)

    def test_automatic_hooks_merge_with_existing_hooks_and_are_idempotent(self) -> None:
        self._write_config()
        existing = {
            "description": "user hook configuration",
            "hooks": {
                "Stop": [{"hooks": [{"type": "command", "command": "python user_stop.py"}]}],
                "SessionStart": [{"hooks": [{"type": "command", "command": "python user_start.py"}]}],
            },
        }
        target = self.home / "hooks.json"
        target.write_text(json.dumps(existing), encoding="utf-8")
        first = global_policy.install(self.home, source_root=self.source)
        installed = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(installed["description"], "user hook configuration")
        self.assertIn("python user_stop.py", json.dumps(installed))
        for event in ("SessionStart", "SubagentStart", "SubagentStop", "Interrupt", "SessionEnd"):
            self.assertIn(event, installed["hooks"])
        self.assertEqual(global_policy.verify(self.home, source_root=self.source)["verdict"], "PASS")
        second = global_policy.install(self.home, source_root=self.source)
        self.assertEqual(second["changed_files"], [])
        self.assertTrue(first["changed_files"])

    def test_malformed_existing_hooks_fail_without_mutation(self) -> None:
        self._write_config()
        target = self.home / "hooks.json"
        target.write_text("not-json\n", encoding="utf-8")
        before = target.read_bytes()
        with self.assertRaises(global_policy.PolicyError):
            global_policy.install(self.home, source_root=self.source)
        self.assertEqual(target.read_bytes(), before)

    def test_corrupt_or_missing_telemetry_fails_verify(self) -> None:
        self._write_config()
        global_policy.install(self.home, source_root=self.source)
        target = self.home / "scripts/orchestra_telemetry.py"
        target.write_text("corrupt\n", encoding="utf-8")
        with self.assertRaises(global_policy.PolicyError):
            global_policy.verify(self.home, source_root=self.source)
        target.write_text((self.source / "scripts/orchestra_telemetry.py").read_text(encoding="utf-8"), encoding="utf-8")
        target.unlink()
        with self.assertRaises(global_policy.PolicyError):
            global_policy.verify(self.home, source_root=self.source)

    def _write_config(self, contents: str | None = None) -> None:
        self.home.joinpath("config.toml").write_text(
            contents
            or (
                'model = "gpt-5.6-luna"\n'
                'model_reasoning_effort = "xhigh"\n\n'
                '[agents]\n'
                'default_subagent_model = "gpt-5.6-luna"\n'
                'default_subagent_reasoning_effort = "xhigh"\n\n'
                '[agents.default]\n'
                'description = "legacy default"\n'
                'config_file = "./agents/default.toml"\n\n'
                '[agents.worker]\n'
                'description = "legacy worker"\n'
                'config_file = "./agents/worker.toml"\n\n'
                '[agents.explorer]\n'
                'description = "legacy explorer"\n'
                'config_file = "./agents/explorer.toml"\n\n'
                '[plugins.example]\n'
                'enabled = true\n'
            ),
            encoding="utf-8",
        )

    def test_dry_run_does_not_create_directories_or_files(self) -> None:
        self._write_config()
        before = {p.relative_to(self.home).as_posix(): p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        report = global_policy.install(self.home, source_root=self.source, dry_run=True)
        after = {p.relative_to(self.home).as_posix(): p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        self.assertEqual(report["verdict"], "DRY_RUN")
        self.assertTrue(report["changed_files"])
        self.assertEqual(before, after)
        self.assertFalse((self.home / "orchestra-backups").exists())

    def test_install_backs_up_changed_files_and_records_hashes(self) -> None:
        self._write_config()
        (self.home / "AGENTS.md").write_text("old policy\n", encoding="utf-8")
        report = global_policy.install(self.home, source_root=self.source, enable_context_management=True)
        backup = Path(report["backup_dir"])
        self.assertTrue(backup.is_dir())
        self.assertEqual((backup / "AGENTS.md").read_text(encoding="utf-8"), "old policy\n")
        manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "complete")
        installed = {entry["path"]: entry["sha256"] for entry in manifest["installed"]}
        self.assertEqual(installed["AGENTS.md"], global_policy._sha256_file(self.home / "AGENTS.md"))
        config = global_policy._toml_bytes(self.home / "config.toml")
        self.assertTrue(config["features"]["context_management"]["experimental_mode"])
        self.assertEqual(config["agents"]["worker"]["config_file"], "./agents/worker.toml")

    def test_install_configures_loopback_native_otel_without_prompt_logging(self) -> None:
        self._write_config()
        global_policy.install(self.home, source_root=self.source)
        config = global_policy._toml_bytes(self.home / "config.toml")
        self.assertEqual(config["otel"]["environment"], "codex-orchestra-local")
        self.assertFalse(config["otel"]["log_user_prompt"])
        self.assertEqual(config["otel"]["trace_exporter"]["otlp-http"]["endpoint"], "http://127.0.0.1:4318/v1/traces")
        self.assertEqual(config["otel"]["metrics_exporter"]["otlp-http"]["endpoint"], "http://127.0.0.1:4318/v1/metrics")

    def test_unrelated_skill_and_config_settings_are_preserved(self) -> None:
        self._write_config()
        unrelated = self.home / "skills/custom/SKILL.md"
        unrelated.parent.mkdir(parents=True)
        unrelated.write_text("keep me\n", encoding="utf-8")
        before_config = self.home / "config.toml"
        original_config = before_config.read_text(encoding="utf-8") + "\n[plugins.example2]\nenabled = true\n"
        before_config.write_text(original_config, encoding="utf-8")
        global_policy.install(self.home, source_root=self.source)
        self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep me\n")
        installed_config = global_policy._toml_bytes(before_config)
        self.assertTrue(installed_config["plugins"]["example2"]["enabled"])
        self.assertEqual(installed_config["agents"]["default"]["description"], "legacy default")

    def test_existing_root_defaults_are_repaired_and_verify_reports_them(self) -> None:
        self._write_config(
            'model = "gpt-6-astra"\n'
            'model_reasoning_effort = "medium"\n'
            'personality = "pragmatic"\n\n'
            '[agents]\n'
            'default_subagent_model = "gpt-6-astra"\n'
            'default_subagent_reasoning_effort = "medium"\n\n'
            '[plugins.example]\n'
            'enabled = true\n'
        )
        global_policy.install(self.home, source_root=self.source)
        config = global_policy._toml_bytes(self.home / "config.toml")
        self.assertEqual(config["model"], "gpt-5.6-luna")
        self.assertEqual(config["model_reasoning_effort"], "xhigh")
        self.assertEqual(config["agents"]["default_subagent_model"], "gpt-5.6-luna")
        self.assertEqual(config["agents"]["default_subagent_reasoning_effort"], "xhigh")
        self.assertEqual(config["personality"], "pragmatic")
        self.assertTrue(config["plugins"]["example"]["enabled"])
        report = global_policy.verify(self.home, source_root=self.source)
        self.assertEqual(report["model"], "gpt-5.6-luna")
        self.assertEqual(report["model_reasoning_effort"], "xhigh")
        self.assertEqual(report["default_subagent_model"], "gpt-5.6-luna")
        self.assertEqual(report["default_subagent_reasoning_effort"], "xhigh")

    def test_astra_effort_profiles_are_installed_and_validated(self) -> None:
        self._write_config()
        global_policy.install(self.home, source_root=self.source)
        for name, effort in (("global-astra-low.config.toml", "low"), ("global-astra-medium.config.toml", "medium"), ("global-astra.config.toml", "medium")):
            profile = global_policy._toml_bytes(self.home / name)
            self.assertEqual(profile["model"], "gpt-6-astra")
            self.assertEqual(profile["model_reasoning_effort"], effort)
            instructions = profile["developer_instructions"]
            self.assertIn("MANUAL_EXPERIMENTAL", instructions)
            self.assertIn("EXPLICIT_USER_OPT_IN", instructions)
        report = global_policy.verify(self.home, source_root=self.source)
        self.assertEqual(report["verdict"], "PASS")

    def test_second_install_is_idempotent_without_a_new_backup(self) -> None:
        self._write_config(
            'model = "gpt-6-astra"\n'
            'model_reasoning_effort = "medium"\n\n'
            '[agents]\n'
            'default_subagent_model = "gpt-6-astra"\n'
            'default_subagent_reasoning_effort = "medium"\n'
        )
        first = global_policy.install(self.home, source_root=self.source)
        backup_root = self.home / "orchestra-backups"
        backups = sorted(backup_root.iterdir())
        second = global_policy.install(self.home, source_root=self.source)
        self.assertTrue(first["changed_files"])
        self.assertEqual(second["changed_files"], [])
        self.assertEqual(sorted(backup_root.iterdir()), backups)

    def test_second_install_is_idempotent_with_telemetry_destination(self) -> None:
        self._write_config()
        first = global_policy.install(self.home, source_root=self.source)
        backups = sorted((self.home / "orchestra-backups").iterdir())
        second = global_policy.install(self.home, source_root=self.source)
        self.assertTrue(first["changed_files"])
        self.assertEqual(second["changed_files"], [])
        self.assertEqual(sorted((self.home / "orchestra-backups").iterdir()), backups)

    def test_unknown_profile_setting_fails_without_mutation(self) -> None:
        self._write_config()
        target = self.home / "agents/default.toml"
        target.parent.mkdir()
        target.write_text(
            'developer_instructions = "old"\nmodel = "gpt-5.6-luna"\nmodel_reasoning_effort = "xhigh"\ncustom = true\n',
            encoding="utf-8",
        )
        before = target.read_bytes()
        with self.assertRaises(global_policy.PolicyError):
            global_policy.install(self.home, source_root=self.source)
        self.assertEqual(target.read_bytes(), before)
        self.assertFalse((self.home / "orchestra-backups").exists())

    def test_malformed_existing_profile_fails_without_mutation(self) -> None:
        self._write_config()
        target = self.home / "agents/worker.toml"
        target.parent.mkdir()
        target.write_text('developer_instructions = "unterminated\n', encoding="utf-8")
        before = target.read_bytes()
        with self.assertRaises(global_policy.PolicyError):
            global_policy.install(self.home, source_root=self.source)
        self.assertEqual(target.read_bytes(), before)
        self.assertFalse((self.home / "orchestra-backups").exists())

    def test_config_parse_failure_has_no_mutations(self) -> None:
        self._write_config('model = "unterminated\n')
        before = (self.home / "config.toml").read_bytes()
        with self.assertRaises(global_policy.PolicyError):
            global_policy.install(self.home, source_root=self.source)
        self.assertEqual((self.home / "config.toml").read_bytes(), before)
        self.assertFalse((self.home / "orchestra-backups").exists())

    def test_missing_base_config_is_created_with_role_pins(self) -> None:
        report = global_policy.install(self.home, source_root=self.source)
        self.assertIn("config.toml", report["changed_files"])
        config = global_policy._toml_bytes(self.home / "config.toml")
        self.assertEqual(config["agents"]["default"]["config_file"], "./agents/default.toml")
        self.assertEqual(config["agents"]["explorer"]["config_file"], "./agents/explorer.toml")
        self.assertEqual(global_policy.verify(self.home, source_root=self.source)["verdict"], "PASS")

    def test_unknown_nested_profile_setting_fails_without_mutation(self) -> None:
        target = self.home / "agents/default.toml"
        target.parent.mkdir()
        target.write_text(
            (self.source / "config/agents/default.toml").read_text(encoding="utf-8")
            + "\n[agents.extra]\nmax_threads = 99\n",
            encoding="utf-8",
        )
        before = target.read_bytes()
        with self.assertRaises(global_policy.PolicyError):
            global_policy.install(self.home, source_root=self.source)
        self.assertEqual(target.read_bytes(), before)
        self.assertFalse((self.home / "orchestra-backups").exists())

    def test_concurrent_config_edit_is_preserved(self) -> None:
        self._write_config()
        config = self.home / "config.toml"
        concurrent = config.read_bytes() + b"\n# another client edited this file\n"
        copy_backup = global_policy._copy_backup

        def edit_after_backup(source: Path, destination: Path) -> None:
            copy_backup(source, destination)
            if source == config:
                config.write_bytes(concurrent)

        with patch.object(global_policy, "_copy_backup", side_effect=edit_after_backup):
            with self.assertRaisesRegex(global_policy.PolicyError, "changed during installation"):
                global_policy.install(self.home, source_root=self.source, enable_context_management=True)
        self.assertEqual(config.read_bytes(), concurrent)
        self.assertFalse((self.home / "AGENTS.md").exists())

    def test_verify_checks_installed_profiles_and_config(self) -> None:
        self._write_config()
        global_policy.install(self.home, source_root=self.source)
        report = global_policy.verify(self.home, source_root=self.source)
        self.assertEqual(report["verdict"], "PASS")
        (self.home / "agents/explorer.toml").write_text("model = 'wrong'\n", encoding="utf-8")
        with self.assertRaises(global_policy.PolicyError):
            global_policy.verify(self.home, source_root=self.source)


if __name__ == "__main__":
    unittest.main()
