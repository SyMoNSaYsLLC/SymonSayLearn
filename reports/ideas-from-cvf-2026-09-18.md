# Ideas from the Computer Vision Foundation sites — 2026-09-18

Garrett asked for a scan of thecvf.com and cove.thecvf.com for ideas not yet implemented.
What came back: the front pages only (conference calendar — WACV Jan 2027 Orlando, CVPR
Jun 2027 Seattle, ICCV Oct 2027 Hong Kong; an open-access proceedings portal; an AI Art
Gallery; awards; sponsorship). The open-access index refuses non-browser fetches (403) and
COVE — the Computer Vision Exchange, a curated dataset registry with per-dataset metadata
(task, modality, licence, citation) — renders client-side, so its listing did not come
through. The ideas below are mapped from what those two things are for onto what the
estate has today. Each names the unit it lands in and what exists already.

| # | Idea | Lands in | What exists today | Gap |
|---|---|---|---|---|
| 1 | **Vision in the dialect.** The Messages dialect carries image content blocks; a `symon-vision` card answers them (captioning, OCR, document questions). | gateway + chat unit | gateway forwards image blocks unchanged; engine is text-only; the selected Rust engine supports vision-language checkpoints | a permissively licensed VLM checkpoint acquired and registered; one more model card; conformance cases with image input |
| 2 | **Image unit beyond text-to-image.** img2img, inpainting, upscaling, ControlNet are already compiled into `sd-cli`. | image / sigils units (8809/8810) | txt2img only is wired; the CUDA `sd-cli` with 141 sm_120a kernels is staged tonight | dialect-neutral operations on the unit (`generate`, `edit`, `upscale`) behind the same key and tier model |
| 3 | **Provenance inside every generated image** — prompt, seed, card id, weights sha, licence — written as image metadata and readable by the web UI. | image unit + web | `sd-cli` writes generation parameters into PNG text chunks | a fixed provenance schema, a verifier, and the gallery below reading it |
| 4 | **A gallery surface** (the AI Art Gallery pattern): the sigils unit's outputs browsable with their provenance cards. | web | three chat surfaces + models/rack/settings pages | one page, one endpoint listing outputs |
| 5 | **The weights and datasets register, served** (the COVE pattern): every checkpoint with task, modality, licence class from the ship gate, source pin, sha, terms — as a page and an endpoint, and enforced: no weights load without a register entry. | control plane + web | `work/pins/model-register.json`, `x-symoneural` provenance on `/v1/models/{id}`, the ship-gate weights rule | the register as a served resource; the load-time check |
| 6 | **Release proceedings** (the open-access pattern): each release ships measured numbers — tokens/s, first-token latency, VRAM held, image seconds per step, conformance pass counts — beside SHA256SUMS. | tools/cut-release | RELEASE-NOTES truth table planned; conformance suite exists (51 assertions) | a small fixed benchmark run at cut time, machine-readable |
| 7 | **Regression gates from fixed seeds** (the challenge/leaderboard pattern): fixed prompts and seeds; token counts and perceptual hashes compared release to release; a drift fails the gate. | ship gate | determinism checks exist for builds (`check-determinism.py`), not for model output | the fixture set and the comparison |
| 8 | **Video understanding on the streamer**: sample frames from the HLS stream, describe them with the vision card, emit captions/scene changes. | streamer unit (8805) + gateway | hls.js front end, GStreamer core/base recipes; no analysis path | frame sampler → vision card → caption track |
| 9 | **Embeddings and retrieval** (`/v1/embeddings` for text and image): local search over the operator's documents and images, feeding the work surface. | gateway + a small model | endpoints.py reserves an embeddings route returning 404 unless `capabilities.embeddings` | a permissive embedding checkpoint; the route promoted from RESERVED |
| 10 | **Segment-then-inpaint**: a small permissive segmentation model produces the mask that inpainting (idea 2) consumes — the most common CV workshop pipeline. | image unit | inpainting compiled in `sd-cli` | the mask model and the two-step operation |

Order of value for the runtimes-completion priority: 1 (uses the engine being built tonight),
5 (governance the gate already wants), 2 (already compiled, just unwired), 6/7 (proof).
Nothing here is started; this note records the map.
