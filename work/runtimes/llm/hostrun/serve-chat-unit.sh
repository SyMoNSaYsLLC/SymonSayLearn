#!/bin/bash
# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright 2026 SymonSaysLLC
# SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
# Serve the `chat` unit (units.REGISTRY["chat"], Resource.GPU, 127.0.0.1:8802).
#
# WHAT THIS IS, STATED PLAINLY
# ----------------------------
# The product is the estate's own runtime. This script is a HOST STAND-IN: it runs
# an ACQUIRED upstream engine from a host virtualenv so the gateway and the client
# contract can be exercised today. It is not `symoneural-llm`, and nothing in the
# estate should describe it as such.
#
# The two estate paths to a serving chat unit are both blocked right now, which is
# why the stand-in exists. Recorded rather than worked around (Section 3.8):
#
#   symoneural-llama-cpp   builds library-only. Its own CMakeCache carries
#                          LLAMA_BUILD_SERVER:BOOL=OFF, so no server binary is
#                          produced and none exists anywhere on this host.
#   symoneural-vllm        the recipe runs to do_compile and stops: no do_install,
#                          no do_package, no ipk in any deploy directory.
#
# Replacing this script with the estate's own build is the next phase. Until it is
# done, every report that cites this unit names the engine that actually answered.
#
# MEASURED CONSTRAINT
# -------------------
# One card, 15.56 GiB visible to the runtime, of which the desktop compositor holds
# ~1.3 GiB. Weights are 12.82 GiB. A first attempt at 0.93 utilisation was refused:
#   "Free memory on device cuda:0 (14.23/15.56 GiB) on startup is less than desired
#    GPU memory utilization (0.93, 14.47 GiB)"
# 0.90 asks for 14.00 GiB and fits. Raising it again requires freeing the card, not
# editing this number.
set -u

ENGINE_VENV=${SYM_CHAT_ENGINE_VENV:-$HOME/.venvs/vllm-0271-cu130}
MODELS_DIR=${SYM_MODELS_DIR:-$HOME/symoneural-models}
MODEL_DIR=${SYM_CHAT_MODEL_DIR:-$MODELS_DIR/symon-chat}
SERVED_NAME=${SYM_CHAT_SERVED_NAME:-symon-ai}
PORT=${SYM_CHAT_PORT:-8802}
RUN_DIR=${SYM_RUN_DIR:-$HOME/symoneural-run}
LOG=$RUN_DIR/logs/chat-unit.log

mkdir -p "$RUN_DIR/logs"
: > "$LOG"
{
  echo "=== $(date -Is) chat unit starting ==="
  echo "engine venv : $ENGINE_VENV   (ACQUIRED UPSTREAM, host stand-in)"
  echo "model dir   : $MODEL_DIR"
  echo "served name : $SERVED_NAME"
  echo "bind        : 127.0.0.1:$PORT"
  "$ENGINE_VENV/bin/vllm" --version
} >> "$LOG" 2>&1

# Optional: hold part of the weight set in host RAM. Set only when the card cannot
# fit the load-time peak; it costs PCIe traffic on every token, so it is never a
# default. bringup-chat-unit.sh reaches for this last, and records that it did.
OFFLOAD=()
if [ -n "${SYM_CPU_OFFLOAD_GB:-}" ] && [ "${SYM_CPU_OFFLOAD_GB}" != "0" ]; then
  OFFLOAD=(--cpu-offload-gb "$SYM_CPU_OFFLOAD_GB")
  echo "cpu offload : ${SYM_CPU_OFFLOAD_GB} GiB to host RAM" >> "$LOG"
fi

# No --api-key: this unit binds loopback and the gateway on 9001 is the only thing
# that talks to it. One trust boundary, one credential; a second key here would be
# another copy of the same secret with its own way of going stale.
exec "$ENGINE_VENV/bin/vllm" serve "$MODEL_DIR" \
  --served-model-name "$SERVED_NAME" \
  --host 127.0.0.1 --port "$PORT" \
  --max-model-len "${SYM_MAX_MODEL_LEN:-16384}" \
  --gpu-memory-utilization "${SYM_GPU_FRACTION:-0.90}" \
  --max-num-seqs "${SYM_MAX_SEQS:-4}" \
  "${OFFLOAD[@]}" \
  --enforce-eager \
  --disable-log-stats \
  --uvicorn-log-level info >> "$LOG" 2>&1
