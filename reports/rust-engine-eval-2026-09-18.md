# Rust engine evaluation — gpt-oss-20b MXFP4 on RTX 5070 Ti (sm_120, CUDA 13.4)

Workflow `wf_d9e6fea7-f03`, 2026-09-18: four evaluators from real clones, four adversarial verifiers, one synthesis. 9 agents, 290 tool calls, 48 min. Every claim below is from source read on this host; nothing was run on the GPU (held by the production chat unit).

# Rust engine decision — gpt-oss-20b (MXFP4) on RTX 5070 Ti, 2026-09-18

**Answer to the relayed question ("solution for not using the copyleft source?"):** strong copyleft is absent from all four candidates — no GPL, LGPL or AGPL obligation anywhere in any closure (the only LGPL string is r-efi's `MIT OR Apache-2.0 OR LGPL-2.1-or-later`, an OR). A *zero*-copyleft closure is not available with the recommended engine as shipped: mistral.rs carries 16 MPL-2.0 crates as hard, non-optional dependencies of the server binary (symphonia ×11 via `mistralrs-core/Cargo.toml:107`, cssparser/cssparser-macros/dtoa-short/selectors via scraper at `:92`, option-ext via directories at `mistralrs-cli/Cargo.toml:41`), and no cargo feature removes them. The two exits are (a) accept MPL-2.0 — file-level weak copyleft, unmodified use in a proprietary binary; no legal determination made here — and record the 16 crates in the licence inventory, or (b) carry a recipe patch that drops symphonia (audio decode), scraper (web search) and directories from three Cargo.tomls. (b) is adjacent work, named and not done. The only zero-copyleft *library* closure found is llama-cpp-rs (88 crates), and its engine is C++.

**Nothing is ready.** No candidate produced a binary that can serve this checkpoint on this host, and no model was loaded (GPU held by production). Every capability claim below is from source, not from a run.

Environment correction: the GPU is held at 15872–15884 MiB of 16303 (read 06:16, 06:34, 06:36), not "about 11 GiB". The holder is `vllm` pid 48888 launched with `--gpu-memory-utilization 0.917 --cpu-offload-gb 3 --max-model-len 16384 --enforce-eager` — the current engine does not hold the whole model in VRAM.

## 1. RANKING

| engine | pure Rust? | gpt-oss | MXFP4 on GPU | fits 16 GB | sm_120 + CUDA 13 | copyleft in closure | built here (rc) | server: OpenAI / Anthropic |
|---|---|---|---|---|---|---|---|---|
| **mistral.rs** 0.9.3 @ d5ae0f18 | Yes — Rust (candle); vendored `.cu` kernels, no C++ core | **Yes**, native: `GptOssForCausalLM`/`gpt_oss` → `GptOssLoader` (normal_loaders.rs:318/355/451); loads the HF safetensors directly | **Yes** by reading: `*_blocks`/`*_scales` loaded as U8 (mxfp4/mod.rs:550-588), consumed by `launch_mxfp4_*_gemm_bf16` with in-kernel LUT dequant (mod.rs:156-166, ffi.rs:76-161); bf16 dequant only on ISQ/UQFF and CPU paths | Fits by arithmetic: ~12.1 GiB resident weights, ~3.5 GiB headroom; **unexercised** | sm_120a: **yes**, proven on disk (`cuobjdump` → `sm_120a.cubin` in paged-attn .o). CUDA 13.0–13.3 only; **13.4 REJECTED** by cudarc-0.19.9/build.rs:182 (env override exists) and mistralrs-quant/build.rs:109 (no override) | 16 MPL-2.0 hard deps; 0 GPL/LGPL/AGPL; 743 crates, no unknowns | **101** both attempts (201 s, 951 s); reproduced in 1 s; no binary | **Yes / Yes** — `/v1/chat/completions`, `/v1/messages`, `/v1/messages/count_tokens`, `/v1/models` (route_registry.rs:27-36, mounted router_builder.rs:375-383), SSE both dialects. `/v1/models` is OpenAI-shaped (handlers.rs:48-70) |
| **llama-cpp-rs** 0.1.157 @ 992519ec | **No** — Rust FFI over the C++ llama.cpp submodule e79e4bf6 (dated **2026-08-13**) | Yes, in C++ (llama-arch.cpp:121, openai-moe.cpp); **GGUF only**, safetensors must be converted; no GGUF exists | **Yes** (C++): mmvq `vec_dot_mxfp4_q8_1`, mmq FP4 MMA on Blackwell (mmq.cu:131); loader memcpy's raw blocks | Fits by arithmetic: ~12.8 GiB + 1–2 GiB; **unexercised**; tight at 128k | **Yes / Yes**: nvcc 13.4.92 accepted by CMake, `compute_120a,code=[sm_120a]` in flags.make; 55/186 CUDA objects compiled, full compile **not shown** | None in the 88-crate library closure; option-ext MPL-2.0 only via examples' hf-hub | **UNDEFINED** — timed out at 55/186 objects, no errors, no binary | **No / No** in Rust. C++ `llama-server` has both (server.cpp:244/250) but `LLAMA_BUILD_SERVER=OFF` (build.rs:657, CMakeCache) |
| **candle** 0.11.0 @ ddf1b879 | Yes | **No** — zero hits for gpt_oss/GptOss (grep rc=1) | **No** — `GgmlDType` has no MXFP4 (quantized/mod.rs:281-297), type 39 rejected (:318); MXFP4 CUDA templates complete but never instantiated (build.rs:31-41) | **Does not fit** — only path is bf16 expansion, ~41.8 GB | sm_120a yes (PTX `.target sm_120a`); 13.4 rejected by cudarc, built only with `CUDARC_CUDA_VERSION=13030` | 2 MPL-2.0 (colored, option-ext) solely via hf-hub; core crates clean | **0** with override (example binary `quantized`, md5 82e63638…); attempt 1 rc=101 | **No / No** — no HTTP framework in any Cargo.toml |
| **burn** 0.22.0-pre.3 @ 8f08fdad | Yes | **No** — no gpt-oss/MoE/CausalLM code (grep rc=1) | **Unknown** — E2M1+UE8M0 block-32 QuantScheme exists (quantization.rs:755) and the matmul binds packed data+scales (matmul/base.rs:128-190), but burn-store has no MXFP4 load route | **Unknown** — no code path | sm_120a via runtime NVRTC (context.rs:207-211); 13.4 rejected by cudarc; with override cudarc+cubecl-cuda compile, final link **unverified** | 3 MPL-2.0: colored (feature-gated by `std`, present in every default build — evaluator's "unconditional" **REFUTED**), buildid (unconditional in cubecl-runtime), attohttpc (via iroh, default feature) | **101**; retry killed → **UNKNOWN** | **No / No** — WebSocket tensor backend only (`/session`, `/data`) |

## 2. WHAT BREAKS FIRST

- **mistral.rs**: `thread 'main' panicked at mistralrs-quant/build.rs:109:9: Unsupported cuda toolkit version: 13.4` — a 4-entry allowlist (`(13, 3), (13, 2), (13, 1), (13, 0), …` at build.rs:12-16) with no env override, hit after cudarc's own allowlist is bypassed with `CUDARC_CUDA_VERSION=13030`. crates.io cudarc is still 0.19.9 (checked 06:35), so no upstream release fixes it. Nothing else stops it on paper; residual unknowns are all "never run" (section 6).
- **llama-cpp-rs**: the pinned llama.cpp submodule e79e4bf660e19f2ad851e06c6913f7a8c5852621 is dated 2026-08-13 08:38:02 +0200 — August 2026, which the rules forbid outright. Behind that: the model, loader and kernels are C++, so it fails "Rust for the LLM engine" by construction, and it ships no server.
- **candle**: cannot load the checkpoint — no `GptOss` model and no MXFP4 dtype on the Rust side; the U8 `*_blocks`/`*_scales` tensors would load with nothing to consume them.
- **burn**: cannot load the checkpoint — `safetensor_dtype_to_burn` maps plain dtypes only (store.rs:1053-1072), no `_blocks`/`_scales` → QFloat adapter (grep rc=1), no LLM stack at all.

## 3. RECOMMENDATION

**mistral.rs at d5ae0f18f2170f10d30880cb7d21fb0880410e7b (0.9.3, 2026-09-07), conditional on one build fix.** It is the only candidate where every requirement is already code rather than a project: native gpt-oss with the HF safetensors loaded as-is, MXFP4 experts staying 4-bit in VRAM, a built-in axum server that already speaks `/v1/messages`, `/v1/messages/count_tokens` and `/v1/models`, Harmony-format handling (`reasoning_parsers/harmony.rs`, `chat_template.rs:113 is_harmony_format`), and sm_120a codegen proven on this host. What remains is a one-line allowlist patch to `mistralrs-quant/build.rs` plus `CUDARC_CUDA_VERSION=13030`, carried as a recipe patch (never an edit to the acquired tree), and then the first actual run. The alternatives are worse in kind, not degree: candle and burn need a model, an MXFP4 kernel path and a server written from scratch, and candle cannot fit the model on today's dtypes; llama-cpp-rs pins an August-2026 submodule and is a Rust FFI over the same C++ llama.cpp core the estate already holds, so "Rust for the LLM" would mean only the API surface, not the kernels. The costs of mistral.rs are real and should be recorded before anything ships: 16 MPL-2.0 hard dependencies, a build-time CUTLASS fetch from GitHub (mistralrs-quant/build.rs:218/262 via cudaforge), `target-cpu=native` in `.cargo/config.toml`, and zero runtime evidence. If the patched build fails or the first serve does not fit in 16303 MiB, the fallback is the estate's own llama.cpp at its non-August SRCREV with `LLAMA_BUILD_SERVER=ON` and `GGML_CUDA=ON` — a C++ engine, said plainly — not any of the other three Rust trees.

## 4. THE BACKEND

Thin layer, not a gateway. mistral.rs already implements the two Anthropic POST routes with SSE and Anthropic-shaped error bodies (`is_anthropic_api_request`, router_builder.rs:466-474), so re-implementing `/v1/messages` in Rust would be duplicate work. What the estate still has to write to hold the fixed contract:

1. **Auth** — no API-key enforcement exists in mistral.rs: `mistralrs-cli/src/args/` has no key option and the router only *allows* `authorization`/`x-api-key` through CORS (router_builder.rs:361-362). The layer checks `x-api-key` / Bearer.
2. **`/v1/models` rewrite** — mistral.rs returns the OpenAI shape (`ModelObjects{object:"list", data:[{id:"default"|<model_id>, object:"model", created, owned_by:"local"}]}`, handlers.rs:48-70, openai.rs:1288-1321); the Anthropic dialect (rules §4.3) needs `type:"model"`, `display_name`, `created_at`, `max_input_tokens`, `max_tokens`, `capabilities`, and the product's model names (`symon-ai`). Pure projection, no engine change.
3. **Model-name mapping and route allow-list** — map the product's model id to mistral.rs's `default`; expose only `/v1/messages`, `/v1/messages/count_tokens`, `/v1/models`; do not forward `/ui`, `/mcp`, `/v1/files`, `/v1/images`, `/v1/audio`, `/v1/responses`, `/v1/load_lora_adapter`, `/metrics` (op-only if kept). Bind mistral.rs to `--host 127.0.0.1` (its default is `0.0.0.0`, args/server.rs:16).
4. **Engine attribution** (rules §3.10) — a response header naming the engine that answered.

Crate: **axum 0.8.x** — mistral.rs is axum 0.8.8 on hyper 1.8.1 with tower-http (Cargo.lock:327-329, mistralrs-server-core/Cargo.toml:17), and Axum is the Rust entry in the approved Backend API table, so the estate has one HTTP framework. Not hyper-direct, not actix. Fact to record, not a recommendation: today the contract is held by the Python gateway on 9001 (`python3 -m symoneural_api.gateway`; `worker.py:34 BASE_URL = os.environ.get("SYM_CHAT_URL", "http://127.0.0.1:8802")`), so cutover to a mistral.rs port is a `SYM_CHAT_URL` change with zero new Rust; replacing that gateway with axum is the Rust-backend decision under §3.8/3.9 and is Garrett's to confirm (Backend API default there is FastAPI).

## 5. ACQUISITION STEP

Written for Garrett to run as **`~/Desktop/claude/RUN-mistralrs-acquisition-2026-09-18.md`** (md5 529428f52563336dd7cc4c266382e422, 120 lines). Part A is safe now; Part B stops production and is gated. Core commands:

```sh
# A1  full clone with history (same convention as upstream/llm/wasm/wasmer), detached at the EVALUATED sha
cd /home/google/symonsaylearn && test ! -e upstream/llm/inference/mistral.rs; echo "target-free rc=$?"
git clone https://github.com/EricLBuehler/mistral.rs /home/google/symonsaylearn/upstream/llm/inference/mistral.rs; rc=$?; echo "clone rc=$rc"
cd /home/google/symonsaylearn/upstream/llm/inference/mistral.rs
git checkout --detach d5ae0f18f2170f10d30880cb7d21fb0880410e7b; rc=$?; echo "checkout rc=$rc"
# A2  record — must match the evaluated values
git rev-parse HEAD                     # d5ae0f18f2170f10d30880cb7d21fb0880410e7b
git log -1 --format='%ci %s'           # 2026-09-07 23:18:22 -0400 docs: sync OpenAPI version with v0.9.3
git describe --tags --abbrev=0         # v0.9.3 (HEAD untagged; v0.9.3 = 24dbf5c256f232176ee5949485ba264049407fbe)
test -e .gitmodules; echo "gitmodules rc=$? (1 = none)"
md5sum LICENSE                         # 2066570cad546d63de123046c2640c56
grep -n '^license\|^version' Cargo.toml   # :23 version = "0.9.3", :30 license = "MIT"
find . -path ./.git -prune -o -type f \( -iname 'LICENSE*' -o -iname 'COPYING*' -o -iname 'LICENCE*' \) -print | sort   # 8 files
# A3  pin — guarded write of work/pins/mistralrs-acquisition.json (schema symoneural-acquisition/1, wasm3 keys + wasmer's commit_date/full_history/size_on_disk)
HEAD_SHA=$(git rev-parse HEAD); LIC_MD5=$(md5sum LICENSE | cut -d' ' -f1); SIZE=$(du -sh --exclude=.git . | cut -f1)
[ "$HEAD_SHA" = d5ae0f18f2170f10d30880cb7d21fb0880410e7b ] && [ "$LIC_MD5" = 2066570cad546d63de123046c2640c56 ]; rc=$?; echo "pin-guard rc=$rc"
[ "$rc" -eq 0 ] && cat > /home/google/symonsaylearn/work/pins/mistralrs-acquisition.json <<JSON
{ "schema": "symoneural-acquisition/1", "component": "mistralrs", "runtime": "llm",
  "upstream_url": "https://github.com/EricLBuehler/mistral.rs",
  "commit_sha": "$HEAD_SHA", "commit_date": "2026-09-07 23:18:22 -0400", "tag": null, "nearest_tag": "v0.9.3", "workspace_version": "0.9.3",
  "declared_license": "MIT", "license_file": "LICENSE", "license_md5": "$LIC_MD5", "copyright": "Copyright (c) 2024 Eric Buehler",
  "acquired": "2026-09-18", "tree": "upstream/llm/inference/mistral.rs", "licence_files_in_tree": 8, "full_history": true, "size_on_disk": "$SIZE",
  "note": "<blockers: CUDA 13.4 allowlists cudarc build.rs:182 + mistralrs-quant build.rs:109; 16 MPL-2.0 hard deps; cudaforge CUTLASS fetch; target-cpu=native; unbuilt, unrun>" }
JSON
python3 -I -c 'import json; json.load(open("/home/google/symonsaylearn/work/pins/mistralrs-acquisition.json")); print("pin json valid")'
```

**The ONE test** (Part B; requires the owner's go-ahead because it stops the production chat unit — `vllm` pid 48888 on 127.0.0.1:8802, a Konsole-launched process, not a service; the gateway on 9001 fails while it is down). Build from a **copy** of the pristine tree with the one-line patch, out-of-tree target, `--locked`:

```sh
export SRC=/home/google/symonsaylearn/upstream/llm/inference/mistral.rs WORK=/home/google/.claude/jobs/e8387b40/tmp/mistralrs-test CARGO_TARGET_DIR=/home/google/.claude/jobs/e8387b40/tmp/mistralrs-target PATH=/usr/local/cuda/bin:$HOME/.cargo/bin:$PATH
mkdir -p "$WORK" "$CARGO_TARGET_DIR" && git -C "$SRC" archive --format=tar d5ae0f18f2170f10d30880cb7d21fb0880410e7b | tar -x -C "$WORK"
sed -i 's/^const SUPPORTED_CUDA_TOOLKIT_VERSIONS: &\[(usize, usize)\] = &\[$/&\n    (13, 4),/' "$WORK/mistralrs-quant/build.rs"; grep -n '(13, 4),' "$WORK/mistralrs-quant/build.rs"; echo "patched rc=$?"
cd "$WORK" && CUDARC_CUDA_VERSION=13030 cargo build --release --locked --features cuda -p mistralrs-cli > build.log 2>&1; rc=$?; echo "build rc=$rc"; ls -la "$CARGO_TARGET_DIR/release/mistralrs"
# --- GO-AHEAD REQUIRED from here ---
kill -TERM 48888; sleep 8; nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader     # expect a few hundred MiB
"$CARGO_TARGET_DIR/release/mistralrs" serve --host 127.0.0.1 -p 8899 --no-ui -m /home/google/symoneural-models/gpt-oss-20b > "$WORK/serve.log" 2>&1 &
for i in $(seq 1 120); do curl -sf -o /dev/null http://127.0.0.1:8899/health && break; sleep 5; done; echo "health rc=$?"
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader     # PASS: ~12500–16303 MiB, no OOM
curl -sS -m 600 -o "$WORK/resp.json" -w 'http=%{http_code}\n' -X POST http://127.0.0.1:8899/v1/messages -H 'content-type: application/json' -H 'anthropic-version: 2023-06-01' \
  -d '{"model":"default","max_tokens":64,"messages":[{"role":"user","content":"Reply with the single word PONG."}]}'; echo "curl rc=$?"
python3 -I -c 'import json; r=json.load(open("'"$WORK"'/resp.json")); print(r.get("type"), r.get("stop_reason"), [c.get("type") for c in r.get("content",[])])'
# PASS = http=200, type=message, non-empty text block, stop_reason present, memory.used < 16303 MiB, no panicked/OOM lines in serve.log
# then stop the test engine and restore production EXACTLY as recorded:
/home/google/.venvs/vllm-0271-cu130/bin/vllm serve /home/google/symoneural-models/gpt-oss-20b --served-model-name symon-ai --host 127.0.0.1 --port 8802 --max-model-len 16384 --gpu-memory-utilization 0.917 --max-num-seqs 4 --cpu-offload-gb 3 --enforce-eager --disable-log-stats --uvicorn-log-level info
```

Port 8899 was not listening at 06:39 (`ss -ltn | grep -c ':8899 '` → 0) and is outside the §4.10 registry.

## 6. RESIDUAL RISKS

| # | Unknown that survived verification | Command that settles it |
|---|---|---|
| 1 | The patched build has never completed; only paged-attn kernels (15 .o, sm_120a) are known to compile | Part B build: `CUDARC_CUDA_VERSION=13030 cargo build --release --locked --features cuda -p mistralrs-cli; rc=$?` → rc=0 and `ls "$CARGO_TARGET_DIR/release/mistralrs"` |
| 2 | cudarc 0.19.9 bindings believe CUDA 13.3 while libcudart/libcublas are 13.4 — ABI assumption, not verified | the serve + one request in Part B; `ldd "$CARGO_TARGET_DIR/release/mistralrs" \| grep -E 'libcuda\|libcublas\|libcudart'` |
| 3 | VRAM fit is arithmetic; the production vLLM needs `--cpu-offload-gb 3` at 0.917 utilization on the same card | `nvidia-smi --query-gpu=memory.used --format=csv,noheader -l 1` while Part B loads and answers; PASS < 16303 MiB with no OOM in `serve.log` |
| 4 | MXFP4 WMMA path selection on sm_120 at runtime (`HAVE_MXFP4_WMMA_KERNELS` is set at build; the ops.rs:545-583 dispatch is unexercised) | `RUST_LOG=debug "$CARGO_TARGET_DIR/release/mistralrs" serve … 2>&1 \| grep -i -E 'mxfp4\|wmma\|fallback'` |
| 5 | Harmony analysis/final channels → Anthropic `thinking`/`text` blocks: parser exists (`mistralrs-core/src/reasoning_parsers/harmony.rs`), mapping unverified | `python3 -I -c 'import json; print([c["type"] for c in json.load(open("resp.json"))["content"]])'` on the Part B response; then the same request with `"stream":true` |
| 6 | Offline BitBake: build fetches CUTLASS with `git clone --depth 1 --filter=blob:none --sparse` into `$CUDAFORGE_HOME/git/checkouts/cutlass-<prefix>` (cudaforge-0.1.6/src/dependency.rs:91-101, 183-191, 442-445); 743 crates need `cargo vendor` | pre-seed `CUDAFORGE_HOME`, then `unshare -n env CUDAFORGE_HOME=… CARGO_NET_OFFLINE=true cargo build --release --locked --features cuda -p mistralrs-cli; rc=$?` |
| 7 | The 16 MPL-2.0 crates are shipped unless patched out | `cargo tree -p mistralrs-cli --features cuda -e normal,build -i symphonia`, same for `scraper` and `directories`; record the 16 in `work/pins/license-inventory.json` |
| 8 | `.cargo/config.toml` `rustflags = ["-C","target-cpu=native"]` makes the binary host-specific | `RUSTFLAGS="" cargo build -v --release --locked --features cuda -p mistralrs-cli 2>&1 \| grep -c 'target-cpu=native'` → 0 |
| 9 | `/v1/models` Anthropic shape and count_tokens correctness — never called | `curl -s http://127.0.0.1:8899/v1/models`; `curl -s -X POST http://127.0.0.1:8899/v1/messages/count_tokens -H 'content-type: application/json' -H 'anthropic-version: 2023-06-01' -d '{"model":"default","messages":[{"role":"user","content":"hi"}]}'` |
| 10 | KV headroom at long context (24 layers, sliding+full alternating) untested; production runs `--max-model-len 16384` | Part B request with a ~16k-token prompt while watching `nvidia-smi … -l 1` |

**Adjacent, named, not done:** patching the three Cargo.tomls to drop the MPL-2.0 crates; a `symoneural-mistralrs` recipe (the estate already has `inherit cargo` recipes, e.g. `recipes-common/symoneural-tokenizers`, to pattern from); the axum thin layer; `upstream/llm/wasm/` and both existing pins are untracked in the symonsaylearn repo (`git status` → `?? upstream/llm/wasm/`); the ggml-derived `candle-kernels/src/mmq_gguf/` carries no upstream copyright notice (candle skeptic, OPEN).

Evidence on disk: evaluations and skeptic artefacts under `/home/google/.claude/jobs/e8387b40/tmp/eval/` (`mistralrs-build{1,2}.{log,rc}`, `skeptic2-mistralrs-build.{log,rc}`, `mistralrs-meta.json` md5 203eba7079cdb0c3fbff9498149b8351, `mistralrs-remote-tags.txt`); commands file `/home/google/Desktop/claude/RUN-mistralrs-acquisition-2026-09-18.md`. Nothing was written under `/home/google/symonsaylearn`; no GPU load; no process stopped.

---

## Per-engine summary lines


