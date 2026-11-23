"""Adapt a project-local Codex Stop event to MLflow's notify-hook payload."""

import json
from pathlib import Path
import re
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MLFLOW_COMMAND = ["npx", "-y", "@mlflow/codex@0.4.0", "notify-hook"]


def last_user_prompt(transcript_path):
    """Read user messages only; tolerate incomplete JSONL records at the end."""
    prompt = ""
    with Path(transcript_path).open(encoding="utf-8") as transcript:
        for line in transcript:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            payload = record.get("payload", {})
            if not isinstance(payload, dict):
                continue
            if record.get("type") == "event_msg" and payload.get("type") == "user_message":
                message = payload.get("message")
                if isinstance(message, str) and message.strip():
                    prompt = message
            elif record.get("type") == "response_item" and payload.get("role") == "user":
                content = payload.get("content", [])
                if isinstance(content, list):
                    message = "\n".join(
                        item["text"] for item in content
                        if isinstance(item, dict) and isinstance(item.get("text"), str)
                    )
                    if message.strip():
                        prompt = message
    return prompt


def notify_payload(event):
    if event.get("hook_event_name") != "Stop":
        return None
    if not event.get("session_id") or not event.get("transcript_path"):
        raise ValueError("Stop event is missing session or transcript information")
    prompt = last_user_prompt(event["transcript_path"])
    if not prompt:
        raise ValueError("No user prompt found in transcript")
    return {
        "type": "agent-turn-complete",
        "thread-id": event["session_id"],
        "turn-id": event.get("turn_id", ""),
        "cwd": str(PROJECT_ROOT),
        "input-messages": [prompt],
        "last-assistant-message": event.get("last_assistant_message") or "",
    }


def run(event):
    payload = notify_payload(event)
    if payload is None:
        return
    # Resolve project MLflow settings from the script's project, even if Codex
    # was launched from a subdirectory. Credentials remain in the environment.
    result = subprocess.run(
        MLFLOW_COMMAND + [json.dumps(payload)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=45,
    )
    diagnostics = result.stdout + "\n" + result.stderr
    if result.returncode or re.search(r"failed|error|forbidden|unauthorized", diagnostics, re.I):
        # SDK diagnostics can contain URLs and request details; keep them private.
        raise RuntimeError("MLflow notify hook reported a failure")


def main():
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            raise ValueError("Expected a Stop event object")
        run(event)
    except Exception as error:
        # Tracing must not block or continue the Codex turn. Return only a safe
        # category; never echo transcript contents, SDK errors, or credentials.
        print(f"[mlflow] Project tracing failed ({type(error).__name__}).", file=sys.stderr)
        print(json.dumps({"systemMessage": "MLflow tracing failed for this turn; check the project hook and server access."}))
    else:
        print("{}")


if __name__ == "__main__":
    main()
