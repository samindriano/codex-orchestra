import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from scripts import codex_benchmark_launcher as launcher


class BenchmarkLauncherTests(unittest.TestCase):
    def test_standard_command_uses_only_documented_default_override(self) -> None:
        command = launcher.codex_argv("standard", ["--profile", "global-luna"], executable="codex.exe")
        self.assertEqual(
            command,
            ["codex.exe", "--profile", "global-luna", "-c", 'service_tier="default"'],
        )

    def test_fast_command_uses_documented_fast_pair(self) -> None:
        command = launcher.codex_argv("fast", [], executable="codex.exe")
        self.assertEqual(
            command,
            ["codex.exe", "-c", 'service_tier="fast"', "-c", "features.fast_mode=true"],
        )

    def test_metadata_is_path_free_and_hashes_normalized_configuration(self) -> None:
        metadata = launcher.launcher_metadata("fast")
        self.assertEqual(metadata["speed_mode"], "FAST")
        self.assertEqual(metadata["speed_mode_source"], "LAUNCHER_EXPLICIT")
        self.assertEqual(metadata["config_hash"], launcher._config_hash({"config_overrides": metadata["config_overrides"]}))
        self.assertNotIn(str(Path.home()), json.dumps(metadata))
        self.assertNotIn("prompt", json.dumps(metadata).lower())
        self.assertEqual(launcher.launcher_metadata("standard", ["--profile", "global-astra-low"])["profile"], "global-astra-low")

    def test_run_scopes_metadata_to_child_and_does_not_mutate_parent_environment(self) -> None:
        before = os.environ.get(launcher.METADATA_ENV)
        observed: dict[str, object] = {}

        def fake_run(command: list[str], *, env: dict[str, str], check: bool) -> subprocess.CompletedProcess[str]:
            observed["command"] = command
            observed["metadata"] = json.loads(env[launcher.METADATA_ENV])
            observed["check"] = check
            return subprocess.CompletedProcess(command, 7)

        with patch.object(launcher, "shutil") as shutil_mock, patch.object(launcher.subprocess, "run", side_effect=fake_run):
            shutil_mock.which.return_value = "codex.exe"
            self.assertEqual(launcher.run("standard", ["--profile", "global-luna"]), 7)
        self.assertEqual(observed["command"], ["codex.exe", "--profile", "global-luna", "-c", 'service_tier="default"'])
        self.assertEqual(observed["metadata"]["speed_mode_source"], "LAUNCHER_EXPLICIT")
        self.assertFalse(observed["check"])
        self.assertEqual(os.environ.get(launcher.METADATA_ENV), before)

    def test_user_speed_overrides_fail_closed(self) -> None:
        for args in (
            ["-c", "service_tier=priority"],
            ["--config=features.fast_mode=false"],
            ["--enable", "fast_mode"],
            ["--disable=fast_mode"],
        ):
            with self.subTest(args=args):
                with self.assertRaises(launcher.LauncherError):
                    launcher.codex_argv("fast", args)

    def test_missing_codex_executable_is_reported(self) -> None:
        with patch.object(launcher.shutil, "which", return_value=None):
            with self.assertRaisesRegex(launcher.LauncherError, "not found"):
                launcher.run("standard", [])


if __name__ == "__main__":
    unittest.main()
