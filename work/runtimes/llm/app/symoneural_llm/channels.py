# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright 2026 SymonSaysLLC
# SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
"""The channel prompt style — for checkpoints trained to reason in one channel and answer in another.

Some checkpoints (the 20B MXFP4 mixture-of-experts the chat unit serves is one) were trained on a
transcript where every message carries a role and a channel:

    <|start|>system<|message|>...<|end|>
    <|start|>user<|message|>...<|end|>
    <|start|>assistant<|channel|>analysis<|message|>...reasoning...<|end|>
    <|start|>assistant<|channel|>final<|message|>...the answer...<|return|>

The native side renders those markers as text, so the adapter can build the prompt in this
shape and split the output back into the Messages dialect's content blocks: `analysis` and
`commentary` become `thinking` blocks, `final` becomes `text`. Generation stops at `<|return|>` (the turn is over) or `<|call|>` (a tool call was made).

A tool call is a message like any other, distinguished by a recipient in its header:

    <|start|>assistant<|channel|>commentary to=functions.get_weather <|constrain|>json<|message|>{"city":"Paris"}<|call|>

and its result comes back as a message FROM that tool:

    <|start|>functions.get_weather to=assistant<|channel|>commentary<|message|>{"c":14}<|end|>

so a call becomes a `tool_use` block and a result is replayed into the transcript.

This module is pure: no I/O, no model, and the splitter is incremental so streaming emits a
thinking block first and a text block after it, with markers that arrive split across pieces
handled by holding back a short tail until they can be recognised.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any, Iterator

STOPS: tuple[str, ...] = ("<|return|>", "<|call|>")
_TERMINATORS = ("<|end|>", "<|return|>", "<|call|>", "<|start|>")
_HOLD = 24        # longer than any marker we may be in the middle of receiving
_HEADER_MAX = 400  # a header is short; past this, there is no header coming and it is plain text

_CHANNEL_RE = re.compile(r"<\|channel\|>([a-z]+)")
_RECIPIENT_RE = re.compile(r"to=([^\s<]+)")


def _parse_header(header: str) -> tuple[str, str | None]:
    """(channel, recipient) from the text between the role and `<|message|>`.

    A missing channel means `final`: some checkpoints omit it on the answer, and treating
    that as an error would turn a good answer into a protocol failure."""
    ch = _CHANNEL_RE.search(header)
    to = _RECIPIENT_RE.search(header)
    return (ch.group(1) if ch else "final"), (to.group(1) if to else None)


def tool_name(recipient: str) -> str:
    """`functions.get_weather` names the tool `get_weather`; the namespace is the format's,
    not the caller's, and a client never sees it."""
    return recipient.rsplit(".", 1)[-1]

# The identity and the reasoning level are deployment settings, not code: the identity is the
# product's own; the level is the checkpoint's own knob ("low" | "medium" | "high").
IDENTITY = os.environ.get("SYM_LLM_IDENTITY", "You are Symon, the assistant served by this SyMoNsAyLeaRn runtime.")
REASONING = os.environ.get("SYM_LLM_REASONING", "medium")


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in (content or []) if isinstance(b, dict) and b.get("type") == "text")


_JSON_TO_TS = {"string": "string", "number": "number", "integer": "number", "boolean": "boolean",
               "object": "object", "array": "any[]", "null": "null"}


def _ts_type(schema: dict) -> str:
    """One JSON Schema property as the type language this format declares tools in."""
    if not isinstance(schema, dict):
        return "any"
    if schema.get("enum"):
        return " | ".join(json.dumps(v) for v in schema["enum"])
    kind = schema.get("type")
    if kind == "array":
        return f"{_ts_type(schema.get('items') or {})}[]"
    if isinstance(kind, list):
        return " | ".join(_JSON_TO_TS.get(k, "any") for k in kind)
    return _JSON_TO_TS.get(kind, "any")


def render_tools(tools: list[dict]) -> str:
    """The caller's tools as a namespace this checkpoint was trained to read.

    The dialect describes a tool with JSON Schema; this format declares one as a typed
    function in a namespace. Translating is not decoration — a checkpoint trained on this
    shape will not reliably call a tool described any other way, and an optional property
    rendered as required is a call it declines to make.
    """
    if not tools:
        return ""
    out = ["# Tools", "", "## functions", "", "namespace functions {", ""]
    for tool in tools:
        desc = (tool.get("description") or "").strip()
        if desc:
            out += [f"// {line}" for line in desc.splitlines()]
        schema = tool.get("input_schema") or {}
        props = schema.get("properties") or {}
        required = set(schema.get("required") or ())
        if not props:
            out += [f"type {tool['name']} = () => any;", ""]
            continue
        out.append(f"type {tool['name']} = (_: {{")
        for name, prop in props.items():
            pd = (prop.get("description") or "").strip() if isinstance(prop, dict) else ""
            if pd:
                out += [f"// {line}" for line in pd.splitlines()]
            mark = "" if name in required else "?"
            out.append(f"{name}{mark}: {_ts_type(prop)},")
        out += ["}) => any;", ""]
    out += ["} // namespace functions"]
    return "\n".join(out)


def _tool_names(messages: list) -> dict[str, str]:
    """tool_use id -> tool name, so a result can be replayed as a message from that tool.

    A `tool_result` carries only the id of the call it answers. The format needs the name,
    because the result is a message FROM the tool. The mapping is rebuilt from the
    transcript rather than stored, since the adapter holds no state between requests."""
    names: dict[str, str] = {}
    for m in messages or []:
        for b in (m.get("content") or []) if not isinstance(m.get("content"), str) else ():
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("id"):
                names[b["id"]] = b.get("name", "")
    return names


def build_prompt(req: dict, *, identity: str = IDENTITY, reasoning: str = REASONING) -> str:
    """The request as the checkpoint's own transcript.

    Prior assistant text is replayed on the `final` channel; a prior tool call is replayed
    on `commentary` with its recipient, and the result that answered it as a message from
    that tool. Replaying a call without its result, or a result without its call, gives the
    model a transcript it was never trained on."""
    parts = [f"<|start|>system<|message|>{identity}\nReasoning: {reasoning}\n"
             "# Valid channels: analysis, commentary, final. Channel must be included for every message."]
    if req.get("tools"):
        parts.append("\nCalls to these tools must go to the commentary channel: 'to=functions.<name>'.")
    parts.append("<|end|>")

    developer = []
    if req.get("system"):
        developer.append(f"# Instructions\n\n{_text_of(req['system'])}")
    if req.get("tools"):
        developer.append(render_tools(req["tools"]))
    if developer:
        parts.append("<|start|>developer<|message|>" + "\n\n".join(developer) + "<|end|>")

    names = _tool_names(req.get("messages", []))
    for m in req.get("messages", []):
        role = m.get("role")
        content = m.get("content")
        blocks = content if isinstance(content, list) else None
        if role == "user":
            # A user turn may carry tool results rather than prose; those are messages from
            # the tool, not from the person, and are replayed as such.
            results = [b for b in (blocks or []) if isinstance(b, dict) and b.get("type") == "tool_result"]
            for r in results:
                name = names.get(r.get("tool_use_id", ""), "tool")
                body = r.get("content")
                body = body if isinstance(body, str) else "".join(
                    b.get("text", "") for b in (body or []) if isinstance(b, dict))
                parts.append(f"<|start|>functions.{name} to=assistant<|channel|>commentary<|message|>{body}<|end|>")
            said = _text_of(content)
            if said or not results:
                parts.append(f"<|start|>user<|message|>{said}<|end|>")
        elif role == "assistant":
            calls = [b for b in (blocks or []) if isinstance(b, dict) and b.get("type") == "tool_use"]
            said = _text_of(content)
            if said:
                parts.append(f"<|start|>assistant<|channel|>final<|message|>{said}<|end|>")
            for c in calls:
                arg = json.dumps(c.get("input") or {}, separators=(",", ":"))
                parts.append(f"<|start|>assistant<|channel|>commentary to=functions.{c.get('name', '')} "
                             f"<|constrain|>json<|message|>{arg}<|call|>")
        else:
            raise ValueError(f"invalid role {role!r}")
    parts.append("<|start|>assistant")
    return "".join(parts)


class ChannelStream:
    """Incremental splitter: feed() pieces, receive block events; finish() flushes.

    Events are tuples: ("start", index, block) · ("delta", index, delta) · ("stop", index),
    where block/delta are the dialect's shapes ({"type": "thinking", "thinking": ""} /
    {"type": "thinking_delta", "thinking": s}; {"type": "text", "text": ""} /
    {"type": "text_delta", "text": s}).
    """

    def __init__(self) -> None:
        self.buf = ""
        self.state = "between"       # between | in_message
        self.kind = "text"           # kind of the open block: text | thinking | tool_use
        self.index = -1
        self.done = False
        self.channels: list[str] = []
        self.called_tool = False     # a tool call was made; the turn is not over

    def feed(self, piece: str) -> list[tuple]:
        if self.done:
            return []
        self.buf += piece
        return self._drain(final=False)

    def finish(self) -> list[tuple]:
        ev = self._drain(final=True)
        if self.state == "in_message":
            ev.append(("stop", self.index)); self.state = "between"
        return ev

    # ---------------------------------------------------------------------------- internals
    def _open(self, channel: str, ev: list, recipient: str | None = None) -> None:
        self.index += 1
        self.channels.append(channel)
        if recipient:
            # A recipient makes this a call, whatever channel carries it. The id is minted
            # here because the format has none: the dialect requires one so a result can
            # name the call it answers.
            self.kind = "tool_use"
            self.called_tool = True
            block = {"type": "tool_use", "id": "toolu_" + uuid.uuid4().hex[:24],
                     "name": tool_name(recipient), "input": {}}
        elif channel == "final":
            self.kind = "text"
            block = {"type": "text", "text": ""}
        else:
            self.kind = "thinking"
            block = {"type": "thinking", "thinking": ""}
        ev.append(("start", self.index, block))
        self.state = "in_message"

    def _delta(self, s: str, ev: list) -> None:
        if not s:
            return
        if self.kind == "tool_use":
            # The arguments stream as JSON text; a client accumulates them and parses once.
            ev.append(("delta", self.index, {"type": "input_json_delta", "partial_json": s}))
        elif self.kind == "text":
            ev.append(("delta", self.index, {"type": "text_delta", "text": s}))
        else:
            ev.append(("delta", self.index, {"type": "thinking_delta", "thinking": s}))

    def _drain(self, *, final: bool) -> list[tuple]:
        ev: list[tuple] = []
        while self.buf and not self.done:
            if self.state == "between":
                # Everything from the role marker to `<|message|>` is the header, whatever it
                # contains. Scanning for the terminator rather than matching one fixed shape is
                # what lets a recipient be recognised: this format puts `to=` in more than one
                # position, and a pattern that assumed a position silently produced a thinking
                # block where a tool call belonged.
                lead = re.match(r"\s*(?:<\|start\|>assistant)?", self.buf)
                rest = self.buf[lead.end() if lead else 0:]
                idx = rest.find("<|message|>")
                if idx != -1 and idx <= _HEADER_MAX:
                    channel, recipient = _parse_header(rest[:idx])
                    self.buf = rest[idx + len("<|message|>"):]
                    self._open(channel, ev, recipient)
                    continue
                if not final and idx == -1 and (rest.lstrip().startswith("<|") or len(rest) < _HOLD):
                    return ev                      # a header may still be arriving
                # No header at all: the model answered in plain text, which is the final channel.
                self.buf = rest
                if self.buf.strip() == "":
                    self.buf = ""
                    return ev
                self._open("final", ev)
                continue
            # in_message: find the earliest terminator
            cut, which = None, None
            for t in _TERMINATORS:
                i = self.buf.find(t)
                if i != -1 and (cut is None or i < cut):
                    cut, which = i, t
            if cut is None:
                keep = 0 if final else min(_HOLD, len(self.buf))
                emit, self.buf = self.buf[:len(self.buf) - keep], self.buf[len(self.buf) - keep:]
                self._delta(emit, ev)
                return ev
            self._delta(self.buf[:cut], ev)
            ev.append(("stop", self.index)); self.state = "between"
            if which == "<|start|>":
                self.buf = self.buf[cut:]                 # the header parser consumes it
            else:
                self.buf = self.buf[cut + len(which):]
                if which in ("<|return|>", "<|call|>"):
                    self.done = True
        return ev


def parse_output(text: str) -> list[dict]:
    """One-shot: the whole generation → content blocks."""
    s = ChannelStream()
    events = s.feed(text) + s.finish()
    blocks: dict[int, dict] = {}
    raw_args: dict[int, str] = {}
    for e in events:
        if e[0] == "start":
            blocks[e[1]] = dict(e[2])
        elif e[0] == "delta":
            b, d = blocks[e[1]], e[2]
            if d["type"] == "input_json_delta":
                raw_args[e[1]] = raw_args.get(e[1], "") + d["partial_json"]
            elif b["type"] == "text":
                b["text"] += d["text"]
            else:
                b["thinking"] += d["thinking"]
    out = [blocks[i] for i in sorted(blocks)]
    for i, b in zip(sorted(blocks), out):
        if b["type"] == "thinking":
            b["signature"] = ""
        elif b["type"] == "tool_use":
            # Arguments arrive as text. Malformed JSON becomes empty input rather than an
            # exception: a client can see a call it cannot satisfy and say so, which is a
            # better failure than the whole response disappearing.
            try:
                parsed = json.loads(raw_args.get(i, "") or "{}")
            except json.JSONDecodeError:
                parsed = {}
            b["input"] = parsed if isinstance(parsed, dict) else {}
    return out or [{"type": "text", "text": ""}]


def sse(events: Iterator[tuple]) -> Iterator[str]:
    """Block events → the dialect's server-sent events."""
    for e in events:
        if e[0] == "start":
            yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': e[1], 'content_block': e[2]})}\n\n"
        elif e[0] == "delta":
            yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': e[1], 'delta': e[2]})}\n\n"
        elif e[0] == "stop":
            yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': e[1]})}\n\n"
