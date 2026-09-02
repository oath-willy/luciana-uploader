from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any


class CodexAppServerError(RuntimeError):
    pass


class CodexAppServer:
    """Small JSONL client for one isolated Codex App Server invocation."""

    def __init__(self, executable: str = "codex", timeout_seconds: int = 900):
        self.executable = executable
        self.timeout_seconds = timeout_seconds
        self._messages: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._deferred: deque[dict[str, Any]] = deque()
        self._stderr: deque[str] = deque(maxlen=50)
        self._next_id = 1
        self._process: subprocess.Popen[str] | None = None

    def __enter__(self) -> "CodexAppServer":
        self._process = subprocess.Popen(
            [self.executable, "app-server", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        self.request(
            "initialize",
            {
                "clientInfo": {"name": "luciana-bs25ai-worker", "version": "1.0.0"},
                "capabilities": {"experimentalApi": True},
            },
        )
        self.notify("initialized", {})
        return self

    def __exit__(self, *_: Any) -> None:
        if not self._process:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=5)

    def start_thread(self, cwd: Path) -> str:
        result = self.request(
            "thread/start",
            {
                "cwd": str(cwd),
                "model": "gpt-5.6-sol",
                "approvalPolicy": "never",
                "sandbox": "read-only",
                "ephemeral": False,
                "serviceName": "luciana-bs25ai",
            },
        )
        return str(result["thread"]["id"])

    def resume_thread(self, thread_id: str, cwd: Path) -> None:
        self.request(
            "thread/resume",
            {
                "threadId": thread_id,
                "cwd": str(cwd),
                "model": "gpt-5.6-sol",
                "approvalPolicy": "never",
                "sandbox": "read-only",
            },
        )

    def set_goal(self, thread_id: str, objective: str, status: str) -> None:
        self.request(
            "thread/goal/set",
            {"threadId": thread_id, "objective": objective, "status": status},
        )

    def set_goal_status(self, thread_id: str, status: str) -> None:
        self.request(
            "thread/goal/set",
            {"threadId": thread_id, "status": status},
        )

    def run_turn(
        self,
        thread_id: str,
        prompt: str,
        output_schema: dict[str, Any],
        effort: str,
        network_access: bool,
    ) -> dict[str, Any]:
        response = self.request(
            "turn/start",
            {
                "threadId": thread_id,
                "input": [{"type": "text", "text": prompt}],
                "model": "gpt-5.6-sol",
                "effort": effort,
                "approvalPolicy": "never",
                "sandboxPolicy": {
                    "type": "readOnly",
                    "networkAccess": network_access,
                },
                "outputSchema": output_schema,
            },
        )
        turn_id = str(response["turn"]["id"])
        deadline = time.monotonic() + self.timeout_seconds
        final_text: str | None = None
        while time.monotonic() < deadline:
            message = self._next_message(deadline)
            method = message.get("method")
            params = message.get("params") or {}
            if params.get("turnId") != turn_id:
                continue
            if method == "item/completed":
                item = params.get("item") or {}
                if item.get("type") == "agentMessage":
                    final_text = item.get("text")
            elif method == "turn/completed":
                turn = params.get("turn") or {}
                if turn.get("status") != "completed":
                    error = turn.get("error") or "turn Codex non completato"
                    raise CodexAppServerError(str(error))
                if not final_text:
                    raise CodexAppServerError("Codex non ha emesso un risultato strutturato")
                try:
                    return json.loads(final_text)
                except json.JSONDecodeError as exc:
                    raise CodexAppServerError("Output Codex non conforme allo schema JSON") from exc
        raise CodexAppServerError("Timeout durante l'analisi Codex")

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        self._write({"id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + self.timeout_seconds
        deferred: list[dict[str, Any]] = []
        while time.monotonic() < deadline:
            message = self._next_raw_message(deadline)
            if message.get("id") != request_id:
                deferred.append(message)
                continue
            self._deferred.extend(deferred)
            if "error" in message:
                raise CodexAppServerError(f"{method}: {message['error']}")
            return message.get("result") or {}
        raise CodexAppServerError(f"Timeout App Server: {method}")

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._write({"method": method, "params": params})

    def _write(self, message: dict[str, Any]) -> None:
        if not self._process or not self._process.stdin:
            raise CodexAppServerError("App Server Codex non avviato")
        self._process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self._process.stdin.flush()

    def _next_message(self, deadline: float) -> dict[str, Any]:
        if self._deferred:
            return self._deferred.popleft()
        return self._next_raw_message(deadline)

    def _next_raw_message(self, deadline: float) -> dict[str, Any]:
        timeout = max(0.01, deadline - time.monotonic())
        try:
            message = self._messages.get(timeout=timeout)
        except queue.Empty as exc:
            raise CodexAppServerError("Timeout in attesa di Codex App Server") from exc
        if message is None:
            detail = "\n".join(self._stderr)
            raise CodexAppServerError(f"Codex App Server terminato. {detail}".strip())
        return message

    def _read_stdout(self) -> None:
        assert self._process and self._process.stdout
        for line in self._process.stdout:
            try:
                self._messages.put(json.loads(line))
            except json.JSONDecodeError:
                self._stderr.append(f"stdout non JSON: {line.rstrip()}")
        self._messages.put(None)

    def _read_stderr(self) -> None:
        assert self._process and self._process.stderr
        for line in self._process.stderr:
            self._stderr.append(line.rstrip())
