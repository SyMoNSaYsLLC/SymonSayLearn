# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright 2026 SymonSaysLLC
# SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
"""The chat worker client — the gateway's one way to reach an inference engine.

The worker is the `chat` unit (units.REGISTRY["chat"], 127.0.0.1:8802). It binds
loopback and carries no credential of its own: the gateway is the only thing that
talks to it, and the gateway is what authenticates callers. Putting the credential
on the worker as well would mean two secrets for one trust boundary, and the one
that is easier to read wins.

The engine already speaks the Messages dialect (`POST /v1/messages`,
`POST /v1/messages/count_tokens`), so this module forwards rather than translates.
That is deliberate: a translation layer that re-derives a wire format the engine
already emits is a second implementation of the same spec, and the two drift.
What the gateway adds is identity, the model registry projection, and the error
envelope — not a re-encoding of messages.

Timeouts are asymmetric on purpose. Connect must fail fast (a dead worker should
surface as 503 in under a second, not hang a client), while read must be patient:
prefill on a long prompt against a single consumer card takes as long as it takes,
and a read timeout mid-generation truncates an answer that was about to arrive.
"""

from __future__ import annotations

import os
from typing import Any, AsyncIterator

import httpx

# The worker's base URL. SYM_CHAT_URL overrides for a test double; the default is
# the `chat` unit's registered port, not a second copy of that number by accident.
BASE_URL = os.environ.get("SYM_CHAT_URL", "http://127.0.0.1:8802").rstrip("/")

CONNECT_TIMEOUT_S = float(os.environ.get("SYM_GW_CONNECT_TIMEOUT", "2.0"))
READ_TIMEOUT_S = float(os.environ.get("SYM_GW_READ_TIMEOUT", "900"))

_TIMEOUT = httpx.Timeout(
    connect=CONNECT_TIMEOUT_S,
    read=READ_TIMEOUT_S,
    write=30.0,
    pool=CONNECT_TIMEOUT_S,
)

_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    """One client for the process: connection reuse, and one place to close."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(base_url=BASE_URL, timeout=_TIMEOUT)
    return _client


async def aclose() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


class WorkerUnavailable(RuntimeError):
    """The worker did not answer. Distinct from the worker answering with an error:
    one is a 503 the operator must act on, the other is a 4xx the caller must."""


async def health() -> bool:
    try:
        r = await client().get("/health", timeout=httpx.Timeout(connect=CONNECT_TIMEOUT_S, read=5.0, write=5.0, pool=CONNECT_TIMEOUT_S))
        return r.status_code == 200
    except httpx.HTTPError:
        return False


async def served_models() -> list[dict[str, Any]]:
    """What the engine says it is serving, for cross-checking the registry.

    The registry declares a context window; the engine knows the one it was
    actually started with. Reading it here is what turns 'the numbers agree' from
    an assumption into a check.
    """
    try:
        r = await client().get("/v1/models")
    except httpx.HTTPError as exc:
        raise WorkerUnavailable(str(exc)) from None
    if r.status_code != 200:
        raise WorkerUnavailable(f"worker /v1/models returned HTTP {r.status_code}")
    body = r.json()
    data = body.get("data")
    return data if isinstance(data, list) else []


async def post_json(path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any] | None, str]:
    """POST and read the whole body. Returns (status, parsed_json_or_None, raw_text).

    The raw text is kept so a non-JSON error body from the engine can be reported
    verbatim instead of becoming 'unparseable response' with the evidence thrown
    away.
    """
    try:
        r = await client().post(path, json=payload)
    except httpx.HTTPError as exc:
        raise WorkerUnavailable(str(exc)) from None
    text = r.text
    try:
        return r.status_code, r.json(), text
    except ValueError:
        return r.status_code, None, text


async def post_stream(path: str, payload: dict[str, Any]) -> AsyncIterator[bytes]:
    """Forward a streaming POST byte for byte.

    The bytes are relayed unmodified. Re-serialising server-sent events through a
    parser would risk reordering or reframing them, and the client's event
    lifecycle is exactly what a re-encode is most likely to break.

    A failure before the first byte is raised so the caller can still answer with a
    proper status; a failure mid-stream cannot be, because the status line is long
    gone — the stream simply ends, which is what a disconnect looks like anyway.
    """
    try:
        async with client().stream("POST", path, json=payload) as r:
            if r.status_code != 200:
                body = (await r.aread()).decode("utf-8", "replace")
                raise WorkerStreamRefused(r.status_code, body)
            async for chunk in r.aiter_raw():
                yield chunk
    except httpx.HTTPError as exc:
        raise WorkerUnavailable(str(exc)) from None


class WorkerStreamRefused(RuntimeError):
    """The worker rejected a streaming request before any event was sent, so the
    gateway can still answer with a real status code rather than an empty stream."""

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"worker refused stream: HTTP {status}")
        self.status = status
        self.body = body
