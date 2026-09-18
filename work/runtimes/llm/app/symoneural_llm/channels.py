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
`commentary` become `thinking` blocks, `final` becomes `text`. Generation stops at `<|return|>`
(the turn is over) or `<|call|>` (a tool call follows).

This module is pure: no I/O, no model, and the splitter is incremental so streaming emits a
thinking block first and a text block after it, with markers that arrive split across pieces
handled by holding back a short tail until they can be recognised.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Iterator

STOPS: tuple[str, ...] = ("<|return|>", "<|call|>")
_TERMINATORS = ("<|end|>", "<|return|>", "<|call|>", "<|start|>")
_HOLD = 24  # longer than any marker we may be in the middle of receiving

# The identity and the reasoning level are deployment settings, not code: the identity is the
# product's own; the level is the checkpoint's own knob ("low" | "medium" | "high").
IDENTITY = os.environ.get("SYM_LLM_IDENTITY", "You are Symon, the assistant served by this SyMoNsAyLeaRn runtime.")
REASONING = os.environ.get("SYM_LLM_REASONING", "medium")


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in (content or []) if isinstance(b, dict) and b.get("type") == "text")


def build_prompt(req: dict, *, identity: str = IDENTITY, reasoning: str = REASONING) -> str:
    """The request as the checkpoint's own transcript. Prior assistant turns are replayed as
    `final` channel messages; the request's `system` becomes the developer instructions."""
    parts = [f"<|start|>system<|message|>{identity}\nReasoning: {reasoning}\n"
             "# Valid channels: analysis, commentary, final. Channel must be included for every message.<|end|>"]
    if req.get("system"):
        parts.append(f"<|start|>developer<|message|># Instructions\n\n{_text_of(req['system'])}<|end|>")
    for m in req.get("messages", []):
        role = m.get("role")
        if role == "user":
            parts.append(f"<|start|>user<|message|>{_text_of(m.get('content'))}<|end|>")
        elif role == "assistant":
            parts.append(f"<|start|>assistant<|channel|>final<|message|>{_text_of(m.get('content'))}<|end|>")
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
        self.kind = "text"           # kind of the open block
        self.index = -1
        self.done = False
        self.channels: list[str] = []

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
    def _open(self, channel: str, ev: list) -> None:
        self.index += 1
        self.kind = "text" if channel == "final" else "thinking"
        self.channels.append(channel)
        ev.append(("start", self.index, {"type": "text", "text": ""} if self.kind == "text" else {"type": "thinking", "thinking": ""}))
        self.state = "in_message"

    def _delta(self, s: str, ev: list) -> None:
        if s:
            ev.append(("delta", self.index, {"type": "text_delta", "text": s} if self.kind == "text" else {"type": "thinking_delta", "thinking": s}))

    def _drain(self, *, final: bool) -> list[tuple]:
        ev: list[tuple] = []
        while self.buf and not self.done:
            if self.state == "between":
                m = re.match(r"\s*(?:<\|start\|>assistant)?\s*(?:<\|channel\|>([a-z]+)(?:\s*<\|constrain\|>[a-z]+)?\s*<\|message\|>)?", self.buf)
                header = m.group(0) if m else ""
                if m and m.group(1):                      # a complete channel header
                    self.buf = self.buf[m.end():]
                    self._open(m.group(1), ev)
                    continue
                # No complete header yet. Either more is coming, or the model answered without
                # markers at all — then it is plain text on the final channel.
                if not final and (len(self.buf) < _HOLD or self.buf.lstrip().startswith("<|")):
                    return ev
                if self.buf.lstrip().startswith("<|") and not final:
                    return ev
                self.buf = self.buf[len(header):] if header and not m.group(1) and self.buf.startswith(header) and "<|" in header else self.buf
                if self.buf.strip() == "":
                    self.buf = ""; return ev
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
    for e in events:
        if e[0] == "start":
            blocks[e[1]] = dict(e[2])
        elif e[0] == "delta":
            b = blocks[e[1]]
            if b["type"] == "text":
                b["text"] += e[2]["text"]
            else:
                b["thinking"] += e[2]["thinking"]
    out = [blocks[i] for i in sorted(blocks)]
    for b in out:
        if b["type"] == "thinking":
            b["signature"] = ""
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
