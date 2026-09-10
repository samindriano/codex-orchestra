import unittest
from pathlib import Path
import tempfile

from scripts.orchestra_dashboard import build_html, load_snapshot
from scripts.orchestra_telemetry import TelemetryStore, create_turn, ingest_otel_payload


class OrchestraDashboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = TelemetryStore(Path(self.temp.name) / "telemetry")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def otel(self, thread: str, turn: str) -> dict[str, object]:
        attrs = [
            {"key": "thread.id", "value": {"stringValue": thread}},
            {"key": "turn.id", "value": {"stringValue": turn}},
        ]
        for key, value in {"input_tokens": 80, "cached_input_tokens": 0, "cache_write_input_tokens": 0, "non_cached_input_tokens": 80, "output_tokens": 20, "reasoning_tokens": 0, "reasoning_output_tokens": 0, "total_tokens": 100}.items():
            attrs.append({"key": f"codex.turn.token_usage.{key}", "value": {"intValue": value}})
        return {"resourceSpans": [{"scopeSpans": [{"spans": [{"name": "session_task.turn", "attributes": attrs}]}]}]}

    def test_unknown_orchestra_total_is_not_root_fallback(self) -> None:
        turn = create_turn(self.store, session_id="dashboard-session", turn_id="dashboard-turn")
        ingest_otel_payload(self.store, self.otel("dashboard-session", "dashboard-turn"))
        snapshot = load_snapshot(self.store)
        row = snapshot["turns"][0]
        self.assertEqual(row["root_exact_total_tokens"], 100)
        self.assertIsNone(row["worker_exact_total_tokens"])
        self.assertIsNone(row["orchestra_exact_total_tokens"])
        html = build_html(snapshot)
        self.assertIn("UNKNOWN", html)
        self.assertIn("dashboard-turn", html)


if __name__ == "__main__":
    unittest.main()
