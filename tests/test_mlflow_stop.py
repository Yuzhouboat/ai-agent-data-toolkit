"""Exercise the Stop adapter without contacting MLflow or creating traces."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "codex/hooks/mlflow_stop.py"
spec = importlib.util.spec_from_file_location("mlflow_stop", SCRIPT)
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


class StopAdapterTests(unittest.TestCase):
    def test_transcript_to_notify_payload_and_project_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            transcript = Path(directory) / "transcript.jsonl"
            records = [
                {"type": "event_msg", "payload": {"type": "user_message", "message": "old prompt"}},
                {"type": "response_item", "payload": {"role": "user", "content": [
                    {"type": "input_text", "text": "latest prompt"}, {"type": "input_image"}]}},
                {"type": "response_item", "payload": {"role": "assistant", "content": [
                    {"type": "output_text", "text": "do not treat as user input"}]}},
            ]
            transcript.write_text("\n".join(map(json.dumps, records)) + "\n{incomplete")
            event = {"hook_event_name": "Stop", "session_id": "test-session", "turn_id": "test-turn",
                     "transcript_path": str(transcript), "cwd": str(Path(directory) / "nested"),
                     "last_assistant_message": "test response"}
            result = subprocess.CompletedProcess([], 0, "", "")
            with patch.object(adapter.subprocess, "run", return_value=result) as run:
                adapter.run(event)
            args, kwargs = run.call_args
            payload = json.loads(args[0][-1])
            self.assertEqual(payload["input-messages"], ["latest prompt"])
            self.assertEqual(payload["thread-id"], "test-session")
            self.assertEqual(payload["turn-id"], "test-turn")
            self.assertEqual(payload["last-assistant-message"], "test response")
            self.assertEqual(kwargs["cwd"], SCRIPT.parents[2])
            self.assertEqual(kwargs["timeout"], 45)

    def test_unrelated_event_does_not_invoke_sdk(self):
        with patch.object(adapter.subprocess, "run") as run:
            adapter.run({"hook_event_name": "SessionStart"})
        run.assert_not_called()

    def test_missing_transcript_is_not_reported_as_an_upload(self):
        with self.assertRaises(ValueError):
            adapter.notify_payload({"hook_event_name": "Stop", "session_id": "test"})

    def test_failures_return_safe_warning_without_blocking(self):
        for failure in [FileNotFoundError("private path"), RuntimeError("secret"),
                        subprocess.TimeoutExpired("private command", 45)]:
            with self.subTest(failure=type(failure).__name__):
                out, err = io.StringIO(), io.StringIO()
                with patch.object(adapter, "run", side_effect=failure), \
                     patch.object(adapter.sys, "stdin", io.StringIO("{}")), \
                     contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    adapter.main()
                result = json.loads(out.getvalue())
                self.assertIn("systemMessage", result)
                self.assertNotIn("decision", result)
                self.assertNotIn("secret", out.getvalue() + err.getvalue())
                self.assertNotIn("private", out.getvalue() + err.getvalue())

    def test_sdk_error_with_zero_exit_is_detected(self):
        with patch.object(adapter, "notify_payload", return_value={"type": "agent-turn-complete"}), \
             patch.object(adapter.subprocess, "run", return_value=subprocess.CompletedProcess(
                 [], 0, "", "Failed to export trace: secret details")):
            with self.assertRaisesRegex(RuntimeError, "reported a failure"):
                adapter.run({})


if __name__ == "__main__":
    unittest.main()
