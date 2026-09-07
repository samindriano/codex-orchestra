from __future__ import annotations

import concurrent.futures
import io
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
    TelemetryStore,
    add_annotation,
    add_snapshot,
    create_run,
    finalize_run,
    handle_hook_event,
    ingest_codex_exec_json,
    ingest_launcher_usage,
    ingest_synthetic_usage,
    main,
    parse_codex_exec_json,
    parse_session_usage,
    report,
)


class OrchestraTelemetryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = TelemetryStore(self.root / "orchestra-telemetry")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _hook(self, event_name: str, session_id: str, **fields: object) -> dict[str, object]:
        event: dict[str, object] = {
            "hook_event_name": event_name,
            "session_id": session_id,
            "cwd": str(self.root),
            "model": "gpt-5.6-luna",
        }
        event.update(fields)
        return event

    def _exec_json(self, name: str, thread_id: str, *, usage: dict[str, object] | None = None, malformed: bool = False) -> Path:
        path = self.root / name
        lines = [
            {"type": "thread.started", "thread_id": thread_id},
            {"type": "turn.started"},
            {"type": "turn.completed", "usage": usage or {
                "input_tokens": 50,
                "cached_input_tokens": 10,
                "output_tokens": 20,
                "reasoning_output_tokens": 3,
                "total_tokens": 70,
            }},
        ]
        text = "\n".join(json.dumps(line) for line in lines) + "\n"
        if malformed:
            text += "{not-json\n"
        path.write_text(text, encoding="utf-8")
        return path

    def _fold(self, run_id: str) -> dict[str, object]:
        return __import__("scripts.orchestra_telemetry", fromlist=["_fold_run"])._fold_run(self.store.run_records(run_id))

    def test_synthetic_lifecycle_is_zero_model_overhead_and_offline(self) -> None:
        run_id = create_run(self.store, task_label="synthetic-review", task_class="REVIEW", complexity="SMALL", mode="DIRECT", root_model="gpt-5.6-luna", root_reasoning_effort="xhigh")["run_id"]
        ingest_synthetic_usage(self.store, run_id, {"model_requests": 2, "input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 30, "reasoning_tokens": 10, "total_tokens": 130})
        finalize_run(self.store, run_id, usage={"total_tokens": 130}, execution={"wall_clock_seconds": 1.5}, result={"completed": True})
        add_annotation(self.store, run_id, reviewer_verdict="PASS", first_pass="PASS")
        result = report(self.store)
        self.assertEqual(result["run_count"], 0)
        self.assertEqual(result["synthetic_run_count"], 1)
        fixture_report = report(self.store, include_synthetic=True)
        self.assertEqual(fixture_report["groups"][0]["median_total_tokens"], 130.0)
        self.assertEqual(fixture_report["groups"][0]["median_total_tokens_n"], 1)
        for record in self.store.read():
            measurement = record.get("measurement")
            if measurement:
                self.assertEqual(measurement["telemetry_model_requests_added"], 0)
                self.assertEqual(measurement["telemetry_tokens_added"], 0)
                self.assertEqual(measurement["telemetry_worker_launches_added"], 0)
                self.assertEqual(measurement["telemetry_context_tokens_added"], 0)

    def test_transcript_path_is_never_opened_by_automatic_hooks(self) -> None:
        transcript = self.root / "tempting-transcript.jsonl"
        transcript.write_text(json.dumps({"type": "turn.completed", "usage": {"total_tokens": 999999}}) + "\n", encoding="utf-8")
        original_open = Path.open

        def guarded_open(path: Path, *args: object, **kwargs: object):
            if path.resolve() == transcript.resolve():
                raise AssertionError("automatic telemetry opened transcript_path")
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", new=guarded_open):
            start = handle_hook_event(self.store, self._hook("SessionStart", "session-blind", transcript_path=str(transcript)))
            final = handle_hook_event(self.store, self._hook("SessionEnd", "session-blind", transcript_path=str(transcript)))
        self.assertEqual(start["run_id"], final["run_id"])
        folded = self._fold(start["run_id"])
        self.assertIsNone(folded["usage"]["total_tokens"])
        self.assertEqual(folded["usage_source"], "NONE")
        self.assertEqual(folded["usage_quality"], "UNKNOWN")
        self.assertNotIn(str(transcript), self.store.ledger_path.read_text(encoding="utf-8"))

    def test_malicious_or_huge_transcript_cannot_affect_telemetry(self) -> None:
        transcript = self.root / "huge-secret.jsonl"
        transcript.write_text("PROMPT_SECRET TOOL_SECRET " * 20000, encoding="utf-8")
        result = handle_hook_event(self.store, self._hook("SessionStart", "session-huge", transcript_path=str(transcript), model="future-model-example-v99"))
        handle_hook_event(self.store, self._hook("SessionEnd", "session-huge", transcript_path=str(transcript), model="future-model-example-v99"))
        folded = self._fold(result["run_id"])
        self.assertEqual(folded["orchestra"]["root"]["model"], "future-model-example-v99")
        self.assertIsNone(folded["usage"]["total_tokens"])
        ledger = self.store.ledger_path.read_text(encoding="utf-8")
        self.assertNotIn("PROMPT_SECRET", ledger)
        self.assertNotIn(str(transcript), ledger)

    def test_stable_hook_model_accepts_luna_astra_and_future_values(self) -> None:
        for session_id, model in (("luna", "gpt-5.6-luna"), ("astra", "gpt-6-astra"), ("future", "future-model-example-v99")):
            start = handle_hook_event(self.store, self._hook("SessionStart", session_id, model=model))
            handle_hook_event(self.store, self._hook("SessionEnd", session_id, model=model))
            self.assertEqual(self._fold(start["run_id"])["orchestra"]["root"]["model"], model)

    def test_missing_effort_and_profile_are_unknown_without_reverse_inference(self) -> None:
        start = handle_hook_event(self.store, self._hook("SessionStart", "session-effort", model="gpt-6-astra"))
        handle_hook_event(self.store, self._hook("SessionEnd", "session-effort", model="gpt-6-astra"))
        folded = self._fold(start["run_id"])
        self.assertIsNone(folded["orchestra"]["root"]["reasoning_effort"])
        self.assertEqual(folded["reasoning_effort_source"], "NONE")
        self.assertIsNone(folded["orchestra"]["root"]["profile"])
        self.assertEqual(folded["orchestra"]["mode"], "NOT_APPLICABLE")

    def test_launcher_metadata_is_explicit_and_can_supply_exact_usage(self) -> None:
        launcher = {"profile": "global-luna", "mode": "LIGHT", "reasoning_effort": "xhigh", "usage": {"model_requests": 1, "input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 4, "reasoning_tokens": 1, "total_tokens": 14}}
        start = handle_hook_event(self.store, self._hook("SessionStart", "session-launcher", orchestra_launcher=launcher))
        handle_hook_event(self.store, self._hook("SessionEnd", "session-launcher", orchestra_launcher=launcher))
        folded = self._fold(start["run_id"])
        self.assertEqual(folded["orchestra"]["mode"], "LIGHT")
        self.assertEqual(folded["orchestra"]["root"]["profile"], "global-luna")
        self.assertEqual(folded["orchestra"]["root"]["reasoning_effort"], "xhigh")
        self.assertEqual(folded["reasoning_effort_source"], "LAUNCHER")
        self.assertEqual(folded["usage_source"], "ORCHESTRA_LAUNCHER")
        self.assertEqual(folded["usage_quality"], "EXACT")
        self.assertEqual(folded["usage"]["total_tokens"], 14)

    def test_codex_exec_json_adapter_is_exact_and_correlated(self) -> None:
        path = self._exec_json("exec-output.jsonl", "thread-exact")
        observation = parse_codex_exec_json(path, expected_thread_id="thread-exact")
        self.assertEqual(observation.usage_source, "CODEX_EXEC_JSON")
        self.assertEqual(observation.usage_quality, "EXACT")
        self.assertEqual(observation.usage["total_tokens"], 70)
        run_id = create_run(self.store, task_label="exec-adapter")["run_id"]
        ingest_codex_exec_json(self.store, run_id, path, expected_thread_id="thread-exact")
        folded = self._fold(run_id)
        self.assertEqual(folded["usage_source"], "CODEX_EXEC_JSON")
        self.assertEqual(folded["usage_quality"], "EXACT")
        self.assertEqual(folded["usage"]["total_tokens"], 70)

    def test_unsupported_or_malformed_exec_source_becomes_unknown(self) -> None:
        malformed = self._exec_json("malformed.jsonl", "thread-malformed", malformed=True)
        observation = parse_codex_exec_json(malformed, expected_thread_id="thread-malformed")
        self.assertEqual(observation.usage_source, "NONE")
        self.assertEqual(observation.usage_quality, "UNKNOWN")
        self.assertIsNone(observation.usage["total_tokens"])
        wrong = parse_codex_exec_json(malformed, expected_thread_id="wrong-thread")
        self.assertEqual(wrong.usage_quality, "UNKNOWN")

    def test_interactive_session_without_stable_usage_is_valid_unknown(self) -> None:
        start = handle_hook_event(self.store, self._hook("SessionStart", "session-unknown"))
        final = handle_hook_event(self.store, self._hook("SessionEnd", "session-unknown"))
        self.assertEqual(final["status"], "FINALIZED")
        folded = self._fold(start["run_id"])
        for field in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens", "total_tokens"):
            self.assertIsNone(folded["usage"][field])
        self.assertEqual(folded["usage_quality"], "UNKNOWN")
        self.assertIsNotNone(folded["execution"]["wall_clock_seconds"])

    def test_two_concurrent_exec_sessions_cannot_cross_attribute_usage(self) -> None:
        fixtures = [("run-a", "thread-a", 11), ("run-b", "thread-b", 22)]

        def ingest(item: tuple[str, str, int]) -> int | None:
            run_id, thread_id, total = item
            path = self._exec_json(f"{thread_id}.jsonl", thread_id, usage={"input_tokens": total, "output_tokens": 0, "total_tokens": total})
            create_run(self.store, task_label=run_id, run_id=run_id)
            ingest_codex_exec_json(self.store, run_id, path, expected_thread_id=thread_id)
            return self._fold(run_id)["usage"]["total_tokens"]

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            totals = list(executor.map(ingest, fixtures))
        self.assertEqual(sorted(totals), [11, 22])

    def test_root_worker_lifecycle_does_not_imply_worker_token_usage(self) -> None:
        start = handle_hook_event(self.store, self._hook("SessionStart", "session-worker"))
        handle_hook_event(self.store, self._hook("SubagentStart", "session-worker", agent_id="worker-1", agent_type="explorer", model="future-worker-v2"))
        handle_hook_event(self.store, self._hook("SubagentStop", "session-worker", agent_id="worker-1", agent_type="explorer", model="future-worker-v2", agent_transcript_path=str(self.root / "never-open.jsonl")))
        handle_hook_event(self.store, self._hook("SessionEnd", "session-worker"))
        folded = self._fold(start["run_id"])
        self.assertEqual(folded["orchestra"]["workers_started"], 1)
        self.assertEqual(folded["orchestra"]["workers_completed"], 1)
        self.assertEqual(folded["orchestra"]["workers"][0]["model"], "future-worker-v2")
        self.assertIsNone(folded["usage"]["total_tokens"])
        self.assertEqual(folded["orchestra"]["attribution_quality"], "ROOT_WORKER_USAGE_PARTIAL")

    def test_project_and_no_project_metadata_never_persist_full_cwd(self) -> None:
        start = handle_hook_event(self.store, self._hook("SessionStart", "session-no-project", cwd=None))
        handle_hook_event(self.store, self._hook("SessionEnd", "session-no-project", cwd=None))
        self.assertEqual(self._fold(start["run_id"])["task"]["project_kind"], "NO_PROJECT")
        self.assertNotIn(str(self.root), self.store.ledger_path.read_text(encoding="utf-8"))

    def test_duplicate_run_and_source_are_rejected(self) -> None:
        run_id = create_run(self.store, task_label="duplicate-check", run_id="run-fixed")["run_id"]
        with self.assertRaises(DuplicateRecordError):
            create_run(self.store, task_label="duplicate-check", run_id=run_id)
        path = self._exec_json("duplicate.jsonl", "thread-duplicate")
        ingest_codex_exec_json(self.store, run_id, path, expected_thread_id="thread-duplicate")
        with self.assertRaises(DuplicateRecordError):
            ingest_codex_exec_json(self.store, run_id, path, expected_thread_id="thread-duplicate")

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
        from scripts.orchestra_telemetry import import_manual

        import_manual(self.store, label="old-benchmark", source_note="manual-note", values={"total_tokens": 10})
        summary = report(self.store)
        self.assertEqual(summary["run_count"], 1)
        self.assertEqual(summary["legacy_manual_observation_count"], 1)
        self.assertEqual(summary["groups"][0]["median_weekly_allowance_pp_consumed"], 2.0)

    def test_reporting_excludes_unknown_usage_from_medians_and_reports_n(self) -> None:
        first = create_run(self.store, task_label="same-group", run_id="known")["run_id"]
        ingest_launcher_usage(self.store, first, {"input_tokens": 10, "output_tokens": 2, "reasoning_tokens": 1, "total_tokens": 12})
        finalize_run(self.store, first, usage_source="ORCHESTRA_LAUNCHER", usage_quality="EXACT")
        second = create_run(self.store, task_label="same-group", run_id="unknown")["run_id"]
        finalize_run(self.store, second)
        summary = report(self.store, group_by=["task_class", "mode", "root_model", "reasoning_effort", "worker_count"])
        self.assertEqual(summary["groups"][0]["usage_total_runs"], 2)
        self.assertEqual(summary["groups"][0]["usage_qualified_runs"], 1)
        self.assertEqual(summary["groups"][0]["median_total_tokens"], 12.0)
        self.assertEqual(summary["groups"][0]["median_total_tokens_n"], 1)

    def test_concurrent_appends_remain_valid(self) -> None:
        def write(index: int) -> dict[str, object]:
            return create_run(self.store, task_label=f"parallel-{index}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(write, range(8)))
        records = self.store.read()
        self.assertEqual(len(records), 8)
        self.assertEqual(len({record["run_id"] for record in records}), 8)

    def test_fail_open_cases_return_zero_and_do_not_emit_stdout(self) -> None:
        payload = json.dumps(self._hook("SessionStart", "fail-open"))
        with patch("scripts.orchestra_telemetry.handle_hook_event", side_effect=RuntimeError("collector")), patch("sys.stdin", io.StringIO(payload)), patch("sys.stdout", new_callable=io.StringIO) as stdout:
            self.assertEqual(main(["--store", str(self.root / "unwritable"), "hook"]), 0)
            self.assertEqual(stdout.getvalue(), "")
        with patch("scripts.orchestra_telemetry.handle_hook_event", side_effect=OSError("lock")), patch("sys.stdin", io.StringIO(payload)):
            self.assertEqual(main(["--store", str(self.root / "locked"), "hook"]), 0)
        malformed_store = self.root / "malformed"
        malformed_store.mkdir()
        (malformed_store / "ledger.jsonl").write_text("not-json\n", encoding="utf-8")
        with patch("sys.stdin", io.StringIO(payload)):
            self.assertEqual(main(["--store", str(malformed_store), "hook"]), 0)
        with patch.dict(os.environ, {"CODEX_ORCHESTRA_TELEMETRY": "0"}):
            before = self.store.ledger_path.read_bytes() if self.store.ledger_path.exists() else b""
            self.assertEqual(handle_hook_event(self.store, self._hook("SessionStart", "disabled"))["status"], "DISABLED")
            after = self.store.ledger_path.read_bytes() if self.store.ledger_path.exists() else b""
            self.assertEqual(before, after)

    def test_collector_source_has_no_runtime_calls_or_transcript_parser(self) -> None:
        source = Path(__file__).parents[1].joinpath("scripts", "orchestra_telemetry.py").read_text(encoding="utf-8")
        self.assertNotIn("subprocess", source)
        self.assertNotIn("urllib", source)
        self.assertNotIn("http.client", source)
        self.assertNotIn("create_thread", source)
        self.assertNotIn("send_message", source)
        self.assertNotIn("token_usage_record", source)
        self.assertNotIn("turn_context", source)

    def test_transcript_parser_is_disabled_without_opening_the_path(self) -> None:
        transcript = self.root / "legacy.jsonl"
        transcript.write_text("{\"type\":\"token_usage_record\"}\n", encoding="utf-8")
        with self.assertRaises(SessionParseError):
            parse_session_usage(transcript)

    def test_telemetry_off_has_no_global_policy_side_effect(self) -> None:
        from scripts import global_policy

        isolated_home = self.root / "telemetry-off-home"
        isolated_home.mkdir()
        global_policy.install(isolated_home, source_root=Path(__file__).parents[1])
        self.assertFalse((isolated_home / "orchestra-telemetry").exists())
        self.assertEqual(global_policy.verify(isolated_home, source_root=Path(__file__).parents[1])["model"], "gpt-5.6-luna")


if __name__ == "__main__":
    unittest.main()
