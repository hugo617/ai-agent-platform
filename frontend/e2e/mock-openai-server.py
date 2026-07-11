#!/usr/bin/env python3
"""Mock OpenAI-compatible server for E2E tests.

Listens on :8088 and responds to ``POST /v1/chat/completions`` with a fixed
streaming reply in OpenAI's SSE format. This lets the E2E chat flow exercise
the full black-box chain (browser → /chat/stream SSE → stream_agent →
ChatOpenAI → this mock) without depending on an external LLM API.

Run standalone (local E2E):
    python frontend/e2e/mock-openai-server.py

In CI it is launched in the background by the e2e workflow step.
"""

from __future__ import annotations

import json
import time
import uuid

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPLY = "你好！这是一个来自测试环境的模拟回复。"

# A fixed, valid OpenAI-style non-streaming / health-check payload used for any
# non-completions route so connectivity checks succeed.
OK = json.dumps({"status": "ok"}).encode()


def _sse_chunks() -> list[bytes]:
    """Build the SSE byte frames for a single assistant reply."""
    frames: list[bytes] = []
    cid = f"chatcmpl-{uuid.uuid4().hex}"
    # Role-only delta first.
    frames.append(
        ("data: " + json.dumps({
            "id": cid,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "mock-model",
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
        }) + "\n\n").encode()
    )
    # Emit the reply one character at a time (simulates token streaming).
    for ch in REPLY:
        frames.append(
            ("data: " + json.dumps({
                "id": cid,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "mock-model",
                "choices": [{"index": 0, "delta": {"content": ch}, "finish_reason": None}],
            }) + "\n\n").encode()
        )
    # Terminal frame.
    frames.append(
        ("data: " + json.dumps({
            "id": cid,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "mock-model",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }) + "\n\n").encode()
    )
    frames.append(b"data: [DONE]\n\n")
    return frames


class Handler(BaseHTTPRequestHandler):
    # Use HTTP/1.1 so keep-alive works for streaming responses. Without this,
    # the default HTTP/1.0 closes the connection before ChatOpenAI finishes
    # consuming the SSE stream (manifests as ReadError('')).
    protocol_version = "HTTP/1.1"

    def do_POST(self):  # noqa: N802 — http.server convention
        # Drain the request body so http.server doesn't try to read it on the
        # *next* keep-alive request (which corrupts the stream).
        length = int(self.headers.get("Content-Length", 0))
        if length:
            self.rfile.read(length)

        if "chat/completions" in self.path:
            body = b"".join(_sse_chunks())
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            # For HTTP/1.1 without chunked encoding, an explicit Content-Length
            # lets the client know when the body ends cleanly.
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def do_GET(self):  # noqa: N802 — connectivity / health probes
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(OK)))
        self.end_headers()
        self.wfile.write(OK)

    def log_message(self, *args):  # silence default request logging
        pass


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 8088), Handler)
    print("mock-openai-server listening on :8088", flush=True)
    server.serve_forever()
