"""The /v1 dialect — the Anthropic Messages shape, served under SyMoNeuRaL's names.

Four routes, and nothing else lives in this namespace:

    GET  /v1/models                    the registry projection
    GET  /v1/models/{model_id}         one row, plus first-party provenance
    POST /v1/messages                  generation, streaming and non-streaming
    POST /v1/messages/count_tokens     input accounting

The shapes are the dialect's exactly, so an unmodified SDK works with no shim.
What is NOT the dialect's is the model name: a client sees `symon-ai`, and the
engine's own name for the checkpoint never crosses this boundary. `models.py`
explains why the row must carry `anthropic_family_tier` for a first-party name to
be selectable at all.

Errors use the dialect's envelope — `{"type":"error","error":{"type":...}}` — and
never FastAPI's default `{"detail": ...}`. A client that pattern-matches on the
envelope to decide whether a failure is retryable gets the wrong answer from
`detail`, and the failure then looks like a model problem instead of a gateway one.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from . import models, worker

router = APIRouter()

# Anthropic error `type` values, mapped to the status each must carry. Naming them
# here keeps a handler from inventing a fifth spelling of "not found".
ERROR_STATUS: dict[str, int] = {
    "invalid_request_error": 400,
    "authentication_error": 401,
    "permission_error": 403,
    "not_found_error": 404,
    "request_too_large": 413,
    "rate_limit_error": 429,
    "api_error": 500,
    "overloaded_error": 529,
}


def error_body(kind: str, message: str) -> dict[str, Any]:
    return {"type": "error", "error": {"type": kind, "message": message}}


def error(kind: str, message: str, *, request_id: str | None = None) -> JSONResponse:
    headers = {"x-request-id": request_id} if request_id else None
    return JSONResponse(
        status_code=ERROR_STATUS.get(kind, 500),
        content=error_body(kind, message),
        headers=headers,
    )


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


# ---------------------------------------------------------------------------
# GET /v1/models — the registry projection
#
# Paginated in the dialect's cursor style because a conforming client sends
# `?limit=1000` and reads `has_more`/`last_id`. One model does not need paging;
# implementing it anyway costs six lines and means the contract does not change
# shape the day a second model is registered.
# ---------------------------------------------------------------------------
@router.get("/v1/models")
async def list_models(request: Request, limit: int = 20, after_id: str | None = None) -> JSONResponse:
    cards = models.cards()
    if after_id is not None:
        ids = [c.id for c in cards]
        if after_id not in ids:
            return error("invalid_request_error", f"after_id {after_id!r} is not a known model",
                         request_id=_request_id(request))
        cards = cards[ids.index(after_id) + 1:]

    limit = max(1, min(limit, 1000))
    page, has_more = cards[:limit], len(cards) > limit
    rows = [c.to_row() for c in page]
    return JSONResponse(
        {
            "data": rows,
            "has_more": has_more,
            "first_id": rows[0]["id"] if rows else None,
            "last_id": rows[-1]["id"] if rows else None,
        },
        headers={"x-request-id": _request_id(request)},
    )


@router.get("/v1/models/{model_id}")
async def retrieve_model(model_id: str, request: Request) -> JSONResponse:
    try:
        card = models.model(model_id)
    except KeyError:
        return error("not_found_error", f"model {model_id!r} is not served here",
                     request_id=_request_id(request))
    return JSONResponse(card.to_detail(), headers={"x-request-id": _request_id(request)})


# ---------------------------------------------------------------------------
# POST /v1/messages
# ---------------------------------------------------------------------------
async def _read_payload(request: Request) -> tuple[dict[str, Any] | None, JSONResponse | None]:
    try:
        payload = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None, error("invalid_request_error", "request body is not valid JSON",
                           request_id=_request_id(request))
    if not isinstance(payload, dict):
        return None, error("invalid_request_error", "request body must be a JSON object",
                           request_id=_request_id(request))
    return payload, None


def _resolve_model(payload: dict[str, Any], request: Request) -> tuple[models.ModelCard | None, JSONResponse | None]:
    """Map the public model name onto the worker's, or refuse by name.

    Refusing an unknown model here rather than forwarding it is what keeps the
    public namespace closed: the engine might happily answer to a name this estate
    never published, and then that name is live without ever being registered.
    """
    requested = payload.get("model")
    if not isinstance(requested, str) or not requested:
        return None, error("invalid_request_error", "field 'model' is required and must be a string",
                           request_id=_request_id(request))
    try:
        card = models.model(requested)
    except KeyError:
        return None, error("not_found_error",
                           f"model {requested!r} is not served here; known: {sorted(models.REGISTRY)}",
                           request_id=_request_id(request))
    return card, None


def _worker_failure(exc: worker.WorkerUnavailable, request: Request) -> JSONResponse:
    return error("overloaded_error",
                 f"the chat unit is not answering on {worker.BASE_URL}: {exc}",
                 request_id=_request_id(request))


def _relay_error(status: int, parsed: dict[str, Any] | None, raw: str, request: Request) -> JSONResponse:
    """Turn the engine's failure into the dialect's envelope, keeping its words.

    If the engine already answered in the dialect's envelope it is passed through
    unchanged; anything else is wrapped, with the original body preserved as the
    message so the cause is not replaced by a category.
    """
    rid = _request_id(request)
    if isinstance(parsed, dict) and parsed.get("type") == "error" and isinstance(parsed.get("error"), dict):
        return JSONResponse(status_code=status, content=parsed, headers={"x-request-id": rid})
    detail = raw.strip()
    if isinstance(parsed, dict):
        inner = parsed.get("error")
        if isinstance(inner, dict) and isinstance(inner.get("message"), str):
            detail = inner["message"]
        elif isinstance(parsed.get("message"), str):
            detail = parsed["message"]
    kind = {400: "invalid_request_error", 404: "not_found_error", 413: "request_too_large",
            422: "invalid_request_error", 429: "rate_limit_error"}.get(status, "api_error")
    return JSONResponse(status_code=ERROR_STATUS[kind],
                        content=error_body(kind, detail[:2000] or f"chat unit returned HTTP {status}"),
                        headers={"x-request-id": rid})


@router.post("/v1/messages")
async def create_message(request: Request):
    payload, bad = await _read_payload(request)
    if bad is not None:
        return bad
    card, bad = _resolve_model(payload, request)
    if bad is not None:
        return bad

    payload["model"] = card.worker_model
    # Per-card defaults fill only what the caller left unset; see models.Sampling.
    card.sampling.apply(payload)
    rid = _request_id(request)
    streaming = bool(payload.get("stream"))

    if not streaming:
        try:
            status, parsed, raw = await worker.post_json("/v1/messages", payload)
        except worker.WorkerUnavailable as exc:
            return _worker_failure(exc, request)
        if status != 200 or parsed is None:
            return _relay_error(status, parsed, raw, request)
        # The name the caller asked for is the name that comes back. Letting the
        # engine's own id surface here would leak the checkpoint through a field
        # every client logs.
        parsed["model"] = card.id
        return JSONResponse(parsed, headers={"x-request-id": rid})

    async def body():
        async for chunk in worker.post_stream("/v1/messages", payload):
            yield chunk

    try:
        stream = body()
        first = await stream.__anext__()
    except StopAsyncIteration:
        return error("api_error", "chat unit closed the stream before sending an event", request_id=rid)
    except worker.WorkerStreamRefused as exc:
        try:
            parsed = json.loads(exc.body)
        except ValueError:
            parsed = None
        return _relay_error(exc.status, parsed, exc.body, request)
    except worker.WorkerUnavailable as exc:
        return _worker_failure(exc, request)

    async def relay():
        yield first
        async for chunk in stream:
            yield chunk

    return StreamingResponse(
        relay(),
        media_type="text/event-stream",
        headers={
            "cache-control": "no-cache",
            "connection": "keep-alive",
            # Proxies that buffer server-sent events turn a live stream into one
            # late burst, which reads to a client as an idle timeout.
            "x-accel-buffering": "no",
            "x-request-id": rid,
        },
    )


@router.post("/v1/messages/count_tokens")
async def count_tokens(request: Request) -> JSONResponse:
    payload, bad = await _read_payload(request)
    if bad is not None:
        return bad
    card, bad = _resolve_model(payload, request)
    if bad is not None:
        return bad
    payload["model"] = card.worker_model
    try:
        status, parsed, raw = await worker.post_json("/v1/messages/count_tokens", payload)
    except worker.WorkerUnavailable as exc:
        return _worker_failure(exc, request)
    if status != 200 or parsed is None:
        return _relay_error(status, parsed, raw, request)
    # The count is the worker's tokenizer output. If it ever cannot tokenise, the
    # honest answer is an error, never an estimate wearing an exact count's shape.
    return JSONResponse(parsed, headers={"x-request-id": _request_id(request)})
