"""The gateway process — one loopback port, the /v1 dialect, and the credential.

This is the thing a client configures. It is NOT a rack unit: it has no entry in
units.REGISTRY, no port in the 8801-8810 block and no GPU claim. It is what the
units sit behind.

    client  ->  127.0.0.1:9001  (this process)  ->  chat unit 127.0.0.1:8802

Served here, and nothing else:

    GET  /health                    public, touches no unit
    GET  /ready                     503 until the chat unit answers
    GET  /version                   gateway + engine identity
    GET  /v1/models                 registry projection        (dialect.py)
    GET  /v1/models/{model_id}      one row + provenance       (dialect.py)
    POST /v1/messages               generation                 (dialect.py)
    POST /v1/messages/count_tokens  input accounting           (dialect.py)

Everything else is 404 in the dialect's envelope. The /api/* namespace is NOT
served by this process: it belongs to symoneural_api.main, which is a separate
application on its own port, and the reserved-namespace rule in endpoints.py is
what keeps the two from growing into each other.

Credential. One key, read from a file the operator provisions, never from a
literal and never generated here. Both header spellings the dialect permits are
accepted, because which one a client sends is the client's choice, not ours:

    Authorization: Bearer <key>
    x-api-key: <key>

The key is compared with hmac.compare_digest and is never logged, never echoed
and never included in an error message. An unconfigured gateway refuses every
authenticated route with 503 rather than defaulting to open: a missing secret must
fail closed, or the failure mode of a provisioning mistake is a public endpoint.
"""

from __future__ import annotations

import hmac
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import dialect, models, worker

__all__ = ["app", "main"]

STARTED = time.time()
VERSION = "1.0.0"

# Where the key lives. 0600, outside the repository, provisioned by the operator.
# SYM_GW_* is deliberately distinct from SYM_GATEWAY_*, which /etc/symoneural/
# already uses for the settlement gateway — two unrelated things called "gateway"
# is precisely how the wrong secret gets read.
KEY_FILE = Path(os.environ.get(
    "SYM_GW_KEY_FILE",
    os.path.expanduser("~/.config/symoneural/gateway-9001.key"),
))

# Routes that must answer while the gateway is unconfigured and every unit is off.
PUBLIC_PATHS: frozenset[str] = frozenset({"/health"})


def _read_key() -> str | None:
    """The provisioned key, or None if unconfigured.

    Read on every request rather than cached at import: rotating the key should
    take effect on the next request, not on the next restart, and an operator who
    has just rotated a credential should not have to guess whether a stale copy is
    still being honoured.
    """
    try:
        value = KEY_FILE.read_text().strip()
    except OSError:
        return None
    return value or None


def key_fingerprint() -> str | None:
    """A stable, non-reversing identifier for the configured key.

    Reported so an operator can confirm which credential is live without either
    side ever printing it.
    """
    import hashlib

    key = _read_key()
    if key is None:
        return None
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _presented(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if header and header.lower().startswith("bearer "):
        token = header[7:].strip()
        if token:
            return token
    token = request.headers.get("x-api-key")
    return token.strip() if token and token.strip() else None


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Own the worker client's lifetime.

    Closing it on shutdown is what stops a reload from leaking sockets to the chat
    unit. Written as a lifespan rather than @app.on_event because the latter is
    deprecated and emits a warning on every start, which trains an operator to
    ignore the startup log.
    """
    yield
    await worker.aclose()


app = FastAPI(
    title="SyMoNeuRaL gateway",
    version=VERSION,
    description="The /v1 dialect over this estate's own inference units.",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=_lifespan,
)


@app.middleware("http")
async def identify_and_authenticate(request: Request, call_next):
    """Request id first, then the credential.

    The id is minted before anything can fail so that every answer, including a
    rejection, carries one. A client that reports a failure with an id can be
    matched to a line in the log; one that cannot leaves the operator correlating
    by timestamp.
    """
    incoming = request.headers.get("x-request-id", "").strip()
    request.state.request_id = incoming[:128] if incoming else secrets.token_hex(16)

    path = request.url.path
    if path not in PUBLIC_PATHS:
        expected = _read_key()
        if expected is None:
            return dialect.error(
                "api_error",
                f"gateway is unconfigured: no credential at {KEY_FILE}",
                request_id=request.state.request_id,
            )
        presented = _presented(request)
        if presented is None or not hmac.compare_digest(presented.encode(), expected.encode()):
            return dialect.error(
                "authentication_error",
                "invalid or missing credential; send Authorization: Bearer <key> or x-api-key: <key>",
                request_id=request.state.request_id,
            )

    response = await call_next(request)
    response.headers["x-request-id"] = request.state.request_id
    return response


@app.exception_handler(404)
async def _not_found(request: Request, _exc: Any) -> JSONResponse:
    """404 in the dialect's envelope, never FastAPI's {"detail": ...}."""
    return dialect.error(
        "not_found_error",
        f"no such route: {request.method} {request.url.path}",
        request_id=getattr(request.state, "request_id", ""),
    )


@app.get("/health")
async def health() -> dict[str, Any]:
    """Public. Answers while every unit is off, and touches none of them."""
    return {"status": "ok", "uptime_s": round(time.time() - STARTED, 1)}


@app.get("/ready")
async def ready() -> JSONResponse:
    """Ready means a caller's next request would actually be served.

    That is a live check against the chat unit, not a flag this process sets about
    itself. A gateway that reports ready because it finished starting is reporting
    on the wrong thing.
    """
    rid = ""
    if await worker.health():
        return JSONResponse({"status": "ready", "chat_unit": worker.BASE_URL,
                             "models": sorted(models.REGISTRY)})
    return JSONResponse(
        status_code=503,
        content={"status": "unavailable", "reason": "chat_unit_unreachable",
                 "chat_unit": worker.BASE_URL},
        headers={"x-request-id": rid} if rid else None,
    )


@app.get("/version")
async def version() -> dict[str, Any]:
    """Gateway identity, the credential's fingerprint, and what the engine reports.

    The engine's own rows are included verbatim so the registry's declared context
    window can be compared with the served one instead of trusted.
    """
    try:
        served = await worker.served_models()
    except worker.WorkerUnavailable as exc:
        served = [{"error": str(exc)}]
    return {
        "gateway": VERSION,
        "chat_unit": worker.BASE_URL,
        "credential_fingerprint": key_fingerprint(),
        "registry": [c.to_detail() for c in models.cards()],
        "engine_reports": served,
    }


app.include_router(dialect.router)


def main() -> None:
    import uvicorn

    uvicorn.run(
        app,
        # Loopback is not a default here, it is the design. Public reach is through
        # the edge proxy and the tunnel, never by binding an interface.
        host=os.environ.get("SYM_GW_HOST", "127.0.0.1"),
        port=int(os.environ.get("SYM_GW_PORT", "9001")),
        log_level=os.environ.get("SYM_LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
