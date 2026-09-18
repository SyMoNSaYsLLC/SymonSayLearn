#!/usr/bin/env bash
# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright 2026 SymonSaysLLC
# SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
#
# verify-3p-path — exercise everything a third-party client does, before anyone opens one.
#
#   work/tools/verify-3p-path.sh [--gateway http://127.0.0.1:9001]
#
# Every check prints PASS or FAIL with the evidence that decided it, and the script
# exits non-zero on the first category that fails. No secret is printed: the key is
# read into a variable from its 0600 file and only ever sent in a header.
#
# WHY THESE CHECKS AND NOT A SMOKE TEST
# -------------------------------------
# On 2026-09-18 the request path worked perfectly while the client offered nothing at
# all: rows were discovered and then dropped because a model id must satisfy the
# client's own naming rule. A test that only asks "did a message come back" would have
# passed all day. So the id rule is asserted here explicitly, as are the streaming
# event order and the error envelope, which a plain request never exercises.
set -o pipefail

GW=${1:-http://127.0.0.1:9001}
[ "$GW" = "--gateway" ] && GW=$2
KEY_FILE=${SYM_GW_KEY_FILE:-$HOME/.config/symoneural/gateway-9001.key}
FAILS=0
pass() { printf '  PASS  %s\n' "$*"; }
fail() { printf '  FAIL  %s\n' "$*"; FAILS=$((FAILS+1)); }
hdr()  { printf '\n== %s\n' "$*"; }

[ -r "$KEY_FILE" ] || { echo "no credential at $KEY_FILE"; exit 78; }
KEY=$(tr -d '\r\n' < "$KEY_FILE")
AUTH=(-H "Authorization: Bearer $KEY" -H "anthropic-version: 2023-06-01" -H "content-type: application/json")

hdr "1. liveness"
code=$(curl -s -o /dev/null -w '%{http_code}' -m 5 "$GW/health"); rc=$?
[ "$rc" -eq 0 ] && [ "$code" = 200 ] && pass "/health 200" || fail "/health rc=$rc code=$code"
code=$(curl -s -o /dev/null -w '%{http_code}' -m 10 "${AUTH[@]}" "$GW/ready"); rc=$?
[ "$code" = 200 ] && pass "/ready 200 (worker reachable)" || fail "/ready code=$code — the gateway cannot reach the chat unit"

hdr "2. authentication"
code=$(curl -s -o /dev/null -w '%{http_code}' -m 5 "$GW/v1/models")
[ "$code" = 401 ] && pass "unauthenticated /v1/models is 401" || fail "unauthenticated /v1/models returned $code, expected 401"
code=$(curl -s -o /dev/null -w '%{http_code}' -m 5 -H "Authorization: Bearer not-the-key" "$GW/v1/models")
[ "$code" = 401 ] && pass "a wrong bearer is 401" || fail "wrong bearer returned $code"
code=$(curl -s -o /dev/null -w '%{http_code}' -m 5 -H "x-api-key: $KEY" "$GW/v1/models")
[ "$code" = 200 ] && pass "x-api-key is accepted as well as bearer" || fail "x-api-key returned $code"

hdr "3. model rows satisfy the client's naming rule"
curl -s -m 8 "${AUTH[@]}" "$GW/v1/models" > /tmp/.m.$$ 2>/dev/null
python3 -I - /tmp/.m.$$ <<'PY'
import json, re, sys
d = json.load(open(sys.argv[1]))
rows = d.get("data", [])
# Measured from the reference client bundle 2026-09-18.
BLOCK = re.compile(r"ark-code|astron|command-r|deepseek|doubao|gemini|gemma|glm|gpt|grok|hermes|kimi|llama|minimax|mistral|mixtral|moonshot|nemotron|openai|phi-|qwen|yi-|stepfun|seed-|bytedance|hunyuan|granite|nova-|devstral|ministral|ernie|codex|arcee|jamba|arctic|solar|mercury|zamba")
TIERS = ["sonnet","opus","haiku","fable","mythos"]
EXACT = re.compile(r"^(%s)(-[\d.]+)?$" % "|".join(TIERS))
CONTAINS = ["claude"] + TIERS + ["anthropic"]
ok = True
def chk(c, msg):
    global ok
    print(("  PASS  " if c else "  FAIL  ") + msg)
    if not c: ok = False
chk(len(rows) == 4, f"four model rows ({len(rows)})")  # chat, code, cowork and the background tier a client resolves for itself
seen_default = {}
for r in rows:
    i = r.get("id",""); lo = i.lower()
    offered = (not BLOCK.search(lo)) and (bool(EXACT.match(lo)) or any(m in lo for m in CONTAINS))
    chk(offered, f"{i}: passes the client's id rule")
    chk(r.get("anthropic_family_tier") in TIERS, f"{i}: tier {r.get('anthropic_family_tier')!r} is a real tier")
    chk(bool(r.get("display_name")), f"{i}: has a display name ({r.get('display_name')!r})")
    chk(r.get("type") == "model", f"{i}: type is 'model'")
    if r.get("is_family_default"):
        t = r["anthropic_family_tier"]
        chk(t not in seen_default, f"{i}: sole default for tier {t}")
        seen_default[t] = i
sys.exit(0 if ok else 1)
PY
[ $? -eq 0 ] || FAILS=$((FAILS+1))

hdr "4. a real completion on every model, plus the legacy aliases"
# The reply is parsed by a real file, not an inline -c string: backslash escaping
# inside a single-quoted shell string silently produced a Python SyntaxError here,
# which 2>/dev/null then swallowed, so every model reported an empty result while the
# path was in fact healthy. A test that can fail silently is worse than no test.
cat > /tmp/.chk.$$.py <<'PY'
import json, sys
try:
    d = json.load(sys.stdin)
except Exception as e:
    print("UNPARSEABLE:", e); raise SystemExit(1)
if d.get("type") == "error":
    print("ERROR:", d.get("error", {}).get("message", "")[:80]); raise SystemExit(1)
txt = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text").strip()
think = any(b.get("type") == "thinking" for b in d.get("content", []))
if not txt:
    print("NO-TEXT-BLOCK types=%s" % [b.get("type") for b in d.get("content", [])]); raise SystemExit(1)
u = d.get("usage", {})
print("model=%s stop=%s thinking=%s in=%s out=%s text=%r"
      % (d.get("model"), d.get("stop_reason"), think,
         u.get("input_tokens"), u.get("output_tokens"), txt[:40]))
PY
for m in symon-sonnet symon-opus symon-fable symon-haiku symon-chat symon-coder symon-work; do
  out=$(curl -s -m 300 -X POST "${AUTH[@]}" "$GW/v1/messages" \
        -d "{\"model\":\"$m\",\"max_tokens\":64,\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly: READY\"}]}")
  got=$(printf '%s' "$out" | python3 -I /tmp/.chk.$$.py 2>&1); rc=$?
  if [ $rc -eq 0 ]; then pass "$m -> $got"; else fail "$m -> $got"; fi
done
rm -f /tmp/.chk.$$.py

hdr "5. streaming event order"
curl -s -N -m 180 -X POST "${AUTH[@]}" "$GW/v1/messages" \
  -d '{"model":"symon-sonnet","max_tokens":48,"stream":true,"messages":[{"role":"user","content":"Count: one two three"}]}' \
  > /tmp/.s.$$ 2>/dev/null
python3 -I - /tmp/.s.$$ <<'PY'
import sys, re
ev = [l.split(":",1)[1].strip() for l in open(sys.argv[1]) if l.startswith("event:")]
ok = True
def chk(c,msg):
    global ok
    print(("  PASS  " if c else "  FAIL  ")+msg)
    if not c: ok=False
chk(bool(ev), f"stream produced events ({len(ev)})")
if ev:
    chk(ev[0]=="message_start", f"first event is message_start (got {ev[0]})")
    chk(ev[-1]=="message_stop", f"last event is message_stop (got {ev[-1]})")
    for need in ("content_block_start","content_block_delta","content_block_stop","message_delta"):
        chk(need in ev, f"stream contains {need}")
    starts, stops = ev.count("content_block_start"), ev.count("content_block_stop")
    chk(starts==stops, f"content blocks balanced ({starts} start / {stops} stop)")
sys.exit(0 if ok else 1)
PY
[ $? -eq 0 ] || FAILS=$((FAILS+1))

hdr "6. token counting"
n=$(curl -s -m 30 -X POST "${AUTH[@]}" "$GW/v1/messages/count_tokens" \
    -d '{"model":"symon-sonnet","messages":[{"role":"user","content":"hello there"}]}' \
    | python3 -I -c 'import json,sys; print(json.load(sys.stdin).get("input_tokens","none"))' 2>/dev/null)
case "$n" in ''|none|0) fail "count_tokens returned $n";; *) pass "count_tokens -> $n input tokens";; esac

hdr "7. error envelope"
body=$(curl -s -m 10 -X POST "${AUTH[@]}" "$GW/v1/messages" \
       -d '{"model":"no-such-model","max_tokens":8,"messages":[{"role":"user","content":"x"}]}')
printf '%s' "$body" | python3 -I -c 'import json,sys
d=json.load(sys.stdin)
assert d.get("type")=="error", d
assert isinstance(d.get("error"),dict) and d["error"].get("type") and d["error"].get("message"), d
print("  PASS  unknown model -> {type:error, error:{type:%s}}" % d["error"]["type"])' 2>/dev/null || fail "unknown model did not return a dialect error envelope: $(printf '%s' "$body" | head -c 120)"

hdr "8. credential helper"
H=/usr/local/libexec/symoneural-gateway-credential
if [ -x "$H" ]; then
  bytes=$("$H" | wc -c); lines=$("$H" | wc -l)
  [ "$bytes" -gt 0 ] && pass "helper emits $bytes bytes" || fail "helper emitted nothing"
  [ "$lines" -eq 0 ] && pass "helper output is a single line with no trailing newline" || fail "helper emitted $lines newlines; the client rejects multi-line output"
  "$H" | grep -qE '^[A-Za-z0-9._~+/-]+$' && pass "helper output is a bare token" || fail "helper output is not a bare token"
else
  fail "helper missing at $H"
fi

rm -f /tmp/.m.$$ /tmp/.s.$$
hdr "result"
if [ "$FAILS" -eq 0 ]; then echo "  ALL CHECKS PASSED"; exit 0; else echo "  $FAILS CHECK GROUP(S) FAILED"; exit 1; fi
