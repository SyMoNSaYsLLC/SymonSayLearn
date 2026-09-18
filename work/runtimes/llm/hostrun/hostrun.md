# hostrun

Scripts that bring the `chat` unit up **on this host**, outside BitBake.

## What this directory is, stated plainly

The product is the estate's own runtime. These scripts run an **acquired upstream
engine from a host virtualenv**. That is a stand-in, recorded under rules Section
3.10, and nothing here may be reported as `symoneural-llm`.

The stand-in exists because both estate paths to a serving chat unit are blocked.
Read from disk, not from recollection:

| Path | Blocking condition |
|---|---|
| `symoneural-llama-cpp` | its own `build/CMakeCache.txt` carries `LLAMA_BUILD_SERVER:BOOL=OFF`. The recipe is library-only; no server binary exists anywhere on this host. |
| `symoneural-vllm` | the recipe stops after `do_compile` — no `do_install`, no `do_package`, no ipk in any deploy directory. |

Replacing this directory with an estate build is the next phase, and the gateway is
written so the cutover is a change of one address: `worker.py` reads `SYM_CHAT_URL`
and nothing above it knows which engine answers.

## Files

| File | Role |
|---|---|
| `serve-chat-unit.sh` | starts one engine on `127.0.0.1:8802` with a given configuration |
| `bringup-chat-unit.sh` | tries configurations in order until one actually serves, and records which |

## Interfaces

| Direction | What |
|---|---|
| Serves | `127.0.0.1:8802` — the `chat` unit's registered port (`units.REGISTRY["chat"]`) |
| Reads | `${SYM_MODELS_DIR:-$HOME/symoneural-models}/symon-chat` |
| Writes | `${SYM_RUN_DIR:-$HOME/symoneural-run}/logs/chat-unit.log`, `chat-unit-bringup.log` |
| Consumed by | `work/runtimes/api/app/symoneural_api/worker.py`, via `SYM_CHAT_URL` |

**No credential.** The unit binds loopback and carries no key. The gateway on 9001
authenticates callers. One trust boundary, one secret; a second key here would be
another copy of the same value with its own way of going stale.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `SYM_CHAT_ENGINE_VENV` | `$HOME/.venvs/vllm-0271-cu130` | the acquired engine |
| `SYM_MODELS_DIR` | `$HOME/symoneural-models` | weight store |
| `SYM_CHAT_PORT` | `8802` | bind port |
| `SYM_CHAT_SERVED_NAME` | `symon-ai` | the engine-side model name |
| `SYM_MAX_MODEL_LEN` | `16384` | served context window; `models.py` must agree |
| `SYM_GPU_FRACTION` | `0.90` | fraction of the card the engine may claim |
| `SYM_MAX_SEQS` | `4` | concurrent sequences |
| `SYM_CPU_OFFLOAD_GB` | unset | GiB of weights held in host RAM. Costs PCIe traffic per token; never a default |

## Why bring-up is a ladder and not one command

MEASURED on this host, 2026-09-18:

The checkpoint is MXFP4 mixture-of-experts and this card is compute capability 12.0
(SM120). The engine excludes SM120 from its Triton MoE path by an explicit range
check in `fused_moe/experts/gpt_oss_triton_kernels_moe.py`: the gate admits a compute
capability of at least 9.0 and below 11.0 — SM90 and SM100 — and nothing else, so
SM120 falls outside it. (Stated in our words; the engine's source is not quoted here.)

So installing `triton_kernels` does not help — the gate is the capability, not the
module. The only remaining path is Marlin, which **repacks** the MoE weights into its
own kernel format during `process_weights_after_loading`, and that repack peaks above
the 12.82 GiB checkpoint.

Attempts, in order:

| Utilisation | Context | Offload | Result |
|---|---|---|---|
| 0.93 | 16384 | — | refused before loading: free 14.23 GiB < requested 14.47 GiB |
| 0.90 | 16384 | — | OOM inside `_repack_marlin_experts`, short by 2.4 MiB |
| 0.917 + `expandable_segments` | 16384 | — | OOM |
| 0.917 + `expandable_segments` | 8192 | — | OOM, short by 1.6 MiB |
| 0.917 + `expandable_segments` | 16384 | 3 GiB | weights loaded: "Model loading took 10.5 GiB" |

A miss of 2.4 MiB is fragmentation, not a shortfall, which is why the ladder's first
rung only changes the allocator and costs nothing. Each later rung gives up something
real, so they are ordered by what they cost: allocator, then context, then throughput.

## A bug this directory paid for

The ladder's original liveness check used `pgrep -f 'vllm serve'` as an immediate
failure condition after a 5-second sleep. `serve-chat-unit.sh` runs the engine's
`--version` first, and during those seconds **nothing matches that pattern**. The
ladder recorded a rung as FAILED five seconds in, while that rung went on to load the
model successfully 36 seconds later. The fix is a grace period before absence counts
as failure. A liveness probe that fires before the thing can be alive is measuring
its own timing, not the service.

Related, and it cost a second run: `pkill -f 'vllm serve'` typed at an interactive
shell matches **that shell's own command line**, because the pattern is in it. Use
`pkill -f '[v]llm serve'`.

## Onward

The gateway that consumes this unit is documented in
`work/runtimes/api/app/symoneural_api/symoneural_api.md`. Read that next; it holds
the endpoint register and the credential model.
