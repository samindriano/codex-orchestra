from __future__ import annotations

import concurrent.futures
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.orchestra_telemetry import (
    DuplicateRecordError,
    LedgerCorruptionError,
    SessionParseError,
    TelemetryError,
    TelemetryStore,
    add_annotation,
    add_snapshot,
    create_run,
    finalize_run,
    handle_hook_event,
    ingest_synthetic_usage,
    ingest_usage,
    parse_session_usage,
    report,
)


class OrchestraTelemetryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = TelemetryStore(Path(self.temp.name) / "orchestra-telemetry")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_synthetic_lifecycle_is_zero_model_overhead_and_offline(self) -> None:
        run = create_run(
            self.store,
            task_label="synthetic-review",
            task_class="REVIEW",
            complexity="SMALL",
            mode="DIRECT",
            root_model="gpt-5.6-luna",
            root_reasoning_effort="xhigh",
        )
        run_id = run["run_id"]
        ingest_synthetic_usage(
            self.store,
            run_id,
            {
                "model_requests": 2,
                "input_tokens": 100,
                "cached_input_tokens": 20,
                "output_tokens": 30,
                "reasoning_output_tokens": 10,
                "total_tokens": 130,
            },
        )
        finalize_run(
            self.store,
            run_id,
            usage={"model_requests": 2, "input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 30, "total_tokens": 130},
            execution={"wall_clock_seconds": 1.5},
            result={"completed": True, "local_validation_status": "PASS"},
        )
        add_annotation(self.store, run_id, reviewer_verdict="PASS", first_pass="PASS")
        result = report(self.store)
        self.assertEqual(result["run_count"], 0)
        self.assertEqual(result["synthetic_run_count"], 1)
        self.assertEqual(result["synthetic_runs_excluded"], 1)
        result_with_fixture = report(self.store, include_synthetic=True)
        self.assertEqual(result_with_fixture["run_count"], 1)
        self.assertEqual(result_with_fixture["groups"][0]["completion_rate"], 1.0)
        self.assertEqual(result_with_fixture["groups"][0]["first_pass_pass_rate"], 1.0)
        self.assertEqual(result_with_fixture["groups"][0]["median_total_tokens"], 130.0)
        for record in self.store.read():
            measurement = record.get("measurement")
            if measurement:
                self.assertEqual(measurement["telemetry_model_requests_added"], 0)
                self.assertEqual(measurement["telemetry_tokens_added"], 0)
                self.assertEqual(measurement["telemetry_worker_launches_added"], 0)
                self.assertEqual(measurement["telemetry_context_tokens_added"], 0)

    def test_parser_reads_only_allowlisted_usage_and_does_not_persist_content(self) -> None:
        source = Path(self.temp.name) / "rollout.jsonl"
        secret = "PROMPT_SECRET_SHOULD_NOT_BE_STORED"
        events = [
            {
                "timestamp": "2026-09-07T00:00:00Z",
                "ordinal": 1,
                "type": "response_item",
                "payload": {"text": secret, "tool_arguments": "TOOL_SECRET"},
            },
            {
                "timestamp": "2026-09-07T00:00:01Z",
                "ordinal": 2,
                "type": "token_usage_record",
                "payload": {
                    "session_id": "session_fixture",
                    "thread_id": "thread_fixture",
                    "usage": {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7},
                    "thread_token_usage": {"input_tokens": 50, "cached_input_tokens": 10, "output_tokens": 20, "total_tokens": 70},
                },
            },
        ]
        source.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
        observation = parse_session_usage(source)
        self.assertEqual(observation.observed_event_count, 1)
        self.assertEqual(observation.usage["total_tokens"], 70)
        self.assertEqual(observation.session_id, "session_fixture")
        run_id = create_run(self.store, task_label="parser-fixture")["run_id"]
        ingest_usage(self.store, run_id, observation)
        ledger = self.store.ledger_path.read_text(encoding="utf-8")
        self.assertNotIn(secret, ledger)
        self.assertNotIn("TOOL_SECRET", ledger)
        self.assertNotIn(str(source), ledger)

    def test_missing_usage_remains_unknown_not_zero(self) -> None:
        start = create_run(self.store, task_label="unknown-usage")
        run_id = start["run_id"]
        self.assertEqual(start["orchestra"]["attribution_quality"], "UNKNOWN")
        self.assertIsNone(start["orchestra"]["root"]["model"])
        finalize_run(self.store, run_id, result={"completed": True})
        summary = report(self.store)["groups"][0]
        self.assertIsNone(summary["median_total_tokens"])
        self.assertIsNone(summary["median_input_tokens"])

    def test_duplicate_run_and_source_are_rejected(self) -> None:
        run_id = "run_fixed"
        create_run(self.store, task_label="duplicate-check", run_id=run_id)
        with self.assertRaises(DuplicateRecordError):
            create_run(self.store, task_label="duplicate-check", run_id=run_id)
        fixture = Path(self.temp.name) / "usage.jsonl"
        fixture.write_text(
            json.dumps({
                "type": "token_usage_record",
                "payload": {"session_id": "s", "thread_id": "t", "thread_token_usage": {"total_tokens": 1}},
            })
            + "\n",
            encoding="utf-8",
        )
        observation = parse_session_usage(fixture)
        ingest_usage(self.store, run_id, observation)
        with self.assertRaises(DuplicateRecordError):
            ingest_usage(self.store, run_id, observation)

    def test_corruption_is_detected_and_blocks_new_writes(self) -> None:
        run_id = create_run(self.store, task_label="corruption-check")["run_id"]
        self.store.ledger_path.write_bytes(self.store.ledger_path.read_bytes() + b"not-json\n")
        with self.assertRaises(LedgerCorruptionError):
            self.store.read()
        with self.assertRaises(LedgerCorruptionError):
            finalize_run(self.store, run_id)

    def test_allowance_delta_and_manual_observations_stay_separate(self) -> None:
        run_id = create_run(self.store, task_label="economics-check", task_class="OPERATIONS")["run_id"]
        add_snapshot(self.store, run_id, source="manual", snapshot_kind="BEFORE", weekly_allowance_pp=95.0, five_hour_allowance_pp=90.0)
        add_snapshot(self.store, run_id, source="manual", snapshot_kind="AFTER", weekly_allowance_pp=93.0, five_hour_allowance_pp=80.0)
        add_annotation(self.store, run_id, reviewer_verdict="PASS", first_pass="PASS")
        summary = report(self.store)
        self.assertEqual(summary["groups"][0]["median_weekly_allowance_pp_consumed"], 2.0)
        self.assertEqual(summary["groups"][0]["median_five_hour_allowance_pp_consumed"], 10.0)
        # Manual imports are intentionally not silently converted into runs.
        from scripts.orchestra_telemetry import import_manual

        import_manual(self.store, label="old-benchmark", source_note="manual-note", values={"total_tokens": 10})
        summary = report(self.store)
        self.assertEqual(summary["run_count"], 1)
        self.assertEqual(summary["legacy_manual_observation_count"], 1)

    def test_concurrent_appends_remain_valid(self) -> None:
        def write(index: int) -> dict[str, object]:
            return create_run(self.store, task_label=f"parallel-{index}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(write, range(8)))
        records = self.store.read()
        self.assertEqual(len(records), 8)
        self.assertEqual(len({record["run_id"] for record in records}), 8)

    def test_collector_source_has_no_model_or_worker_runtime_calls(self) -> None:
        source = Path(__file__).parents[1].joinpath("scripts", "orchestra_telemetry.py").read_text(encoding="utf-8")
        self.assertNotIn("subprocess", source)
        self.assertNotIn("urllib", source)
        self.assertNotIn("http.client", source)
        self.assertNotIn("create_thread", source)
        self.assertNotIn("send_message", source)

    def test_telemetry_off_has_no_global_policy_side_effect(self) -> None:
        from scripts import global_policy

        isolated_home = Path(self.temp.name) / "telemetry-off-home"
        isolated_home.mkdir()
        global_policy.install(isolated_home, source_root=Path(__file__).parents[1])
        self.assertFalse((isolated_home / "orchestra-telemetry").exists())
        self.assertEqual(global_policy.verify(isolated_home, source_root=Path(__file__).parents[1])["model"], "gpt-5.6-luna")
        self.assertEqual(global_policy.verify(isolated_home, source_root=Path(__file__).parents[1])["default_subagent_model"], "gpt-5.6-luna")

    def test_explicit_file_boundary_rejects_directories(self) -> None:
        with self.assertRaises(TelemetryError):
            parse_session_usage(Path(self.temp.name))
        with self.assertRaises(TelemetryError):
            create_run(self.store, task_label="C:/private/prompt.txt")

    def _write_hook_rollout(
        self,
        name: str,
        *,
        session_id: str,
        thread_id: str,
        model: str,
        effort: str,
        total_tokens: int,
        secret: str = "HOOK_PROMPT_SECRET",
    ) -> Path:
        path = Path(self.temp.name) / name
        events = [
            {
                "type": "response_item",
                "payload": {"text": secret, "tool_arguments": secret},
            },
            {
                "type": "turn_context",
                "payload": {
                    "effort": effort,
                    "model": model,
                    "collaboration_mode": {"settings": {"developer_instructions": secret}},
                },
            },
            {
                "type": "token_usage_record",
                "payload": {
                    "session_id": session_id,
                    "thread_id": thread_id,
                    "thread_token_usage": {
                        "input_tokens": total_tokens - 2,
                        "cached_input_tokens": 1,
                        "cache_write_input_tokens": 0,
                        "output_tokens": 2,
                        "reasoning_output_tokens": 1,
                        "total_tokens": total_tokens,
                    },
                },
            },
        ]
        path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
        return path

    def test_lifecycle_hooks_auto_create_ingest_finalize_and_aggregate_workers(self) -> None:
        session_id = "session_auto_root"
        root_path = self._write_hook_rollout(
            "root-rollout.jsonl",
            session_id=session_id,
            thread_id=session_id,
            model="future/gpt-9",
            effort="medium",
            total_tokens=10,
        )
        worker_path = self._write_hook_rollout(
            "worker-rollout.jsonl",
            session_id=session_id,
            thread_id="worker-1",
            model="future/worker-2",
            effort="xhigh",
            total_tokens=7,
        )
        start = handle_hook_event(self.store, {
            "hook_event_name": "SessionStart",
            "session_id": session_id,
            "transcript_path": None,
            "cwd": "C:/Windows",
            "model": "future/gpt-9",
        })
        handle_hook_event(self.store, {
            "hook_event_name": "SubagentStart",
            "session_id": session_id,
            "agent_id": "worker-1",
            "agent_type": "explorer",
            "model": "future/worker-2",
        })
        handle_hook_event(self.store, {
            "hook_event_name": "SubagentStop",
            "session_id": session_id,
            "agent_id": "worker-1",
            "agent_type": "explorer",
            "agent_transcript_path": str(worker_path),
            "model": "future/worker-2",
        })
        final = handle_hook_event(self.store, {
            "hook_event_name": "SessionEnd",
            "session_id": session_id,
            "transcript_path": str(root_path),
            "cwd": self.temp.name,
            "model": "future/gpt-9",
            "reason": "other",
        })
        self.assertEqual(start["run_id"], final["run_id"])
        self.assertEqual(final["status"], "FINALIZED")
        folded = __import__("scripts.orchestra_telemetry", fromlist=["_fold_run"])._fold_run(self.store.run_records(start["run_id"]))
        self.assertEqual(folded["task"]["project_kind"], "NO_PROJECT")
        self.assertEqual(folded["orchestra"]["root"]["model"], "future/gpt-9")
        self.assertEqual(folded["orchestra"]["root"]["reasoning_effort"], "medium")
        self.assertEqual(folded["usage"]["total_tokens"], 17)
        self.assertEqual(folded["orchestra"]["actual_worker_count"], 1)
        self.assertEqual(folded["orchestra"]["attribution_quality"], "ROOT_WORKER_USAGE_PARTIAL")
        ledger = self.store.ledger_path.read_text(encoding="utf-8")
        self.assertNotIn("HOOK_PROMPT_SECRET", ledger)
        self.assertNotIn(str(root_path), ledger)
        self.assertEqual(report(self.store)["run_count"], 1)
        ledger_before_duplicate_end = self.store.ledger_path.read_bytes()
        duplicate = handle_hook_event(self.store, {
            "hook_event_name": "SessionEnd",
            "session_id": session_id,
            "transcript_path": str(root_path),
            "cwd": self.temp.name,
            "model": "future/gpt-9",
            "reason": "other",
        })
        self.assertEqual(duplicate["run_id"], start["run_id"])
        self.assertEqual(duplicate["status"], "FINALIZED")
        self.assertEqual(self.store.ledger_path.read_bytes(), ledger_before_duplicate_end)

    def test_hook_correlation_mismatch_fails_closed_and_disable_is_noop(self) -> None:
        session_id = "session_exact"
        handle_hook_event(self.store, {
            "hook_event_name": "SessionStart",
            "session_id": session_id,
            "cwd": self.temp.name,
            "model": "gpt-5.6-luna",
        })
        bad_path = self._write_hook_rollout(
            "wrong-session.jsonl",
            session_id="another-session",
            thread_id="another-session",
            model="gpt-5.6-luna",
            effort="xhigh",
            total_tokens=3,
        )
        with self.assertRaises(SessionParseError):
            handle_hook_event(self.store, {
                "hook_event_name": "SessionEnd",
                "session_id": session_id,
                "transcript_path": str(bad_path),
                "cwd": self.temp.name,
                "model": "gpt-5.6-luna",
            })
        missing_path = Path(self.temp.name) / "missing-session.jsonl"
        missing_path.write_text(
            json.dumps({
                "type": "token_usage_record",
                "payload": {"thread_token_usage": {"total_tokens": 3}},
            })
            + "\n",
            encoding="utf-8",
        )
        with self.assertRaises(SessionParseError):
            handle_hook_event(self.store, {
                "hook_event_name": "SessionEnd",
                "session_id": session_id,
                "transcript_path": str(missing_path),
                "cwd": self.temp.name,
                "model": "gpt-5.6-luna",
            })
        before = self.store.ledger_path.read_bytes()
        with patch.dict(os.environ, {"CODEX_ORCHESTRA_TELEMETRY": "0"}):
            self.assertEqual(handle_hook_event(self.store, {
                "hook_event_name": "SessionStart",
                "session_id": "disabled-session",
                "cwd": self.temp.name,
                "model": "gpt-5.6-luna",
            })["status"], "DISABLED")
        self.assertEqual(self.store.ledger_path.read_bytes(), before)

    def test_interrupt_is_retained_as_abnormal_without_fabricated_usage(self) -> None:
        session_id = "session_interrupt"
        start = handle_hook_event(self.store, {
            "hook_event_name": "SessionStart",
            "session_id": session_id,
            "cwd": self.temp.name,
            "model": "gpt-5.6-luna",
        })
        handle_hook_event(self.store, {
            "hook_event_name": "Interrupt",
            "session_id": session_id,
            "turn_id": "turn-interrupted",
        })
        handle_hook_event(self.store, {
            "hook_event_name": "SessionEnd",
            "session_id": session_id,
            "transcript_path": None,
            "cwd": self.temp.name,
            "model": "gpt-5.6-luna",
        })
        folded = __import__("scripts.orchestra_telemetry", fromlist=["_fold_run"])._fold_run(self.store.run_records(start["run_id"]))
        self.assertFalse(folded["result"]["completed"])
        self.assertEqual(folded["execution"]["abnormal_termination"], "INTERRUPTED")
        self.assertIsNone(folded["usage"]["total_tokens"])


if __name__ == "__main__":
    unittest.main()
