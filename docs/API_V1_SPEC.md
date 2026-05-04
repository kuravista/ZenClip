# ZenClip API v1 — Spesifikasi Terpadu

**Lokasi machine-readable:** `docs/openapi-v1.yaml`  
**Status:** Target kontrak untuk refactor; backend saat ini utamanya `app.py` (monolith). Endpoint `/api/v1/*` belum semua diimplementasikan — gunakan dokumen ini sebagai sumber kebenaran desain.

---

## 1. Prinsip

| Item | Nilai |
|------|--------|
| Base path | `/api/v1` |
| Namespace AI | `/api/v1/ai/...` |
| Download YouTube (job terpisah) | `POST /api/v1/youtube/download` |
| Upload video | `multipart/form-data` |
| Resume / preview / settings | `application/json` |

---

## 2. Mapping endpoint lama → v1

| Lama | Baru (v1) |
|------|-----------|
| `POST /process` | `POST /api/v1/jobs/process` |
| `GET /status/{job_id}` | `GET /api/v1/jobs/{job_id}` |
| `POST /api/cancel_job/{job_id}`, `POST /cancel_job/{job_id}` | `POST /api/v1/jobs/{job_id}/cancel` |
| `GET /jobs`, `GET /jobs/stats`, `DELETE /jobs/{job_id}` | `/api/v1/jobs`, `/api/v1/jobs/stats`, `DELETE /api/v1/jobs/{job_id}` |
| `POST /extract_transcript` | `POST /api/v1/jobs/extract-transcript` |
| `GET /get_transcript/{job_id}` | `GET /api/v1/jobs/{job_id}/transcript` |
| `POST /process_with_transcript` | `POST /api/v1/jobs/{job_id}/resume` |
| `POST /manual_transcript_import` | `POST /api/v1/jobs/import-transcript` |
| `POST /auto_fix_transcript` | `POST /api/v1/ai/transcript/auto-fix` |
| `POST /normalize_import_schema` | `POST /api/v1/ai/transcript/normalize` |
| `POST /api/yt-preview` | `POST /api/v1/ai/youtube/preview` |
| `GET /api/yt-supported` | `GET /api/v1/ai/youtube/supported` |
| *(baru)* | `POST /api/v1/youtube/download` |
| `GET /api/videos`, video by path, delete | `/api/v1/videos/...` |
| `GET /api/thumbnail/...`, `GET /api/thumbnails/...` | `GET /api/v1/thumbnails/{filename}` |
| `GET /download/...` | `GET /api/v1/download/{filepath}` |
| `POST /api/upload` | `POST /api/v1/videos/upload` |
| `POST /api/preview` | `POST /api/v1/videos/preview` |
| Settings / fonts / health | `/api/v1/settings`, `/api/v1/fonts`, `/api/v1/health` |

---

## 3. Sepuluh endpoint penting — request / response minimal

### 1) `POST /api/v1/jobs/process`

- **Body:** `multipart/form-data`
- **Wajib salah satu:** `video_file` (file) **atau** `url` (string)
- **Opsional:** `yt_quality`, `num_clips`, `min_duration`, `api_provider`, `api_key`, `add_subtitles`, `add_viral_hook`, `manual_cut`, `manual_segments` (string JSON), dll.

**200:** `{"job_id": "uuid"}`  
**400:** `{"error":"validation_error","message":"..."}`

### 2) `GET /api/v1/jobs/{job_id}`

**200:**

```json
{
  "job_id": "uuid",
  "status": "processing|waiting_review|complete|error|cancelled",
  "progress": 42,
  "message": "…",
  "error": null,
  "clips": []
}
```

### 3) `POST /api/v1/jobs/{job_id}/cancel`

**200:** `{"status":"success","job_id":"uuid"}`

### 4) `POST /api/v1/youtube/download`

**Body JSON:**

```json
{ "url": "https://…", "quality": "720p" }
```

**200:** `{"job_id":"uuid","mode":"youtube_download"}`

Hasil path file setelah selesai: ekstensi respons `GET /api/v1/jobs/{job_id}` (mis. `result.video_path`) — detail implementasi.

### 5) `POST /api/v1/jobs/extract-transcript`

- **Body:** `multipart` — pola sama: `video_file` atau `url`
- **200:** `{"job_id":"uuid"}`

### 6) `POST /api/v1/jobs/{job_id}/resume`

**Body JSON:**

```json
{
  "phrase_timings": [{ "text": "…", "start": 0.0, "end": 1.2 }],
  "clips_data": [{ "start_time": 10.5, "end_time": 45.0, "topic": "…" }]
}
```

**200:** `{"status":"resumed","job_id":"uuid"}`

### 7) `POST /api/v1/ai/youtube/preview`

**Body:** `{"url":"https://…"}`

**200:** `{"status":"success","metadata":{ "title","duration","thumbnail","available_qualities","webpage_url" }}`

### 8) `GET /api/v1/videos`

**200:** `{"videos":[…],"count":n}`

### 9) `GET /api/v1/settings` / `PUT /api/v1/settings`

**PUT:** partial JSON. **200:** `{"status":"success","settings":{…}}`

### 10) `GET /api/v1/health`

**200:** `{"status":"ok","version":"1.0.0"}`

---

## 4. Schema `phrase_timings` & `clips_data`

### `phrase_timings` → disimpan sebagai `transcript.json` (array)

**Minimal (cukup untuk banyak langkah pipeline):**

```json
[
  { "text": "Kalimat.", "start": 1.24, "end": 4.10 }
]
```

**Lengkap (output ASR internal):** tambahkan `duration`, dan `words[]`:

```json
{
  "text": "Kalimat.",
  "start": 1.24,
  "end": 4.10,
  "duration": 2.86,
  "words": [
    { "text": "Kalimat", "start": 1.24, "end": 1.80, "probability": 0.95 }
  ]
}
```

**Aturan:** setiap item `end > start`; `text` tidak kosong.

**Normalisasi impor:** `POST /api/v1/ai/transcript/normalize` (setara lama `normalize_import_schema`) menerima sinonim field dan mengeluarkan `text` + `start` + `end` saja (tanpa `words`).

### `clips_data` → disimpan sebagai `analysis.json`

**Penting:** root file harus **JSON array** `[...]`, bukan `{"clips":[...]}`, agar kompatibel dengan `JobRunner`.

**Minimal:**

```json
[
  { "start_time": 120.5, "end_time": 185.0, "topic": "Judul klip" }
]
```

**Disarankan (selaras LLM + video cutter):**

| Field | Wajib cutter | Keterangan |
|--------|----------------|------------|
| `start_time` | ya | detik |
| `end_time` | ya | detik, `> start_time` |
| `topic` | sangat disarankan | label / nama file |
| `viral_score` | tidak | number |
| `reason` | tidak | string |
| `hook_heading` | tidak | string |
| `hook_subheading` | tidak | string |
| `viral_caption` | tidak | string |

Opsional renderer: `hook_top_text`, `preset2_content`, `highlight_map`, `emoji_map`, watermark per-clip, dll.

### Segmen manual UI (`manual_segments` pada job, bukan `analysis.json`)

```json
[{ "start": "02:00", "end": "02:45" }]
```

Waktu string `MM:SS` atau `H:MM:SS`.

### Catatan implementasi saat ini

- `JobRunner` mengharapkan `analysis.json` sebagai **array**.
- Beberapa router lama menulis `{"clips": [...]}` — itu **tidak selaras** dengan runner; v1 harus menulis array langsung.

---

## 5. Referensi OpenAPI

Lihat **`openapi-v1.yaml`** di folder yang sama untuk skema yang bisa di-import ke Swagger UI / codegen.

---

*Dokumen ini menggabungkan ringkasan API v1, mapping legacy, 10 endpoint kunci, dan kontrak `phrase_timings` / `clips_data`.*
