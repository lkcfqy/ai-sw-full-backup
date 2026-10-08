# KitGuard shared local models

Current selected model, verified on 2026-09-26: [mlx-community/Qwen3.6-27B-4bit](https://huggingface.co/mlx-community/Qwen3.6-27B-4bit/tree/c000ac2c2057d94be3fa931000c31723aac53282), pinned revision `c000ac2c2057d94be3fa931000c31723aac53282`, local directory `Qwen3.6-27B-4bit`. This is a community MLX quantization of [Qwen/Qwen3.6-27B](https://huggingface.co/Qwen/Qwen3.6-27B/tree/6a9e13bd6fc8f0983b9b99948120bc37f49c13e9), not Qwen-published MLX weights.

KitGuard's selected visual protocol is **one observation producing a part-by-part class/position inventory, followed by code-based counting**, with image longest side 1536, maximum 900 output tokens, temperature 0 and thinking disabled. The chosen protocol was frozen before the 48-image holdout run in the project file `docs/RELEASE_EVALUATION_FREEZE.json`. Coordinates are model estimates, not independently validated location truth. Earlier two-orientation and brightness-gate experiments are not the selected production protocol.

The model loaded and ran on the Apple M5 Pro Mac with 64 GiB physical memory, Python 3.12.14, MLX 0.32.2 and MLX-VLM 0.7.3. Completed development records show 15/16 original-photo count vectors correct, with one incorrect but definite observation, and 24/24 author-written language cases passing their expected proposal/clarification behavior. These are development checks, not field accuracy or a guarantee of correctness. Later holdout results belong to the project's final evaluation report and are not inferred here.

Runtime evidence is separate from acquisition evidence: [Qwen3.6-27B-KitGuard-runtime-verification-v1.json](verification/Qwen3.6-27B-KitGuard-runtime-verification-v1.json) derives its metrics from the completed `loco_development_release_v1` and `instructions_27b_v1` records and pins their file hashes. The language run preceded final spatial integration and records its own source snapshot. Expected clarification responses can have caught domain-error records and are not counted as execution failures.

The visual development run reported an MLX peak of **19.114 decimal GB**, image-call median **14.742 seconds** and maximum **18.273 seconds**, including cold loading when applicable. The text-only language run reported a maximum MLX peak of **17.050 decimal GB**. This is the `mx.get_peak_memory() / 1e9` metric surfaced by MLX-VLM, potentially cumulative within a process. It is **not the computer's total RAM usage, independent per-image allocation, or a promise for longer contexts and concurrent workloads**. The development model load took 2.979 seconds; these observations apply only to the recorded run.

Retained baseline: [mlx-community/Qwen3-VL-8B-Instruct-8bit](https://huggingface.co/mlx-community/Qwen3-VL-8B-Instruct-8bit), revision `a0093b9b5fda6f76ddd4a462c6830ae7c4fe47ec`, local directory `Qwen3-VL-8B-Instruct-8bit`.

Formats: MLX 8-bit baseline and MLX 4-bit selected model for Apple Silicon Macs. Other compatible projects can reuse the same local directories without another download. These are not RTX 3080/CUDA or Ollama GGUF formats. The original unquantized model weights were not downloaded; upstream cards and license texts were archived separately.

The repository's original README is inside the model directory. See the adjacent manifest for source revision, SHA-256 hashes, verified bytes, and license location. The acquisition manifest's historical `status=files_verified_runtime_not_tested` is deliberately unchanged: the downloader did not load a model. The later runtime-verification JSON supplies subsequent runtime evidence without rewriting that history. `.incomplete` files and `.download-chunks` are staging data, not usable weights. The original candidate rationale in `provenance/Qwen3.6-27B-4bit/候选选择与使用边界.md` is also retained as a dated pre-verification record.

Both the community and original model cards declare Apache-2.0. The original upstream license is archived as `licenses/Qwen3.6-27B/LICENSE`; the pinned source is [the Qwen license](https://huggingface.co/Qwen/Qwen3.6-27B/blob/6a9e13bd6fc8f0983b9b99948120bc37f49c13e9/LICENSE). Model licensing does not replace the distinct **CC BY-NC-SA 4.0** terms on the MVTec photographs and derived labels. Dataset provenance and use limits are documented separately in the KitGuard project.

For a fresh installation, use the KitGuard project's locked environment and `.venv/bin/python scripts/download_candidate_model.py` to acquire the selected model. `.venv/bin/python scripts/download_model.py` manages the retained 8B baseline. The selected downloader is revision-pinned, verifies all source files and only then writes the acquisition manifest. Do not run a downloader or replace shared model files while another process is using them. From the project, `bash scripts/run.sh` selects this 27B local protocol and enables offline inference. Other projects should use the absolute model directory with an independently compatible MLX runtime.

## Baseline upstream index compatibility

The pinned community snapshot has a stale `model.safetensors.index.json` naming four upstream shards, while the quantized snapshot actually contains two shards. No original model file was edited: all original SHA-256 hashes remain valid. MLX-VLM 0.7.3 falls back to the actual local safetensors files. KitGuard's availability check uses the verified sizes of the two real shards.

The selected 27B model has a matching three-shard index. Its three weight files total 16,054,541,599 bytes; the full 16-file snapshot totals 16,081,490,064 bytes. All downloaded source files remain unchanged. File verification and a model's ability to run are separate from application-level accuracy.

## Verification scope

See the separate current runtime-verification JSON above and `verification/Qwen3.6-27B-reproducibility-review.json` for the bounded independent CPU-only acquisition review. That review rechecked all 16 sizes, 13 non-weight file hashes, the preserved weight checksum evidence, and freshly fetched pinned upstream license/community card hashes. It did not load or rehash 16 GB of model weights while the benchmark was running.

`verification/kitguard_smoke_result.json` and `verification/README.md` retain earlier 8B local engineering checks. Synthetic pictures are deliberately labeled and are not evidence of accuracy on real hardware. Public static photographs do not prove actual physical correction, continuous recapture, human task-time savings or unfamiliar-factory performance.
