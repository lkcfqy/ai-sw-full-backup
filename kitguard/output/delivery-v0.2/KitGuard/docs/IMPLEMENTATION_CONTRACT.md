# KitGuard implementation contract

Local desktop application; Python FastAPI, SQLite, vanilla HTML/CSS/JS. Root owns app.py, store.py, schemas.py. Frontend agent owns static/. Model agent owns vision.py, scripts/download_model.py and shared model directory, bootstrap dependencies. Tests agent owns tests/. Do not edit another owner's files without coordination.

Updated implementation notes, 2026-09-26: file ownership above describes the initial delegation; current root coordinates all core changes. Historical evaluation runs preserve their own source snapshots, so this current contract does not retroactively describe those versions.

## Data

Four part IDs: bolt, nut, washer, bracket. Each order requirement is a strict integer 0..3 (not boolean), total 1..12. Observed counts are independently validated and may exceed the order quantity; uncertain classes are null. Catalog labels: 볼트/螺栓, 너트/螺母, 와셔/垫圈, 브래킷/角码. Single reference type per category, not fine-grained SKU/size recognition.

Order object: {id,title,revision,evidence_epoch,requirements:{bolt:2,nut:2,washer:2,bracket:1},status:'pending'|'needs_action'|'ready'|'completed',created_at,updated_at,latest_check:null|Check,photos:[],events:[],revisions:[],references:{},reference_history:[],checks:[],completions:[]}. POST responses order under {order:...} except noted.
Photo includes {id,url,sha256,source_sha256,revision,created_at,width,height,quality:{warning:null|string}}. sha256 identifies the normalized stored JPEG; source_sha256 identifies original uploaded bytes, which are not retained as the original file. The photograph is evidence supplied by the operator, not authenticated physical-scene provenance.
Check: {id,order_id,revision,photo_id,decision:'ready'|'recapture'|'correct'|'manual',observed:{bolt:int|null,nut:int|null,washer:int|null,bracket:int|null},differences:[{part,required,observed,delta}],issues:[string],action:{kind:'none'|'separate'|'recapture'|'add_remove'|'manual',message:string,region:[x1,y1,x2,y2]|null},model_label,backend:'mlx'|'test',latency_ms,created_at,valid:bool}. Region normalized 0..1. No model confidence as certainty. Inference duration varies by model/image and cannot be promised; frontend disables repeated inspect while awaiting and shows honest loading, not fake timed stages. Manual review is never ready/completed by inference.
Event: {id,kind,message,created_at,payload}. Revision {revision,requirements,instruction,created_at}.

## HTTP API

- GET /api/health -> {ok:true,model:{available,loaded,label,path,error},version}
- GET /api/catalog -> {parts:[{id,label_ko,label_zh}],limits:{per_part:3,total:12}}
- GET /api/orders -> {orders:[Order summary...]}
- POST /api/orders JSON {title,requirements} (title 1..100 characters) -> {order:Order}, 201
- GET /api/orders/{id} -> {order:Order}
- POST /api/orders/{id}/propose-revision JSON {instruction,expected_revision} (instruction 1..500 characters) -> {proposal:{requirements,explanation,base_revision}}. DOES NOT mutate order. Human must approve via next route. Structured number edits can call next route directly.
- POST /api/orders/{id}/revise JSON {requirements,instruction,expected_revision} -> {order:Order}; atomically invalidate old checks. Reject stale expected_revision with409.
- POST /api/orders/{id}/photos multipart photo:file, expected_revision:int -> {order:Order,photo:Photo},201. Image JPEG/PNG/WEBP max12MB, decode/check dimensions, strip EXIF by reencoding. New photo invalidates previous readiness. Filename never controls storage path.
- POST /api/orders/{id}/references/{part} multipart photo:file -> {order:Order}; updating a reference invalidates readiness.
- POST /api/orders/{id}/inspect JSON {photo_id,expected_revision} -> {order:Order,check:Check}; executes real model observer, checks state again after inference before committing; reject stale409, model unavailable503, request deadline504 (GPU worker may continue). Targeted new photos allowed, up to2 additional evidence attempts then manual. Correct/add-remove advice only when counts observable.
- POST /api/orders/{id}/complete JSON {check_id,expected_revision,confirmed:true,idempotency_key} -> {order:Order,completion:{id,replayed:bool}}; atomic version + latest photo/check +ready validation, readback; stale409. Completed record keeps supporting photo and order revision. Exact same idempotency key/body returns same result; conflicts409. A revision after completion resets current order pending but keeps history.
- GET /api/orders/{id}/export -> downloadable JSON with all state/events. GET /api/photos/{photo_id} -> immutable local image. GET /api/templates/tray.svg -> printable12slot tray.
- GET /api/orders/{id}/evidence.zip -> temporary on-disk ZIP containing this order's linked current/historical photographs, evidence.json, a relative offline viewer, README and SHA256.json. The server verifies photo hashes and fails on missing/corrupt content. Other orders and the SQLite database are excluded.

Errors: {detail:string|validation errors}. No hidden fake model success, no seeded production demo results. New order default requirements chosen in UI. A separate labeled deterministic test fixture may be used by automated tests only, not product demo.

## Selected release configuration

The current selected default is `Qwen3.6-27B-4bit`, repository `mlx-community/Qwen3.6-27B-4bit`, pinned revision `c000ac2c2057d94be3fa931000c31723aac53282`. Shared weights live outside this project in `~/Downloads/AI-Models/Qwen3.6-27B-4bit/`. The downloader and model provenance manifest retain upstream file hashes; no inference-time downloads or cloud requests are allowed by the local adapter.

Default observation is `spatial_inventory`, input longest side 1536px, one model call, 900 output tokens, temperature 0 and `enable_thinking=false`. `KITGUARD_MODEL_PATH`, optional `KITGUARD_MODEL_PROFILE`, `KITGUARD_OBSERVATION_MODE` and `KITGUARD_IMAGE_MAX_SIDE` configure the adapter. The selected default is neither dual orientation nor a geometry/brightness rejection guard. The protocol/source hashes and planned comparison were frozen before holdout in `docs/RELEASE_EVALUATION_FREEZE.json`; evaluation snapshots, not the current working tree, define historical results.

Upload normalization strips EXIF and caps stored images at 2048px. The selected observer resizes this stored image to at most 1536px, preserving its orientation and aspect ratio; references are at most 512px. An image's normalized original coordinate frame refers to this unrotated photograph, not raw camera sensor coordinates or a tray identifier.

## Model adapter

vision.py exports LocalVision(model_path:Path|None=None) and methods status()->dict, observe(image_path:Path, requirements:dict, references:dict[str,Path])->dict, propose_revision(instruction:str, requirements:dict)->dict.
Observation dictionary (optional evidence fields below): {observed:{bolt:int|null,nut:int|null,washer:int|null,bracket:int|null},issues:[str],action:{kind:'none'|'separate'|'recapture'|'manual',message:str,region:[0..1]*4|null},model_label:str,backend:'mlx',latency_ms:int}. Never trust metadata as state. Root independently validates and derives count differences. Uncertain/occluded=null; malformed output must fail closed. Model runs serialized in one worker thread, model loads once, no parallel GPU execution. App calls via to_thread / lock, not main async loop. Adapter must tolerate Korean short instruction and bounded output; see settled plan for limitations.
Proposal {requirements:dict,explanation:str}. All values validated by server. If unclear, raise ValueError asking clarification, never mutate. Keep short metadata for audit; no claim external photo provenance verified.

create_app(data_dir:Path|None=None, analyzer=None) in kitguard.app allows test analyzer injection. Default data_dir from KITGUARD_DATA_DIR or project data/, model path KITGUARD_MODEL_PATH or ~/Downloads/AI-Models/Qwen3.6-27B-4bit. Importing app must NOT load weights. Default app bound127.0.0.1 only; no internet service deploy.

## Current evidence and model extensions

- Checks preserve `requirements_snapshot`, `reference_ids`, `photo_sha256`, `runtime_identity`, `observation_context`, `evidence_feedback` and actual `tool_trace`. Store commit is appended only after current-state comparison succeeds. Historical details remain read-only.
- Feedback applies only to different photo IDs in the same requirements revision and exact reference set. It compares observed uncertainty/count changes, never asserts a physical action happened (`physical_action_verified=false`). Identical bytes can be submitted under a new ID; that is not proof of a new physical scene.
- Two additional distinct photos per continuous unclear episode trigger manual review. Old revisions/references and same-photo retries do not consume that episode's budget. Correct quantities are never carried forward to fill a new image's unknown counts.
- Natural-language revision uses source-grounded part/quantity spans and set/add/remove intents. The code validates original wording, computes arithmetic, checks constraints and preserves unmentioned quantities. Ambiguous/unsupported edits require clarification; a proposed change is not an applied revision.
- `LocalVision` supports pinned 8B and 27B profiles and `single`/`dual_orientation`/`spatial_inventory` modes, with longest side 1024/1536/2048. Current defaults are the selected release configuration above. Target quantities remain outside visual prompts. Direct counting retains its 450-token budget, so the planned same-model control changes prompt/output structure and token budget together; it is not an isolated spatial-coordinate or token-budget ablation.
- In `dual_orientation`, the second image is an actual 90-degree rotation without the first response or order target. Count disagreement becomes null. Any uncertainty in either observation blocks a clear result. Matching responses are correlated and may both be wrong; they are not confidence estimates or independent experts.
- `observation_verification` preserves both pass inputs' SHA, transformations and validated observations. Failure in the second pass does not fall back to a successful first response; exception-bound diagnostics preserve the successful pass in the failed event without producing a valid check. Timeout does not guarantee the GPU thread stopped.
- Public-image evaluations and browser fixtures are separate. `app-upload` evaluation actually executes the isolated upload route before the observer; it does not exercise the live inspect timeout route. Its measured interval includes SQLite/upload/normalization/hash overhead, and is labeled accordingly.

## Spatial object evidence and deterministic counts

The selected model is asked for a strict `SpatialInventory`: at most 20 objects `{part,center:[x,y]}`, unique `uncertain_parts`, brief `issues`, and action `none` or `recapture`. `part` is one of the four catalog IDs; coordinates are finite numeric values in 0..1. The prompt does not include requirements, dataset truth or a normal package composition. A bolt head and its attached shaft form one object; washer includes flat and split/spring lock washers. Bags, printed text, shadows and reflections are excluded.

`spatial.py` counts entries by part. It does not deduplicate positions, invent hidden objects, clamp to target quantities or use geometric location as correctness proof. Affected classes become null. If an issue/action is not localized to a class, all classes become unknown; uncertainty forces recapture. Server validation checks that every non-null observed count equals its listed category total and uncertain parts remain null. A plausible but incorrect list can still pass this structural validation.

The optional saved check field is:

```json
{
  "object_evidence": {
    "protocol": "spatial_inventory_v1",
    "coordinate_frame": "normalized_original",
    "objects": [{"part": "bolt", "center": [0.25, 0.5]}],
    "uncertain_parts": []
  }
}
```

The JSON above describes field shape, not a model result. `object_evidence` may be absent on old or other-protocol checks. UI binds overlays to the check's exact `photo_id`; if both stored photo/check SHA values exist, they must match. Invalid coordinate lists/frames are hidden, never silently filtered into an apparently complete inventory. Native keyboard-operable toggles start off on each photo/check render; the issue region remains above markers. Lists and markers are read-only, expose saved order revision, and cannot confer completion authority. Backend `test` records are visibly labeled engineering fixtures.

The actual trace includes `derive_counts_from_object_list` with `status`, `listed_objects` and `uncertain_parts`, followed by requirements comparison, previous-evidence review, action selection and commit after the version/evidence guard succeeds. These are software execution steps, not hidden model reasoning. `runtime_identity` stores label, repository, model revision, observer protocol SHA, mode and image size. `GET /api/health` additionally reports observer source hashes and load/last-inference status; this is operational metadata, not a per-check guarantee of physical correctness.

UI selectors for read-only recording: workspace `.evidence-panel [data-action="spatial-toggle"]`, audit `#audit-dialog [data-spatial-scope="audit"] [data-action="spatial-toggle"]`, list `.spatial-inventory > summary`. Toggle state is `aria-pressed`; overlays are `#workspace-spatial-overlay` / `#audit-spatial-overlay`. No field means no selector.

## Portable audit and scope of claims

JSON export preserves versions, reference history, checks, events, completion receipts and saved runtime identities. Evidence ZIP adds this order's linked normalized photo bytes, `OPEN_ME.html`, `evidence.json`, `README.txt` and `SHA256.json`. The server verifies stored-photo hashes and refuses missing/corrupt evidence, excludes other orders and the database, and creates a read-only snapshot. Hashes are not digital signatures, captured-scene authenticity or verification that a requested material operation occurred. Original upload bytes and model weights are not in the bundle.

Position evidence is model-estimated; there is no annotated localization accuracy claim. Model-supplied lists can duplicate, omit or misclassify parts. Four-class quantity checks do not identify exact SKU, long/short screw composition, dimensions, material, thread or industrial compliance. The current public LOCO scope merges long/short screws and contains no bracket positives. Development tuning, frozen holdout, engineering fixtures and human field validation must remain distinct. Static public images and operator completion receipts do not establish that the agent verified real replenishment. Missing/failed/partial evaluation data must not become zeros or successful observations.
