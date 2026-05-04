# OpenAPI v1 vs modular backend — contract audit

**Purpose:** Map [`openapi-v1.yaml`](openapi-v1.yaml) (target v1 contract) to the **current** FastAPI handlers under `backend/src/` (mostly `app_modular.py` + `routers/`). Flag naming/path gaps for future `/api/v1` gateway or client updates.

**Last updated:** 2026-04-15

---

## Operations matrix

| OpenAPI v1 (target) | Implemented route (modular) | Handler module | Notes |
|---------------------|------------------------------|----------------|--------|
| `GET /api/v1/health` | `GET /api/health`, `GET /health` | `routers/health.py` | Multiple aliases; v1 path not mounted verbatim. |
| `POST /api/v1/jobs/process` | `POST /process` | `routers/processing.py` | Multipart: OpenAPI uses `video_file`; router uses field name **`video`** (UploadFile). Response includes `status` + `job_id` (see `JobCreatedResponse` in OpenAPI). |
| `GET /api/v1/jobs/{job_id}` | `GET /status/{job_id}` | `routers/processing.py` | Same information as `JobStatusResponse`; path differs. |
| `POST /api/v1/jobs/{job_id}/cancel` | `POST /cancel_job/{job_id}` | `routers/processing.py` | Path prefix differs. |
| `POST /api/v1/youtube/download` | (partial / legacy in `app.py`) | `app.py`, media services | Not exposed as v1-prefixed route in modular app; see `API_V1_SPEC.md` if present. |
| `POST /api/v1/youtube/preview` | (partial / legacy) | `app.py` | Same as above. |

---

## Schema vs runtime (`GET /status/{job_id}`)

Aligned with [`JobRecord.to_status_api_dict`](../backend/src/services/core/ports/job_record.py):

| Field | OpenAPI `JobStatusResponse` | Runtime notes |
|-------|----------------------------|---------------|
| `job_id` | string (uuid) | UUID string from job manager. |
| `status` | string (pipeline values) | Includes `queued`, `preparing`, `transcribing`, `analyzing`, `waiting_review`, `cutting`, `complete`, `error`, `cancelled`. |
| `progress` | string **or** number | Human-readable line when available; otherwise numeric fallback (`percentage` or `0`). |
| `message` | optional string | Mirrors progress text / `progress_msg` when set. |
| `percentage` | optional int 0–100 | Present when metadata carries `percentage`. |
| `error` | optional string | Present on failure paths. |
| `clips` | optional array | Returned when present in spec; may be absent until job completes. |

---

## Long-running / blocking flows (`app.py`)

- Monolithic [`app.py`](../backend/src/app.py) defines a large `POST /process` with many form fields and may run long steps inline depending on code path.
- Modular [`app_modular.py`](../backend/src/app_modular.py) + `POST /process` delegates to `JobCommandPort.submit_job` → `JobManager` queue; HTTP returns quickly with `job_id`.
- **Strangler:** `CLIP_USE_MODULAR_ENTRY=1` re-executes `app_modular.py` from `app.py` **main** only; it does **not** rewrite in-handler delegation for monolith `POST /process`.

---

## Follow-ups (optional)

- Mount v1 router with prefix `/api/v1` that forwards to existing handlers (thin adapter).
- Rename multipart field `video` → `video_file` behind feature flag for strict OpenAPI match.
- Add automated diff test: OpenAPI examples vs sample JSON from `TestClient`.
