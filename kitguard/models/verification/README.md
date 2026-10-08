# KitGuard local model engineering verification

Verified on 2026-09-26 with Apple M5 Pro, 64 GiB unified memory, macOS 26.6.2, Python 3.12.14, MLX 0.32.2, MLX-VLM 0.7.3, Transformers 5.17.0, Torch 2.14.0 and Torchvision 0.29.0. The complete dependency versions are pinned in the KitGuard project's `requirements-lock.txt` without an absolute editable install path.

Only `mlx-community/Qwen3-VL-8B-Instruct-8bit` was downloaded, pinned at `a0093b9b5fda6f76ddd4a462c6830ae7c4fe47ec`. All 17 repository files total 9,871,846,818 bytes. Both actual safetensors shards match their upstream LFS SHA-256 values, and all file sizes and SHA-256 hashes are recorded in the adjacent model manifest. The first snapshot fetch completed in approximately 14 minutes 44 seconds. Subsequent downloader invocations reused the completed snapshot and reverified it; their short invocation durations are not a full-download benchmark.

## Actual inference and API results

`kitguard_smoke.py` loads the actual local weights once and runs all cases in one process. The image case uses FastAPI TestClient, the actual LocalVision adapter, and a temporary database: create order → upload PNG → inspect → read back state. It does not use the deterministic unit-test analyzer.

| Check | Actual result | Measured time |
|---|---|---|
| Cold model load | Model and processor loaded from local files | 2.100 s |
| Korean instruction to remove one bolt and add one washer | Correct proposed counts: bolt 0, nut 1, washer 2, bracket 1 | 3.247 s generation; 5.798 s first-call wall time including cold load |
| Chinese instruction to set bolts to two, leaving others unchanged | Correct proposed counts: bolt 2, nut 1, washer 1, bracket 1 | 1.928 s generation; 1.929 s wall time |
| Chinese request for 100 bolts | Actual model returned a clarification; adapter raised ValueError, without clamping | 1.693 s generation; 1.694 s wall time |
| Clearly labeled synthetic engineering image through the full API | `backend=mlx`, all counts null, `decision=manual`, order `needs_action`, never `completed` | 5.434 s generation; 5.465 s complete image API sequence |

MLX reported peak allocated memory was **10.913 GB (decimal)**, taken from `mx.get_peak_memory()/1e9` through MLX-VLM. This is not whole-system memory or process RSS. Separately, macOS process maximum RSS was **10,766,778,368 bytes** for this test process.

The process exited after verification, releasing the loaded weights. No model remains resident merely because these files exist.

## Interpretation and limits

The image is a deliberately labeled generated engineering fixture, not a photograph of hardware. These checks establish model loading, bounded local image processing, structured response validation, multilingual quantity proposals, rejection of the tested out-of-range request, and real API integration. They do **not** establish physical-part counting accuracy, production readiness, latency for arbitrary photographs, or resistance to every ambiguous instruction.

The raw successful smoke report preserves the initial model-generated explanation wording. A subsequent small application change formats accepted proposals from validated current-to-proposed quantities and explicitly says `미적용 변경 제안 ... 승인 후 적용됩니다.`. Rejection keeps the model's actual clarification. This change does not alter inference or automatically apply an order revision; it prevents generated prose from claiming that an unapproved proposal was already applied. The complete project suite passed 67 tests after this change.

## Files

- `synthetic_engineering_smoke.png`: clearly labeled engineering fixture.
- `kitguard_smoke.py`: reproducible actual-model smoke procedure.
- `kitguard_smoke_result.json`: successful actual output, API identifiers, decisions and metrics.
- `kitguard_smoke.log`: output from the successful run.

The model directory's original index references four nonexistent upstream shards. Source files remain unchanged. MLX-VLM falls back to the two real local safetensors files; KitGuard's availability check validates those two files by their exact verified sizes.
