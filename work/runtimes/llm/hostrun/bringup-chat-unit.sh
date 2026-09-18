#!/bin/bash
# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright 2026 SymonSaysLLC
# SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
# Bring the `chat` unit up, trying known-good configurations in order and recording
# which one actually served. Stops at the first success.
#
# WHY THIS IS A LADDER AND NOT ONE COMMAND
# ---------------------------------------
# MEASURED on this host, 2026-09-18: the checkpoint is MXFP4 MoE and this card is
# compute capability 12.0 (SM120). vLLM 0.27.1 excludes SM120 from its Triton MoE
# path by an explicit range check in
# fused_moe/experts/gpt_oss_triton_kernels_moe.py:
#
#     # covers Hopper SM90 and Blackwell SM100, excludes SM120
#     return cap is not None and (9, 0) <= (cap.major, cap.minor) < (11, 0)
#
# so the only remaining path is Marlin, which REPACKS the MoE weights into its own
# kernel format during process_weights_after_loading. That repack peaks above the
# 12.82 GiB checkpoint. Attempt 1 at utilisation 0.93 was refused before loading;
# attempt 2 at 0.90 died inside _repack_marlin_experts with:
#
#     torch.OutOfMemoryError: Tried to allocate 276.00 MiB.
#     GPU 0 has ... 273.62 MiB is free.
#
# Short by 2.4 MiB. A miss that small is fragmentation, not a real shortfall, which
# is why the first rung only changes the allocator. Each later rung gives up
# something real, so they are ordered by what they cost.
set -u

RUN_DIR=${SYM_RUN_DIR:-/home/google/symoneural-run}
LOG=$RUN_DIR/logs/chat-unit.log
LADDER_LOG=$RUN_DIR/logs/chat-unit-bringup.log
PORT=${SYM_CHAT_PORT:-8802}
LAUNCH=$(dirname -- "${BASH_SOURCE[0]}")/serve-chat-unit.sh
mkdir -p "$RUN_DIR/logs"

note() { echo "$(date -Is) $*" | tee -a "$LADDER_LOG"; }

stop_unit() {
  pkill -f 'vllm serve' 2>/dev/null
  for _ in $(seq 1 20); do pgrep -f 'vllm serve' >/dev/null || break; sleep 1; done
  pkill -9 -f 'vllm serve' 2>/dev/null
  sleep 2
}

# Success is the unit answering on its port, not the log containing a hopeful line.
#
# The grace period is not padding. The launcher runs `vllm --version` before it
# execs `vllm serve`, and during those seconds NOTHING matches the `vllm serve`
# pattern. An earlier version of this function used pgrep as an immediate failure
# condition and killed a rung five seconds in, while the engine was still starting —
# it went on to load the model successfully 36 seconds after being recorded as
# failed. A liveness probe that fires before the thing can be alive measures its own
# timing, not the service.
GRACE_S=${SYM_BRINGUP_GRACE:-120}

wait_for_unit() {
  local started=$SECONDS
  local deadline=$((SECONDS + ${1:-900}))
  while [ $SECONDS -lt $deadline ]; do
    if curl -fsS -m 3 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then return 0; fi
    # A fatal marker in the log is definitive at any time.
    grep -qE 'OutOfMemoryError|EngineCore failed to start|ValueError: Free memory|Engine core initialization failed' "$LOG" 2>/dev/null && return 1
    # Absence of the process only means failure once it has had time to appear.
    if [ $((SECONDS - started)) -gt $GRACE_S ] && ! pgrep -f 'vllm serve' >/dev/null; then
      return 1
    fi
    sleep 5
  done
  return 1
}

attempt() {
  local name=$1; shift
  note "RUNG $name: $*"
  stop_unit
  env "$@" setsid nohup "$LAUNCH" >/dev/null 2>&1 </dev/null &
  sleep 5
  if wait_for_unit 600; then
    note "RUNG $name: SERVING on 127.0.0.1:$PORT"
    note "RUNG $name: settings -> $*"
    nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader | tee -a "$LADDER_LOG"
    return 0
  fi
  note "RUNG $name: FAILED"
  grep -m1 -E 'OutOfMemoryError|ValueError: Free memory' "$LOG" 2>/dev/null | tee -a "$LADDER_LOG"
  return 1
}

: > "$LADDER_LOG"
note "=== chat unit bring-up ladder ==="

# Rung 1 — costs nothing. expandable_segments stops the allocator from stranding
# memory in fixed-size segments, which is what a 2.4 MiB miss looks like.
attempt 1-expandable \
  PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  SYM_GPU_FRACTION=0.917 SYM_MAX_MODEL_LEN=16384 && exit 0

# Rung 2 — costs context. A smaller window frees KV pool, which is not where the
# repack failed, but it lowers total pressure.
attempt 2-shorter-context \
  PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  SYM_GPU_FRACTION=0.917 SYM_MAX_MODEL_LEN=8192 && exit 0

# Rung 3 — costs throughput. Holds part of the weight set in host RAM (85 GiB free)
# so the Marlin repack has room on the card. This one is expected to work; it is
# last because every token then crosses PCIe.
attempt 3-cpu-offload \
  PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  SYM_GPU_FRACTION=0.917 SYM_MAX_MODEL_LEN=16384 SYM_CPU_OFFLOAD_GB=3 && exit 0

note "ALL RUNGS FAILED — the chat unit did not serve. See $LOG"
exit 1
