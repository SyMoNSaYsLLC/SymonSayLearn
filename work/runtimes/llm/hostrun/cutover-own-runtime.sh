#!/usr/bin/env bash
# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright 2026 SymonSaysLLC
# SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
#
# cutover-own-runtime — put the estate's OWN chat runtime on 8802 in place of the substitution
# engine, prove it through the gateway, and restore automatically if any probe fails.
#
#   SYM_CHAT_TOKEN=<the chat unit's bearer> work/runtimes/llm/hostrun/cutover-own-runtime.sh
#
# The token is the unit's own credential (rules R13: agents never generate one). It must be in
# the environment when this runs; it is never printed, logged or written by this script.
#
# What runs: symoneural-llm serve (the stdlib gateway over libsymoneural-llm, the CUDA backend
# module loaded) with the GGUF registry, every layer on the GPU, 16k context, the channel prompt
# style. Then the /v1 gateway on 9001 is restarted with SYM_CHAT_WORKER_MODEL=symon-chat and the
# same token so it can reach the unit. Probes: direct and through the gateway, non-streaming
# and streaming; then the benchmark. On any failure: the runtime is stopped, the substitution
# engine's bring-up ladder is run, and the gateway is restarted without the override.
set -o pipefail
[ -n "$SYM_CHAT_TOKEN" ] || { echo "SYM_CHAT_TOKEN is not in the environment; refusing (the unit would refuse too)" >&2; exit 78; }
REPO=${SYMON_REPO:-/home/google/symonsaylearn}; RUN=${SYM_RUN_DIR:-$HOME/symoneural-run}; mkdir -p "$RUN/logs"
STAGE=${SYM_LLM_STAGE:-/home/google/symoneural-release/v1.0.0/symoneural-llm-native/x86_64}
REG=${SYM_LLM_REGISTRY_ROOT:-$HOME/symoneural-models/registry}; KEY=${SYM_GW_KEY_FILE:-$HOME/.config/symoneural/gateway-9001.key}
TS=$(date +%Y%m%d-%H%M%S); LOG=$RUN/logs/cutover-own-$TS.log; exec > >(tee -a "$LOG") 2>&1
echo "=== $(date -Is) CUTOVER to the estate's own runtime (log $LOG) ==="
[ -f "$REG/symon-chat.gguf" ] || { echo "no $REG/symon-chat.gguf"; exit 2; }
[ -f "$STAGE/lib/libsymoneural-llm.so.1.1.1" ] && [ -f "$STAGE/lib/ggml/libggml-cuda.so" ] || { echo "stage libraries missing under $STAGE"; exit 2; }
OLD=$(ss -ltnp | grep -E ':8802 ' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); GP=$(ss -ltnp | grep -E ':9001 ' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
GCWD=$(readlink /proc/$GP/cwd); mapfile -d '' GENV < /proc/$GP/environ
GENV_CLEAN=(); for kv in "${GENV[@]}"; do case "$kv" in SYM_CHAT_WORKER_MODEL=*|SYM_CHAT_TOKEN=*) ;; *) GENV_CLEAN+=("$kv");; esac; done
echo "substitution engine pid ${OLD:-none}; gateway pid $GP (cwd $GCWD)"
start_gateway() { local p; p=$(ss -ltnp | grep -E ':9001 ' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); [ -n "$p" ] && { kill "$p"; for i in $(seq 1 20); do ss -ltn | grep -q ':9001 ' || break; sleep 0.5; done; }
  ( cd "$GCWD" && env -i "${GENV_CLEAN[@]}" "$@" nohup python3 -m symoneural_api.gateway >> "$RUN/logs/gateway.log" 2>&1 & )
  for i in $(seq 1 40); do curl -sf -o /dev/null http://127.0.0.1:9001/health && return 0; sleep 0.5; done; echo "gateway did not come up"; return 1; }
restore() { echo "=== $(date -Is) RESTORE: $1 ==="; [ -n "$EPID" ] && kill "$EPID" 2>/dev/null; sleep 2
  PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True SYM_GPU_FRACTION=0.917 SYM_MAX_MODEL_LEN=16384 SYM_CPU_OFFLOAD_GB=3 nohup "$REPO/work/runtimes/llm/hostrun/bringup-chat-unit.sh" > "$RUN/logs/restore-bringup-$TS.log" 2>&1 &
  start_gateway; for i in $(seq 1 120); do curl -sf -o /dev/null http://127.0.0.1:8802/v1/models && { echo "substitution engine restored after ${i}x5s"; exit 2; }; sleep 5; done; echo "RESTORE FAILED"; exit 3; }
echo "--- 1. stop the substitution engine ---"; [ -n "$OLD" ] && { kill "$OLD"; for i in $(seq 1 30); do ss -ltn | grep -q ':8802 ' || break; sleep 1; done; ss -ltn | grep -q ':8802 ' && { kill -9 "$OLD"; sleep 3; }; }
for i in $(seq 1 30); do [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)" -lt 2000 ] && break; sleep 1; done; echo "GPU after stop: $(nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader)"
echo "--- 2. start the estate's own runtime on 8802 ---"; S=$(date +%s)
( cd "$REPO/work/runtimes/llm/app" && SYM_LLM_NATIVE=$STAGE/lib/libsymoneural-llm.so.1.1.1 LD_LIBRARY_PATH=$STAGE/lib GGML_BACKEND_PATH=$STAGE/lib/ggml/libggml-cuda.so \
  SYM_LLM_REGISTRY_ROOT=$REG SYM_LLM_PROMPT_STYLE=${SYM_LLM_PROMPT_STYLE:-channels} SYM_LLM_REASONING=${SYM_LLM_REASONING:-medium} \
  nohup python3 -m symoneural_llm.main serve --host 127.0.0.1 --port 8802 --gpu-layers -1 --n-ctx "${SYM_MAX_MODEL_LEN:-16384}" --threads 8 --allowed-models symon-chat > "$RUN/logs/own-runtime-$TS.log" 2>&1 & echo $! > "$RUN/own-runtime.pid" )
EPID=$(cat "$RUN/own-runtime.pid")
for i in $(seq 1 60); do kill -0 "$EPID" 2>/dev/null || { echo "runtime exited:"; tail -20 "$RUN/logs/own-runtime-$TS.log"; restore "runtime exited"; }; curl -sf -o /dev/null http://127.0.0.1:8802/api/health && break; sleep 2; done
curl -sf -o /dev/null http://127.0.0.1:8802/api/health || { tail -20 "$RUN/logs/own-runtime-$TS.log"; restore "no health"; }
echo "runtime up after $(( $(date +%s)-S )) s; GPU: $(nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader)"
echo "--- 3. direct probes (bearer from the environment) ---"
curl -s -H "Authorization: Bearer $SYM_CHAT_TOKEN" http://127.0.0.1:8802/v1/models | python3 -c 'import sys,json; print("models:", [m.get("id") for m in json.load(sys.stdin).get("data",[])])'
curl -s -o "$RUN/logs/own-direct-$TS.json" -w 'direct /v1/messages %{http_code} in %{time_total}s\n' -H "Authorization: Bearer $SYM_CHAT_TOKEN" -H 'content-type: application/json' -d '{"model":"symon-chat","max_tokens":96,"messages":[{"role":"user","content":"In one sentence, what is the capital of France?"}]}' http://127.0.0.1:8802/v1/messages
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print("  stop:", d.get("stop_reason"), "| usage:", d.get("usage")); [print("  ", b["type"], "->", (b.get("text") or b.get("thinking") or "")[:200].replace("\n"," ")) for b in d.get("content",[])]' "$RUN/logs/own-direct-$TS.json" || restore "direct probe unreadable"
grep -q '"type": *"text"' "$RUN/logs/own-direct-$TS.json" || { echo "no text block in the direct answer"; restore "direct probe failed"; }
echo "--- 4. gateway restart with the override and the bearer ---"; start_gateway SYM_CHAT_WORKER_MODEL=symon-chat SYM_CHAT_TOKEN="$SYM_CHAT_TOKEN" || restore "gateway restart failed"
gc=$(curl -s -o "$RUN/logs/own-gw-$TS.json" -w '%{http_code}' -H "x-api-key: $(cat "$KEY")" -H 'content-type: application/json' -d '{"model":"symon-chat","max_tokens":96,"messages":[{"role":"user","content":"In one sentence, what are you?"}]}' http://127.0.0.1:9001/v1/messages)
echo "gateway /v1/messages -> $gc"; python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print("  model:", d.get("model"), "| stop:", d.get("stop_reason")); [print("  ", b["type"], "->", (b.get("text") or b.get("thinking") or "")[:200].replace("\n"," ")) for b in d.get("content",[])]' "$RUN/logs/own-gw-$TS.json"
gs=$(curl -sN -H "x-api-key: $(cat "$KEY")" -H 'content-type: application/json' -d '{"model":"symon-chat","max_tokens":48,"stream":true,"messages":[{"role":"user","content":"Count to three."}]}' http://127.0.0.1:9001/v1/messages | grep '^event:' | sort | uniq -c | tr '\n' ';'); echo "gateway streaming events: $gs"
[ "$gc" = 200 ] || restore "gateway probe failed"
echo "--- 5. bench through the gateway, 20 s, 2 workers ---"; /home/google/symoneural-learn/tools/bench-gateway.sh --duration 20s --workers 2 --max-tokens 64 --out "$REPO/production/bench" --quiet 2>&1 | tail -8
echo "GPU at end: $(nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader)"
echo "=== $(date -Is) CUTOVER HOLDS: the estate's own runtime (pid $EPID) serves 8802; gateway on 9001 points at it. Restore: kill \$(cat $RUN/own-runtime.pid); PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True SYM_GPU_FRACTION=0.917 SYM_MAX_MODEL_LEN=16384 SYM_CPU_OFFLOAD_GB=3 $REPO/work/runtimes/llm/hostrun/bringup-chat-unit.sh; then restart the gateway without SYM_CHAT_WORKER_MODEL/SYM_CHAT_TOKEN ==="
