from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1]))

from scripts import orchestra_dashboard as dashboard
from scripts import orchestra_telemetry as telemetry


class OrchestraDashboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = telemetry.TelemetryStore(Path(self.temp.name) / "telemetry")
        self._make_fixture_ledger()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _end_after(self, started_at: str, seconds: int) -> str:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        return (started + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")

    def _make_exact_turn(self) -> dict[str, str]:
        turn_id = "turn-exact-1"
        start = telemetry.create_run(
            self.store,
            task_label="codex-turn",
            task_id=turn_id,
            project_label="alpha",
            project_repo_label="repo-alpha",
            project_branch="main",
            project_kind="GIT",
            mode="DIRECT",
            root_model="gpt-5.6-luna",
            record_type="turn_start",
            measurement_generation="TURN_LEVEL_V1_2",
            session_id="session-1",
            turn_id=turn_id,
            speed_mode="FAST",
            speed_mode_source="LAUNCHER_EXPLICIT",
        )
        telemetry.observe_metadata(
            self.store,
            start["run_id"],
            source_kind="TEST_METADATA",
            project_label="alpha",
            project_repo_label="repo-alpha",
            project_branch="main",
            root_model="gpt-5.6-luna",
            speed_mode="FAST",
            speed_mode_source="LAUNCHER_EXPLICIT",
            measurement_generation="TURN_LEVEL_V1_2",
        )
        telemetry.ingest_launcher_usage(
            self.store,
            start["run_id"],
            {
                "model_requests": 1,
                "input_tokens": 80,
                "cached_input_tokens": 20,
                "cache_write_input_tokens": 0,
                "non_cached_input_tokens": 60,
                "output_tokens": 15,
                "reasoning_output_tokens": 5,
                "total_tokens": 95,
            },
            session_id="session-1",
            turn_id=turn_id,
            measurement_generation="TURN_LEVEL_V1_2",
        )
        telemetry.observe_worker(
            self.store,
            start["run_id"],
            worker_id="worker-1",
            turn_id=turn_id,
            measurement_generation="TURN_LEVEL_V1_2",
            model="gpt-5.6-luna",
            launch_status="COMPLETED",
        )
        telemetry.ingest_launcher_usage(
            self.store,
            start["run_id"],
            {
                "model_requests": 1,
                "input_tokens": 10,
                "cached_input_tokens": 0,
                "cache_write_input_tokens": 0,
                "non_cached_input_tokens": 10,
                "output_tokens": 2,
                "reasoning_output_tokens": 0,
                "total_tokens": 12,
            },
            attribution_role="WORKER",
            worker_id="worker-1",
            turn_id=turn_id,
            measurement_generation="TURN_LEVEL_V1_2",
        )
        telemetry.finalize_run(
            self.store,
            start["run_id"],
            record_type="turn_finalize",
            ended_at_utc=self._end_after(start["started_at_utc"], 2),
            usage={
                "input_tokens": 80,
                "cached_input_tokens": 20,
                "cache_write_input_tokens": 0,
                "non_cached_input_tokens": 60,
                "output_tokens": 15,
                "reasoning_output_tokens": 5,
                "total_tokens": 95,
            },
            usage_source="ORCHESTRA_LAUNCHER",
            usage_quality="EXACT",
            measurement_generation="TURN_LEVEL_V1_2",
            session_id="session-1",
            turn_id=turn_id,
            turn_status="COMPLETED",
        )
        return {"run_id": start["run_id"], "turn_id": turn_id}

    def _make_interrupted_turn(self) -> None:
        turn_id = "turn-interrupted-1"
        start = telemetry.create_run(
            self.store,
            task_label="codex-turn",
            task_id=turn_id,
            project_label="beta",
            project_repo_label="repo-beta",
            project_kind="GIT",
            record_type="turn_start",
            measurement_generation="TURN_LEVEL_V1_2",
            session_id="session-2",
            turn_id=turn_id,
        )
        telemetry.observe_interruption(
            self.store,
            start["run_id"],
            session_id="session-2",
            thread_id="thread-2",
            turn_id=turn_id,
            measurement_generation="TURN_LEVEL_V1_2",
        )
        telemetry.finalize_run(
            self.store,
            start["run_id"],
            record_type="turn_finalize",
            ended_at_utc=self._end_after(start["started_at_utc"], 3),
            usage_quality="UNKNOWN",
            measurement_generation="TURN_LEVEL_V1_2",
            session_id="session-2",
            turn_id=turn_id,
            turn_status="INTERRUPTED",
        )

    def _make_open_turn(self) -> None:
        telemetry.create_run(
            self.store,
            task_label="codex-turn",
            task_id="turn-open-1",
            project_label="alpha",
            project_kind="GIT",
            record_type="turn_start",
            measurement_generation="TURN_LEVEL_V1_2",
            session_id="session-3",
            turn_id="turn-open-1",
            turn_status="STARTED",
        )

    def _make_excluded_records(self) -> None:
        session = telemetry.create_run(self.store, task_label="codex-session", record_type="run_start")
        telemetry.finalize_run(self.store, session["run_id"], record_type="run_finalize", result={"completed": True})
        synthetic = telemetry.create_run(
            self.store,
            task_label="codex-turn",
            task_id="turn-synthetic-1",
            record_type="turn_start",
            measurement_generation="TURN_LEVEL_V1_2",
            session_id="session-synthetic",
            turn_id="turn-synthetic-1",
        )
        telemetry.ingest_synthetic_usage(self.store, synthetic["run_id"], {"total_tokens": 999})
        telemetry.finalize_run(self.store, synthetic["run_id"], record_type="turn_finalize", turn_status="COMPLETED")
        telemetry.import_manual(self.store, label="old", source_note="separate")

    def _make_fixture_ledger(self) -> None:
        self._make_exact_turn()
        self._make_interrupted_turn()
        self._make_open_turn()
        self._make_excluded_records()

    def test_snapshot_is_read_only_and_preserves_unknown(self) -> None:
        before = self.store.ledger_path.read_bytes()
        snapshot = dashboard.load_snapshot(self.store, cache=None)
        after = self.store.ledger_path.read_bytes()
        self.assertEqual(before, after)
        self.assertEqual(snapshot["overview"]["total_turns"], 3)
        self.assertEqual(snapshot["overview"]["completed"], 1)
        self.assertEqual(snapshot["overview"]["interrupted"], 1)
        self.assertEqual(snapshot["overview"]["open"], 1)
        self.assertEqual(snapshot["overview"]["exact_tokens"]["total"], 95)
        self.assertEqual(snapshot["overview"]["root_vs_worker_exact_tokens"], {"root": 95, "worker": 12, "orchestra": 107})
        self.assertEqual(snapshot["speed_comparison"]["FAST"]["record_count"], 1)
        self.assertEqual(snapshot["speed_comparison"]["STANDARD"]["record_count"], 0)
        open_row = next(row for row in snapshot["turns"] if row["status"] == "OPEN")
        self.assertIsNone(open_row["total_tokens"])
        self.assertIsNone(open_row["duration_seconds"])
        self.assertEqual(snapshot["exclusions"]["session_level_runs_excluded"], 1)
        self.assertEqual(snapshot["exclusions"]["synthetic_runs_excluded"], 1)
        self.assertEqual(snapshot["exclusions"]["legacy_manual_observations_excluded"], 1)

    def test_rebuildable_sqlite_cache_is_derived_only(self) -> None:
        cache = Path(self.temp.name) / "dashboard-cache.sqlite3"
        before = self.store.ledger_path.read_bytes()
        snapshot = dashboard.load_snapshot(self.store, cache=cache, rebuild=True)
        self.assertTrue(cache.is_file())
        cached = dashboard.load_snapshot(self.store, cache=cache)
        self.assertEqual(cached, snapshot)
        connection = sqlite3.connect(str(cache))
        try:
            payload = connection.execute("SELECT payload FROM dashboard_snapshot WHERE id = 1").fetchone()[0]
        finally:
            connection.close()
        self.assertNotIn("transcript_path", payload.lower())
        self.assertNotIn("response_text", payload.lower())
        self.assertNotIn("secret", payload.lower())
        self.assertEqual(self.store.ledger_path.read_bytes(), before)

    def test_partial_final_jsonl_line_is_ignored_until_next_refresh(self) -> None:
        self.store.ledger_path.write_bytes(self.store.ledger_path.read_bytes() + b'{"schema":"orchestra_telemetry_v1"')
        snapshot = dashboard.load_snapshot(self.store, cache=None)
        self.assertEqual(snapshot["overview"]["total_turns"], 3)
        self.assertTrue(snapshot["source"]["partial_final_line_ignored"])

    def test_cache_cannot_target_ledger_and_html_is_self_contained(self) -> None:
        with self.assertRaises(dashboard.DashboardError):
            dashboard._cache_path(self.store, str(self.store.ledger_path))
        snapshot = dashboard.load_snapshot(self.store, cache=None)
        report = dashboard.build_html(snapshot)
        self.assertIn("Orchestra telemetry dashboard", report)
        self.assertIn("Root vs worker exact usage", report)
        self.assertNotIn("thread-2", report)
        self.assertNotIn("raw transcript", report.lower())

    def test_non_loopback_host_is_rejected(self) -> None:
        self.assertEqual(dashboard.main(["--store", str(self.store.root), "serve", "--host", "0.0.0.0", "--no-browser"]), 2)
if __name__ == "__main__":
    unittest.main()
