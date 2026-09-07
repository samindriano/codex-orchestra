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
    _project_metadata,
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

    def _turn_lifecycle(self, session_id: str, turn_id: str = "turn-1", **fields: object) -> str:
        handle_hook_event(self.store, self._hook("SessionStart", session_id, **fields))
        start = handle_hook_event(self.store, self._hook("UserPromptSubmit", session_id, turn_id=turn_id, **fields))
        handle_hook_event(self.store, self._hook("Stop", session_id, turn_id=turn_id, **fields))
        return str(start["run_id"])

    def _exec_json(self, name: str, thread_id: str, *, turn_id: str | None = None, usage: dict[str, object] | None = None, malformed: bool = False) -> Path:
        path = self.root / name
        turn_id = turn_id or f"{thread_id}-turn"
        lines = [
            {"type": "thread.started", "thread_id": thread_id},
            {"type": "turn.started", "turn_id": turn_id},
            {"type": "turn.completed", "turn_id": turn_id, "usage": usage or {
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
            run_id = self._turn_lifecycle("session-blind", transcript_path=str(transcript))
            final = handle_hook_event(self.store, self._hook("SessionEnd", "session-blind", transcript_path=str(transcript)))
        self.assertEqual(final["status"], "SESSION_ENDED")
        folded = self._fold(run_id)
        self.assertIsNone(folded["usage"]["total_tokens"])
        self.assertEqual(folded["usage_source"], "NONE")
        self.assertEqual(folded["usage_quality"], "UNKNOWN")
        self.assertNotIn(str(transcript), self.store.ledger_path.read_text(encoding="utf-8"))

    def test_malicious_or_huge_transcript_cannot_affect_telemetry(self) -> None:
        transcript = self.root / "huge-secret.jsonl"
        transcript.write_text("PROMPT_SECRET TOOL_SECRET " * 20000, encoding="utf-8")
        run_id = self._turn_lifecycle("session-huge", transcript_path=str(transcript), model="future-model-example-v99")
        folded = self._fold(run_id)
        self.assertEqual(folded["orchestra"]["root"]["model"], "future-model-example-v99")
        self.assertIsNone(folded["usage"]["total_tokens"])
        ledger = self.store.ledger_path.read_text(encoding="utf-8")
        self.assertNotIn("PROMPT_SECRET", ledger)
        self.assertNotIn(str(transcript), ledger)

    def test_stable_hook_model_accepts_luna_astra_and_future_values(self) -> None:
        for session_id, model in (("luna", "gpt-5.6-luna"), ("astra", "gpt-6-astra"), ("future", "future-model-example-v99")):
            run_id = self._turn_lifecycle(session_id, model=model)
            self.assertEqual(self._fold(run_id)["orchestra"]["root"]["model"], model)

    def test_missing_effort_and_profile_are_unknown_without_reverse_inference(self) -> None:
        run_id = self._turn_lifecycle("session-effort", model="gpt-6-astra")
        folded = self._fold(run_id)
        self.assertIsNone(folded["orchestra"]["root"]["reasoning_effort"])
        self.assertEqual(folded["reasoning_effort_source"], "NONE")
        self.assertIsNone(folded["orchestra"]["root"]["profile"])
        self.assertEqual(folded["orchestra"]["mode"], "NOT_APPLICABLE")

    def test_launcher_metadata_is_explicit_and_can_supply_exact_usage(self) -> None:
        launcher = {"profile": "global-luna", "mode": "LIGHT", "reasoning_effort": "xhigh", "usage": {"model_requests": 1, "input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 4, "reasoning_tokens": 1, "total_tokens": 14}}
        run_id = self._turn_lifecycle("session-launcher", orchestra_launcher=launcher)
        folded = self._fold(run_id)
        self.assertEqual(folded["orchestra"]["mode"], "LIGHT")
        self.assertEqual(folded["orchestra"]["root"]["profile"], "global-luna")
        self.assertEqual(folded["orchestra"]["root"]["reasoning_effort"], "xhigh")
        self.assertEqual(folded["reasoning_effort_source"], "LAUNCHER")
        self.assertEqual(folded["usage_source"], "ORCHESTRA_LAUNCHER")
        self.assertEqual(folded["usage_quality"], "EXACT")
        self.assertEqual(folded["usage"]["total_tokens"], 14)

    def test_codex_exec_json_adapter_is_exact_and_correlated(self) -> None:
        path = self._exec_json("exec-output.jsonl", "thread-exact", turn_id="turn-exact")
        observation = parse_codex_exec_json(path, expected_thread_id="thread-exact", expected_turn_id="turn-exact")
        self.assertEqual(observation.usage_source, "CODEX_EXEC_JSON")
        self.assertEqual(observation.usage_quality, "EXACT")
        self.assertEqual(observation.usage["total_tokens"], 70)
        self.assertEqual(observation.turn_id, "turn-exact")
        run_id = create_run(self.store, task_label="exec-adapter")["run_id"]
        ingest_codex_exec_json(self.store, run_id, path, expected_thread_id="thread-exact", expected_turn_id="turn-exact", turn_id="turn-exact", measurement_generation="TURN_LEVEL_V1_2")
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

    def test_turn_chronology_is_distinct_from_later_inspection_turn(self) -> None:
        handle_hook_event(self.store, self._hook("SessionStart", "long-session"))
        first = handle_hook_event(self.store, self._hook("UserPromptSubmit", "long-session", turn_id="substantive-A", prompt="PROMPT_A"))
        handle_hook_event(self.store, self._hook("Stop", "long-session", turn_id="substantive-A", last_assistant_message="ANSWER_A"))
        second = handle_hook_event(self.store, self._hook("UserPromptSubmit", "long-session", turn_id="inspection-B", prompt="PROMPT_B"))
        handle_hook_event(self.store, self._hook("Stop", "long-session", turn_id="inspection-B", last_assistant_message="ANSWER_B"))
        handle_hook_event(self.store, self._hook("SessionEnd", "long-session"))
        self.assertNotEqual(first["run_id"], second["run_id"])
        self.assertEqual(self._fold(first["run_id"])["turn_id"], "substantive-A")
        self.assertEqual(self._fold(second["run_id"])["turn_id"], "inspection-B")
        self.assertEqual(report(self.store)["run_count"], 2)
        ledger = self.store.ledger_path.read_text(encoding="utf-8")
        for secret in ("PROMPT_A", "PROMPT_B", "ANSWER_A", "ANSWER_B"):
            self.assertNotIn(secret, ledger)

    def test_interrupt_resume_and_compaction_keep_turn_identity(self) -> None:
        handle_hook_event(self.store, self._hook("SessionStart", "resume-session"))
        interrupted = handle_hook_event(self.store, self._hook("UserPromptSubmit", "resume-session", turn_id="turn-interrupted"))
        self.assertEqual(handle_hook_event(self.store, self._hook("PreCompact", "resume-session", turn_id="turn-interrupted"))["status"], "IGNORED")
        handle_hook_event(self.store, self._hook("Interrupt", "resume-session", turn_id="turn-interrupted"))
        handle_hook_event(self.store, self._hook("Stop", "resume-session", turn_id="turn-interrupted"))
        resumed = handle_hook_event(self.store, self._hook("UserPromptSubmit", "resume-session", turn_id="turn-resumed"))
        handle_hook_event(self.store, self._hook("Stop", "resume-session", turn_id="turn-resumed"))
        first = self._fold(str(interrupted["run_id"]))
        second = self._fold(str(resumed["run_id"]))
        self.assertEqual(first["turn_status"], "INTERRUPTED")
        self.assertFalse(first["result"]["completed"])
        self.assertEqual(second["turn_status"], "COMPLETED")
        self.assertTrue(second["result"]["completed"])
        self.assertEqual(len([r for r in self.store.read() if r["record_type"] == "turn_finalize"]), 2)

    def test_turn_workers_link_to_parent_turn_without_fabricated_worker_usage(self) -> None:
        handle_hook_event(self.store, self._hook("SessionStart", "worker-session"))
        start = handle_hook_event(self.store, self._hook("UserPromptSubmit", "worker-session", turn_id="turn-workers"))
        handle_hook_event(self.store, self._hook("SubagentStart", "worker-session", turn_id="turn-workers", agent_id="agent-1", agent_type="explorer", model="worker-model"))
        handle_hook_event(self.store, self._hook("SubagentStop", "worker-session", turn_id="turn-workers", agent_id="agent-1", agent_type="explorer", model="worker-model", last_assistant_message="WORKER_SECRET"))
        handle_hook_event(self.store, self._hook("Stop", "worker-session", turn_id="turn-workers"))
        folded = self._fold(str(start["run_id"]))
        self.assertEqual(folded["orchestra"]["workers"][0]["worker_id"], "agent-1")
        self.assertEqual(folded["orchestra"]["workers"][0]["model"], "worker-model")
        self.assertIsNone(folded["usage"]["total_tokens"])
        self.assertNotIn("WORKER_SECRET", self.store.ledger_path.read_text(encoding="utf-8"))

    def test_project_metadata_distinguishes_worktree_repo_branch_and_non_git(self) -> None:
        repo = self.root / "ordinary-repo"
        (repo / ".git").mkdir(parents=True)
        (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        worktree = self.root / "idx-foreign-flow-prospective-pit-shadow-v1"
        worktree.mkdir()
        git_dir = repo / ".git" / "worktrees" / worktree.name
        git_dir.mkdir(parents=True)
        (git_dir / "HEAD").write_text("ref: refs/heads/feature/pit-shadow\n", encoding="utf-8")
        (git_dir / "commondir").write_text(str(repo / ".git") + "\n", encoding="utf-8")
        (worktree / ".git").write_text(f"gitdir: {git_dir}\n", encoding="utf-8")
        git_meta = _project_metadata(str(worktree))
        self.assertEqual((git_meta.kind, git_meta.label, git_meta.repo_label, git_meta.branch), ("GIT", worktree.name, "ordinary-repo", "feature-pit-shadow"))
        ordinary_meta = _project_metadata(str(repo))
        self.assertEqual((ordinary_meta.kind, ordinary_meta.label, ordinary_meta.branch), ("GIT", "ordinary-repo", "main"))
        no_project = _project_metadata(None)
        self.assertEqual((no_project.kind, no_project.label), ("NO_PROJECT", None))

    def test_concurrent_sessions_and_turns_do_not_cross_attribute(self) -> None:
        def run(index: int) -> tuple[str, str]:
            session_id = f"concurrent-session-{index}"
            turn_id = f"concurrent-turn-{index}"
            run_id = self._turn_lifecycle(session_id, turn_id)
            return session_id, run_id

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(run, range(8)))
        self.assertEqual(len({run_id for _, run_id in results}), 8)
        for session_id, run_id in results:
            folded = self._fold(run_id)
            self.assertEqual(folded["session_id"], session_id)
            self.assertEqual(folded["turn_id"], session_id.replace("session", "turn"))

    def test_interactive_session_without_stable_usage_is_valid_unknown(self) -> None:
        run_id = self._turn_lifecycle("session-unknown")
        folded = self._fold(run_id)
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
        handle_hook_event(self.store, self._hook("SessionStart", "session-worker"))
        start = handle_hook_event(self.store, self._hook("UserPromptSubmit", "session-worker", turn_id="turn-worker"))
        handle_hook_event(self.store, self._hook("SubagentStart", "session-worker", turn_id="turn-worker", agent_id="worker-1", agent_type="explorer", model="future-worker-v2"))
        handle_hook_event(self.store, self._hook("SubagentStop", "session-worker", turn_id="turn-worker", agent_id="worker-1", agent_type="explorer", model="future-worker-v2", agent_transcript_path=str(self.root / "never-open.jsonl")))
        handle_hook_event(self.store, self._hook("Stop", "session-worker", turn_id="turn-worker"))
        folded = self._fold(start["run_id"])
        self.assertEqual(folded["orchestra"]["workers_started"], 1)
        self.assertEqual(folded["orchestra"]["workers_completed"], 1)
        self.assertEqual(folded["orchestra"]["workers"][0]["model"], "future-worker-v2")
        self.assertIsNone(folded["usage"]["total_tokens"])
        self.assertEqual(folded["orchestra"]["attribution_quality"], "ROOT_WORKER_USAGE_PARTIAL")

    def test_project_and_no_project_metadata_never_persist_full_cwd(self) -> None:
        run_id = self._turn_lifecycle("session-no-project", cwd=None)
        self.assertEqual(self._fold(run_id)["task"]["project_kind"], "NO_PROJECT")
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

    def test_legacy_session_level_runs_are_excluded_from_default_turn_report(self) -> None:
        legacy = create_run(self.store, task_label="codex-session", run_id="legacy-session")
        finalize_run(self.store, legacy["run_id"])
        self.assertEqual(report(self.store)["run_count"], 0)
        compatibility = report(self.store, include_session_level=True)
        self.assertEqual(compatibility["run_count"], 1)
        self.assertEqual(compatibility["groups"][0]["runs"], 1)

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
