import json
from pathlib import Path
import tempfile
import unittest

from scripts.orchestra_telemetry import (
    TelemetryStore,
    _fold_run,
    _otel_attach,
    _structured_child_ids,
    create_turn,
    handle_hook_event,
    ingest_otel_payload,
    observe_worker,
)


class OrchestraTelemetryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = TelemetryStore(Path(self.temp.name) / "telemetry")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def hook(self, name: str, session: str, *, turn: str | None = None, **fields: object) -> dict[str, object]:
        event: dict[str, object] = {"hook_event_name": name, "session_id": session}
        if turn is not None:
            event["turn_id"] = turn
        event.update(fields)
        return event

    def otel(self, thread: str, turn: str, total: int = 100) -> dict[str, object]:
        values = {
            "input_tokens": total - 20,
            "cached_input_tokens": 0,
            "cache_write_input_tokens": 0,
            "non_cached_input_tokens": total - 20,
            "output_tokens": 20,
            "reasoning_tokens": 0,
            "reasoning_output_tokens": 0,
            "total_tokens": total,
        }
        attrs = [
            {"key": "thread.id", "value": {"stringValue": thread}},
            {"key": "turn.id", "value": {"stringValue": turn}},
        ]
        attrs.extend({"key": f"codex.turn.token_usage.{key}", "value": {"intValue": value}} for key, value in values.items())
        return {"resourceSpans": [{"scopeSpans": [{"spans": [{"name": "session_task.turn", "attributes": attrs}]}]}]}

    def start_root(self, session: str = "root-session", turn: str = "root-turn") -> str:
        handle_hook_event(self.store, self.hook("SessionStart", session))
        result = handle_hook_event(self.store, self.hook("UserPromptSubmit", session, turn=turn))
        return str(result["run_id"])

    def add_worker(self, session: str, turn: str, worker: str, *, model: str = "worker-model", native_thread_id: str | None = None, native_turn_id: str | None = None) -> None:
        self.add_edge(session, "root-turn", worker)
        fields: dict[str, object] = {"agent_id": worker, "agent_type": "explorer", "model": model}
        if native_thread_id is not None:
            fields["native_thread_id"] = native_thread_id
        if native_turn_id is not None:
            fields["native_turn_id"] = native_turn_id
        handle_hook_event(self.store, self.hook("SubagentStart", session, turn=turn, **fields))

    def add_edge(self, session: str, turn: str, *workers: str, tool_response: object | None = None) -> None:
        if tool_response is None:
            tool_response = {"receiver_thread_ids": list(workers)}
        handle_hook_event(
            self.store,
            self.hook("PostToolUse", session, turn=turn, tool_name="spawn_agent", tool_response=tool_response),
        )

    def stop_worker(self, session: str, turn: str, worker: str, *, model: str = "worker-model") -> None:
        handle_hook_event(self.store, self.hook("SubagentStop", session, turn=turn, agent_id=worker, agent_type="explorer", model=model))

    def fold(self, run_id: str) -> dict[str, object]:
        return _fold_run(self.store.run_records(run_id))

    def test_root_only_proven_zero_workers(self) -> None:
        record = create_turn(self.store, session_id="zero-session", turn_id="zero-turn", actual_worker_count=0, worker_presence_quality="EXACT")
        ingest_otel_payload(self.store, self.otel("zero-session", "zero-turn", 100))
        folded = self.fold(str(record["run_id"]))
        orchestra = folded["orchestra"]
        self.assertEqual(folded["usage_quality"], "EXACT")
        self.assertEqual(orchestra["worker_total_tokens"], 0)
        self.assertEqual(orchestra["orchestra_total_tokens"], 100)

    def test_normal_hook_path_without_edges_cannot_prove_zero_workers(self) -> None:
        run_id = self.start_root()
        ingest_otel_payload(self.store, self.otel("root-session", "root-turn", 100))
        handle_hook_event(self.store, self.hook("Stop", "root-session", turn="root-turn"))
        orchestra = self.fold(run_id)["orchestra"]
        self.assertIsNone(orchestra["actual_worker_count"])
        self.assertEqual(orchestra["worker_presence_quality"], "UNKNOWN")
        self.assertIsNone(orchestra["worker_total_tokens"])
        self.assertIsNone(orchestra["orchestra_total_tokens"])

    def test_two_edges_only_one_lifecycle_is_unknown(self) -> None:
        run_id = self.start_root()
        self.add_edge("root-session", "root-turn", "worker-a", "worker-b")
        handle_hook_event(self.store, self.hook("SubagentStart", "root-session", turn="worker-turn-a", agent_id="worker-a", agent_type="explorer", model="worker-model"))
        handle_hook_event(self.store, self.hook("SubagentStop", "root-session", turn="worker-turn-a", agent_id="worker-a", agent_type="explorer", model="worker-model"))
        ingest_otel_payload(self.store, self.otel("root-session", "root-turn", 100))
        ingest_otel_payload(self.store, self.otel("worker-a", "worker-turn-a", 25))
        orchestra = self.fold(run_id)["orchestra"]
        self.assertEqual(orchestra["actual_worker_count"], 2)
        self.assertEqual(orchestra["worker_presence_quality"], "EXACT")
        self.assertEqual(orchestra["worker_total_quality"], "UNKNOWN")
        self.assertIsNone(orchestra["worker_total_tokens"])
        self.assertIsNone(orchestra["orchestra_total_tokens"])

    def test_two_edges_only_one_worker_otel_is_unknown(self) -> None:
        run_id = self.start_root()
        self.add_worker("root-session", "worker-turn-a", "worker-a")
        self.add_worker("root-session", "worker-turn-b", "worker-b")
        self.stop_worker("root-session", "worker-turn-a", "worker-a")
        self.stop_worker("root-session", "worker-turn-b", "worker-b")
        ingest_otel_payload(self.store, self.otel("root-session", "root-turn", 100))
        ingest_otel_payload(self.store, self.otel("worker-a", "worker-turn-a", 25))
        orchestra = self.fold(run_id)["orchestra"]
        self.assertEqual(orchestra["actual_worker_count"], 2)
        self.assertEqual(orchestra["worker_presence_quality"], "EXACT")
        self.assertEqual(orchestra["worker_total_quality"], "UNKNOWN")
        self.assertIsNone(orchestra["worker_total_tokens"])
        self.assertIsNone(orchestra["orchestra_total_tokens"])

    def test_edge_without_lifecycle_is_not_exact_even_with_otel(self) -> None:
        run_id = self.start_root()
        self.add_edge("root-session", "root-turn", "worker-a")
        ingest_otel_payload(self.store, self.otel("root-session", "root-turn", 100))
        ingest_otel_payload(self.store, self.otel("worker-a", "worker-turn-a", 25))
        orchestra = self.fold(run_id)["orchestra"]
        self.assertEqual(orchestra["actual_worker_count"], 1)
        self.assertIsNone(orchestra["worker_total_tokens"])
        self.assertIsNone(orchestra["orchestra_total_tokens"])
        self.assertTrue((self.store.root / "otel-pending.jsonl").exists())

    def test_edge_with_usage_without_lifecycle_is_not_exact(self) -> None:
        run_id = self.start_root()
        self.add_edge("root-session", "root-turn", "worker-a")
        _otel_attach(
            self.store,
            {
                "source_digest": "synthetic-worker-usage",
                "thread_id": "worker-a",
                "turn_id": "worker-turn-a",
                "usage": {
                    "input_tokens": 5,
                    "cached_input_tokens": 0,
                    "cache_write_input_tokens": 0,
                    "non_cached_input_tokens": 5,
                    "output_tokens": 20,
                    "reasoning_output_tokens": 0,
                    "total_tokens": 25,
                },
                "malformed": False,
            },
            (run_id, "worker-a"),
        )
        orchestra = self.fold(run_id)["orchestra"]
        self.assertEqual(orchestra["actual_worker_count"], 1)
        self.assertEqual(orchestra["worker_presence_quality"], "EXACT")
        self.assertEqual(orchestra["worker_total_quality"], "UNKNOWN")
        self.assertIsNone(orchestra["worker_total_tokens"])
        self.assertIsNone(orchestra["orchestra_total_tokens"])

    def test_lifecycle_without_exact_edge_cannot_claim_worker_population(self) -> None:
        run_id = self.start_root()
        observe_worker(
            self.store,
            run_id,
            worker_id="worker-a",
            session_id="root-session",
            turn_id="worker-turn-a",
            launch_status="COMPLETED",
            agent_type="explorer",
            model="worker-model",
            native_thread_id="worker-a",
            native_turn_id="worker-turn-a",
        )
        ingest_otel_payload(self.store, self.otel("root-session", "root-turn", 100))
        ingest_otel_payload(self.store, self.otel("worker-a", "worker-turn-a", 25))
        orchestra = self.fold(run_id)["orchestra"]
        self.assertIsNone(orchestra["actual_worker_count"])
        self.assertEqual(orchestra["worker_presence_quality"], "UNKNOWN")
        self.assertEqual(orchestra["worker_total_quality"], "UNKNOWN")
        self.assertIsNone(orchestra["orchestra_total_tokens"])

    def test_duplicate_edge_is_one_expected_worker(self) -> None:
        run_id = self.start_root()
        self.add_edge("root-session", "root-turn", "worker-a")
        self.add_edge("root-session", "root-turn", "worker-a")
        self.add_worker("root-session", "worker-turn-a", "worker-a")
        self.stop_worker("root-session", "worker-turn-a", "worker-a")
        ingest_otel_payload(self.store, self.otel("root-session", "root-turn", 100))
        ingest_otel_payload(self.store, self.otel("worker-a", "worker-turn-a", 25))
        edges = [item for item in self.store.read() if item.get("record_type") == "worker_edge_observed"]
        orchestra = self.fold(run_id)["orchestra"]
        self.assertEqual(len(edges), 1)
        self.assertEqual(orchestra["actual_worker_count"], 1)
        self.assertEqual(orchestra["worker_total_tokens"], 25)
        self.assertEqual(orchestra["orchestra_total_tokens"], 125)

    def test_nested_child_edge_is_in_expected_population(self) -> None:
        run_id = self.start_root()
        self.add_worker("root-session", "worker-turn-a", "worker-a")
        handle_hook_event(self.store, self.hook("PostToolUse", "root-session", turn="worker-turn-a", tool_name="spawn_agent", tool_response={"result": {"structured_content": {"receiver_thread_ids": ["worker-b"]}}}))
        handle_hook_event(self.store, self.hook("SubagentStart", "root-session", turn="worker-turn-b", agent_id="worker-b", agent_type="explorer", model="worker-model"))
        handle_hook_event(self.store, self.hook("SubagentStop", "root-session", turn="worker-turn-b", agent_id="worker-b", agent_type="explorer", model="worker-model"))
        ingest_otel_payload(self.store, self.otel("root-session", "root-turn", 100))
        ingest_otel_payload(self.store, self.otel("worker-a", "worker-turn-a", 25))
        ingest_otel_payload(self.store, self.otel("worker-b", "worker-turn-b", 35))
        orchestra = self.fold(run_id)["orchestra"]
        self.assertEqual(orchestra["actual_worker_count"], 2)
        self.assertEqual({worker["worker_id"] for worker in orchestra["workers"]}, {"worker-a", "worker-b"})
        self.assertEqual(orchestra["worker_total_tokens"], 60)
        self.assertEqual(orchestra["orchestra_total_tokens"], 160)
        nested_edges = [item for item in self.store.run_records(run_id) if item.get("record_type") == "worker_edge_observed" and item.get("worker_id") == "worker-b"]
        self.assertEqual([(item["parent_session_id"], item["parent_turn_id"]) for item in nested_edges], [("root-session", "worker-turn-a")])

    def test_root_and_one_worker_are_exact(self) -> None:
        run_id = self.start_root()
        self.add_worker("root-session", "worker-turn-a", "worker-a")
        self.stop_worker("root-session", "worker-turn-a", "worker-a")
        ingest_otel_payload(self.store, self.otel("root-session", "root-turn", 100))
        ingest_otel_payload(self.store, self.otel("worker-a", "worker-turn-a", 25))
        handle_hook_event(self.store, self.hook("Stop", "root-session", turn="root-turn"))
        orchestra = self.fold(run_id)["orchestra"]
        self.assertEqual(orchestra["actual_worker_count"], 1)
        self.assertEqual(orchestra["worker_total_tokens"], 25)
        self.assertEqual(orchestra["orchestra_total_tokens"], 125)

    def test_root_and_two_workers_are_exact(self) -> None:
        run_id = self.start_root()
        self.add_worker("root-session", "worker-turn-a", "worker-a")
        self.add_worker("root-session", "worker-turn-b", "worker-b")
        self.stop_worker("root-session", "worker-turn-a", "worker-a")
        self.stop_worker("root-session", "worker-turn-b", "worker-b")
        ingest_otel_payload(self.store, self.otel("root-session", "root-turn", 100))
        ingest_otel_payload(self.store, self.otel("worker-a", "worker-turn-a", 25))
        ingest_otel_payload(self.store, self.otel("worker-b", "worker-turn-b", 35))
        handle_hook_event(self.store, self.hook("Stop", "root-session", turn="root-turn"))
        orchestra = self.fold(run_id)["orchestra"]
        self.assertEqual(orchestra["actual_worker_count"], 2)
        self.assertEqual(orchestra["worker_total_tokens"], 60)
        self.assertEqual(orchestra["orchestra_total_tokens"], 160)

    def test_same_model_workers_remain_distinct(self) -> None:
        run_id = self.start_root()
        self.add_worker("root-session", "turn-a", "same-a")
        self.add_worker("root-session", "turn-b", "same-b")
        self.stop_worker("root-session", "turn-a", "same-a")
        self.stop_worker("root-session", "turn-b", "same-b")
        ingest_otel_payload(self.store, self.otel("same-a", "turn-a", 21))
        ingest_otel_payload(self.store, self.otel("same-b", "turn-b", 22))
        ingest_otel_payload(self.store, self.otel("root-session", "root-turn", 100))
        workers = self.fold(run_id)["orchestra"]["workers"]
        self.assertEqual({worker["worker_id"] for worker in workers}, {"same-a", "same-b"})
        self.assertEqual(self.fold(run_id)["orchestra"]["worker_total_tokens"], 43)

    def test_multiple_turns_per_worker_sum_each_native_turn_once(self) -> None:
        run_id = self.start_root()
        for turn, total in (("worker-turn-1", 31), ("worker-turn-2", 33)):
            self.add_worker("root-session", turn, "worker-a")
            self.stop_worker("root-session", turn, "worker-a")
            ingest_otel_payload(self.store, self.otel("worker-a", turn, total))
        ingest_otel_payload(self.store, self.otel("root-session", "root-turn", 100))
        orchestra = self.fold(run_id)["orchestra"]
        self.assertEqual(orchestra["actual_worker_count"], 1)
        self.assertEqual(orchestra["worker_total_tokens"], 64)

    def test_delayed_otel_reconciles_after_identity_hooks(self) -> None:
        self.assertEqual(ingest_otel_payload(self.store, self.otel("root-session", "root-turn", 100)), 0)
        run_id = self.start_root()
        self.assertEqual(ingest_otel_payload(self.store, self.otel("worker-a", "worker-turn-a", 25)), 0)
        self.add_worker("root-session", "worker-turn-a", "worker-a")
        self.stop_worker("root-session", "worker-turn-a", "worker-a")
        handle_hook_event(self.store, self.hook("Stop", "root-session", turn="root-turn"))
        self.assertEqual(self.fold(run_id)["orchestra"]["orchestra_total_tokens"], 125)
        self.assertFalse((self.store.root / "otel-pending.jsonl").exists())

    def test_duplicate_otel_does_not_increase_total(self) -> None:
        run_id = self.start_root()
        self.add_worker("root-session", "worker-turn-a", "worker-a")
        self.stop_worker("root-session", "worker-turn-a", "worker-a")
        payload = self.otel("worker-a", "worker-turn-a", 25)
        ingest_otel_payload(self.store, payload)
        ingest_otel_payload(self.store, payload)
        ingest_otel_payload(self.store, self.otel("root-session", "root-turn", 100))
        usage = [item for item in self.store.read() if item.get("record_type") == "usage_observed"]
        self.assertEqual(len(usage), 2)
        self.assertEqual(self.fold(run_id)["orchestra"]["orchestra_total_tokens"], 125)

    def test_conflicting_otel_delivery_is_unknown(self) -> None:
        run_id = self.start_root()
        ingest_otel_payload(self.store, self.otel("root-session", "root-turn", 100))
        ingest_otel_payload(self.store, self.otel("root-session", "root-turn", 101))
        folded = self.fold(run_id)
        self.assertEqual(folded["usage_quality"], "UNKNOWN")
        self.assertIsNone(folded["orchestra"]["orchestra_total_tokens"])

    def test_worker_lifecycle_without_usage_is_unknown(self) -> None:
        run_id = self.start_root()
        self.add_worker("root-session", "worker-turn-a", "worker-a")
        self.stop_worker("root-session", "worker-turn-a", "worker-a")
        orchestra = self.fold(run_id)["orchestra"]
        self.assertEqual(orchestra["worker_total_quality"], "UNKNOWN")
        self.assertIsNone(orchestra["orchestra_total_tokens"])

    def test_unresolved_identity_stays_pending_and_unknown(self) -> None:
        run_id = self.start_root()
        ingest_otel_payload(self.store, self.otel("unresolved-thread", "unresolved-turn", 25))
        folded = self.fold(run_id)
        self.assertIsNone(folded["orchestra"]["worker_total_tokens"])
        self.assertTrue((self.store.root / "otel-pending.jsonl").exists())

    def test_root_exact_plus_worker_unknown_never_claims_total(self) -> None:
        run_id = self.start_root()
        self.add_worker("root-session", "worker-turn-a", "worker-a")
        self.stop_worker("root-session", "worker-turn-a", "worker-a")
        ingest_otel_payload(self.store, self.otel("root-session", "root-turn", 100))
        orchestra = self.fold(run_id)["orchestra"]
        self.assertEqual(self.fold(run_id)["usage_quality"], "EXACT")
        self.assertEqual(orchestra["worker_total_quality"], "UNKNOWN")
        self.assertIsNone(orchestra["orchestra_total_tokens"])

    def test_root_worker_collision_prevents_double_count(self) -> None:
        run_id = self.start_root()
        self.add_worker("root-session", "root-turn", "worker-a", native_thread_id="root-session", native_turn_id="root-turn")
        ingest_otel_payload(self.store, self.otel("root-session", "root-turn", 100))
        self.assertEqual(len([item for item in self.store.read() if item.get("record_type") == "usage_observed"]), 0)
        self.assertIsNone(self.fold(run_id)["usage"]["total_tokens"])

    def test_structured_parser_rejects_prose_and_accepts_allowlisted_ids(self) -> None:
        self.assertEqual(_structured_child_ids({"message": "secret worker-a", "text": "worker-b"}), [])
        self.assertEqual(_structured_child_ids({"structured_content": {"receiver_thread_ids": ["worker-a", "worker-b"]}}), ["worker-a", "worker-b"])
        self.assertEqual(_structured_child_ids(json.dumps({"agents_states": {"worker-c": {"status": "pending"}}})), ["worker-c"])

    def test_prompt_and_tool_prose_never_enters_ledger(self) -> None:
        self.start_root()
        secret = "PROMPT_SECRET_TOOL_OUTPUT_SECRET"
        handle_hook_event(self.store, self.hook("PostToolUse", "root-session", turn="root-turn", tool_name="spawn_agent", tool_response={"message": secret, "output": secret}))
        handle_hook_event(self.store, self.hook("SessionEnd", "root-session", transcript_path=secret, agent_transcript_path=secret))
        raw = self.store.ledger_path.read_text(encoding="utf-8")
        self.assertNotIn(secret, raw)
        self.assertNotIn("transcript_path", raw)


if __name__ == "__main__":
    unittest.main()
