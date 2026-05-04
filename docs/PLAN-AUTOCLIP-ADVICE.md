# PLAN-AUTOCLIP-ADVICE.md
## Rencana Adopsi Fitur Terbaik AutoClip ke ZenClip

> **Status**: Draft — Developer Handoff Document  
> **Tanggal**: 18 April 2026  
> **Versi**: 1.0  
> **Penulis**: Hermes Agent (Audit & Analysis)  

---

## 1. Executive Summary

### Kenapa Ini Penting?

ZenClip saat ini sudah punya fondasi yang kuat — multi-LLM (6 provider), 8 subtitle style, 4 hook preset, face-aware smart crop, anti-hallucination, dan GPU acceleration. Tapi ada area yang kurang: ZenClip melakukan *semua* analisis dalam **satu LLM call** (`llm_analyzer.py` ~590 LOC), yang artinya:

- Tidak ada scoring/grading untuk clip yang dihasilkan
- Tidak ada clustering/collection untuk konten bertema sama
- Tidak ada title generation terpisah (hanya viral_caption yang singkat)
- Tidak ada resumability yang granular per-step
- Video panjang (>60 menit) sangat berisik karena sampling uniform

AutoClip, di sisi lain, menggunakan **6-step pipeline** terpisah (outline → timeline → scoring → title → clustering → video), yang menghasilkan output lebih terstruktur dan berkualitas tinggi.

### Current State vs Target State

| Aspek | Current (ZenClip) | Target (Post-Adopsi) |
|-------|--------------------|--------------------|
| Analisis LLM | 1 call, semua serba sekali | 1 call (short) / multi-step (long) |
| Scoring | Tidak ada | Post-processing 4 kriteria + weighted score |
| Clustering | Tidak ada | Hybrid keyword + LLM clustering, optional |
| Title Generation | viral_caption (inline, max 10 kata) | Separate title generation (15-25 kata) |
| Content-Type Prompts | 6 genre (general, podcast, gaming, etc) | Retain + scoring prompt per genre |
| Resumability | Job-level (video_info, transcript, analysis) | Step-level granularity |
| Long Video | Sampling uniform, risk kehilangan konteks | Chunking 30 min per-chunk |

---

## 2. Current Architecture Analysis

### Arsitektur Single-Call ZenClip

```
User Request
    │
    ▼
┌─────────────────────────────────────────────┐
│  job_runner.py (Pipeline Orchestrator)       │
│                                              │
│  1. PREPARING → Download/Verify video        │
│  2. TRANSCRIBING → Whisper transcription     │
│  3. ANALYZING → llm_analyzer.py              │
│     └── Satu LLM call untuk SEMUA:           │
│         • Deteksi clip viral                 │
│         • Generate hook text                  │
│         • Generate viral_caption              │
│         • Generate preset2_content            │
│  4. WAITING_REVIEW (optional)                │
│  5. CUTTING → FFmpeg video cutting           │
│  6. COMPLETE                                  │
└─────────────────────────────────────────────┘
```

**File kunci:**
- `llm_analyzer.py` — Core LLM logic, ~590 LOC, semua dalam satu fungsi `analyze_transcript_with_llm()`
- `job_runner.py` — Pipeline orchestrator, ~230 LOC, artifact-based resume
- `llm_provider.py` — Multi-provider (deepseek, openai, gemini, anthropic, local, openrouter)

### Keterbatasan Arsitektur Saat Ini

1. **Tidak ada scoring** — LLM langsung pilih clip "terbaik", tapi tidak ada score numerik yang bisa di-sort/filter
2. **Prompt terlalu panjang** — System prompt sudah 150+ baris, menambah scoring/klustering di prompt yang sama bakal meledak token dan menurunkan kualitas
3. **ViralClip schema terbatas** — Hanya punya `start_time`, `end_time`, `topic`, `reason`, `viral_caption`, hook fields. Tidak ada `score`, `title`, `collection_id`
4. **Tidak bisa ranking** — User minta 3 clip, LLM kasih 3 clip. Tidak bisa kasih 10 clip lalu user pilih top 3
5. **No content grouping** — 10 clip dari 1 jam video gaming, semuanya flat, tidak ada kategorisasi

---

## 3. What AutoClip Does Better

### P1: Scoring System (HIGH impact, LOW effort)

**Problem Statement:**
ZenClip tidak punya scoring untuk clip. User minta N clip, LLM kasih N clip — tidak ada cara untuk mengukur "seberapa viral" secara numerik. Ini bikin sulit untuk:
- Sort clip berdasarkan potensi viral
- Filter clip di bawah threshold tertentu
- Kasih user lebih banyak opsi untuk dipilih

**Bagaimana AutoClip Implementasi:**
AutoClip punya `step3_scoring.py` yang memanggil LLM terpisah dengan prompt `推荐理由.txt`. Setiap clip di-score 0.0-1.0 berdasarkan 4 kriteria:
1. *Information Value* — Keunikan insight
2. *Emotional Resonance* — Kemampuan trigger emosi
3. *Viral Potential* — Kutipan/sharing potential
4. *Structural Completeness* — Logic & completeness

**Adaptasi untuk ZenClip:**
Jadikan scoring sebagai **post-processing step** setelah `analyze_transcript_with_llm()` menghasilkan clip mentah. Jangan ganti clip selection LLM — tambahkan scoring di atasnya.

```python
# File baru: services/ai/clip_scorer.py

class ClipScorer:
    """Post-processing scorer untuk clip yang sudah di-generate LLM."""
    
    SCORING_CRITERIA = {
        'information_value': 0.25,    # Keunikan insight
        'emotional_resonance': 0.30,  # Trigger emosi (weight tertinggi)
        'viral_potential': 0.25,      # Shareability
        'structural_quality': 0.20,   # Kelengkapan logic
    }
    
    def score_clips(self, clips: List[Dict], video_type: str = 'general') -> List[Dict]:
        """
        Score clip yang sudah ada. Tambahkan viral_score dan score_breakdown.
        """
        from services.ai.llm_provider import generate_llm_response
        
        # Siapkan input untuk LLM scoring
        clips_for_scoring = []
        for i, clip in enumerate(clips):
            clips_for_scoring.append({
                "id": str(i),
                "topic": clip.get("topic", ""),
                "reason": clip.get("reason", ""),
                "start_time": clip["start_time"],
                "end_time": clip["end_time"],
                "duration": clip["end_time"] - clip["start_time"]
            })
        
        response = generate_llm_response(
            prompt=json.dumps(clips_for_scoring, ensure_ascii=False),
            system_instruction=SCORING_PROMPT[video_type],
            api_key=self.api_key,
            provider=self.provider,
            temperature=0.2  # Low temp untuk scoring konsisten
        )
        
        # Parse dan merge scores
        scored = self._parse_and_merge(clips, response)
        return sorted(scored, key=lambda x: x['viral_score'], reverse=True)
```

**Files to create/modify:**
- CREATE: `services/ai/clip_scorer.py`
- MODIFY: `services/core/job_runner.py` — Tambah step scoring setelah ANALYZING
- MODIFY: `services/core/tasks_stateless.py` — Export scoring function

**Effort:** 4-6 jam  
**Priority:** P1 — HIGH

---

### P2: Clustering/Collections (HIGH impact, MEDIUM effort)

**Problem Statement:**
Video panjang (podcast 2 jam, gaming stream) menghasilkan 5-10 clip yang semua flat. Tidak ada pengelompokan per topik. AutoClip mengelompokkan clip jadi "collections" — misal "Investasi Teknologi", "Tips Karir" — sehingga user bisa publish sebagai series.

**Bagaimana AutoClip Implementasi:**
`step5_clustering.py` menggunakan hybrid approach:
1. **Keyword pre-clustering** — Dictionary-based keyword matching ke 8 tema
2. **LLM clustering** — Kirim hasil pre-cluster ke LLM untuk refinement
3. **Fallback** — Jika LLM gagal, pakai pre-cluster saja

```python
# AutoClip: Hybrid keyword + LLM clustering
theme_keywords = {
    '投资理财': ['投资', '理财', '股票', ...],
    '职场成长': ['职场', '工作', '技能', ...],
    # ... 8 tema
}

# Pre-cluster dulu
pre_clusters = self._pre_cluster_by_keywords(clips)

# LLM refine
response = self.llm_client.call_with_retry(clustering_prompt + clip_data)
collections = self.llm_client.parse_json_response(response)

# Validasi: minimal 2 clip per collection, max 10
validated = self._validate_collections(collections, clips)
```

**Adaptasi untuk ZenClip:**
- Jadikan clustering **optional post-processing**, dipicu oleh flag `enable_clustering: true`
- ZenClip sudah punya genre detection, jadi keyword dictionary bisa dimapping dari genre
- Collections disimpan sebagai metadata, tidak mempengaruhi clip cutting

**Files to create/modify:**
- CREATE: `services/ai/clip_clusterer.py`
- MODIFY: `job_runner.py` — Tambah optional clustering step
- MODIFY: API endpoint — Tambah `enable_clustering` parameter

**Effort:** 8-12 jam  
**Priority:** P2 — HIGH

---

### P3: Content-Type-Specific Scoring (MEDIUM impact, LOW effort)

**Problem Statement:**
ZenClip sudah punya 6 genre prompt (general, podcast, gaming, motivational, comedy, education). Tapi scoring criteria-nya sama untuk semua genre. Podcast gaming butuh scoring berbeda dengan podcast edukasi.

**Bagaimana AutoClip Implementasi:**
AutoClip punya folder per content type (`prompt/business/`, `prompt/entertainment/`, `prompt/speech/`, dll). Setiap folder berisi scoring prompt yang *berbeda* — entertainment prompt fokus ke "entertainment value + star charisma", speech prompt fokus ke "persuasion + insight depth".

**Adaptasi untuk ZenClip:**
Buat variant scoring prompt per genre. ZenClip sudah punya `PromptManager.get_prompts()` dengan key per genre. Tinggal tambahkan `scoring_prompt` per genre.

**Files to create/modify:**
- MODIFY: `services/ai/clip_scorer.py` — Load scoring prompt per video_type
- CREATE: `prompts/scoring/` — Prompt files per genre

**Effort:** 2-3 jam  
**Priority:** P3 — MEDIUM

---

### P4: Separate Title Generation (MEDIUM impact, LOW effort)

**Problem Statement:**
ZenClip hanya generate `viral_caption` (max 10 kata) sebagai bagian dari main LLM call. Ini terlalu pendek untuk konteks yang lebih luas. AutoClip punya `step4_title.py` yang generate judul 15-25 kata secara terpisah, menghasilkan judul yang lebih berkualitas.

**Bagaimana AutoClip Implementasi:**
```python
# step4_title.py — LLM terpisah untuk title generation
# Prompt: "生成1个最佳标题，忠于原文，拒绝夸张，精炼有力"
# Input: clips dengan id, title, content, recommend_reason
# Output: {"id": "judul yang digenerate"}
```

**Adaptasi untuk ZenClip:**
Tambahkan title generation sebagai optional post-processing. Retain `viral_caption` untuk caption pendek, tambahkan `generated_title` untuk judul yang lebih panjang.

```python
# services/ai/title_generator.py
TITLE_PROMPT = """ROLE: Kamu adalah ahli pembuat judul video viral.
TASK: Buat 1 judul terbaik untuk setiap clip video.

PRINSIP:
1. Jujur — judul HARUS sesuai konten, JANGAN berbohong
2. Tidak berlebihan — hindari "MENGAGUMKAN!", "TERBAIK!"
3. Singkat tapi padat — 15-25 kata
4. Hook di awal — kalimat pertama harus bikin penasaran

INPUT: JSON array clips dengan id, topic, reason
OUTPUT: JSON object {"id": "judul"}

CONTOH OUTPUT:
{"0": "Kenapa 90% Orang Gagal Investasi: 3 Kesalahan yang Gua Juga Pernah Buat"}
"""
```

**Files to create/modify:**
- CREATE: `services/ai/title_generator.py`
- MODIFY: `job_runner.py` — Tambah optional title generation
- MODIFY: `ViralClip` model — Tambah field `generated_title`

**Effort:** 3-4 jam  
**Priority:** P4 — MEDIUM

---

### P5: Pipeline Resumability (MEDIUM impact, MEDIUM effort)

**Problem Statement:**
ZenClip sudah punya job-level resumability (cek `video_info.json`, `transcript.json`, `analysis.json`, `clips_result.json`). Tapi tidak ada step-level granularity. Kalau scoring gagal, harus re-run dari awal.

**Bagaimana AutoClip Implementasi:**
AutoClip menyimpan artifact per-step (`step1_outline.json`, `step3_high_score_clips.json`, `step4_titles.json`, dll). Setiap step cek apakah output-nya sudah ada.

**Adaptasi untuk ZenClip:**
ZenClip sudah punya pattern ini di `job_runner.py` (cek `os.path.exists(analysis_path)`). Tinggal extend untuk step baru:

```python
# Tambah di job_runner.py
scoring_path = os.path.join(self.job_dir, "scoring.json")
if os.path.exists(scoring_path):
    clips_data = self._load_artifact("scoring.json")
    log.info(f"Resuming: scoring found", module="JobRunner")
else:
    clips_data = score_step(clips_data, ...)
    self._save_artifact("scoring.json", clips_data)
```

**Files to modify:**
- MODIFY: `services/core/job_runner.py` — Tambah artifact check per step baru

**Effort:** 2-3 jam  
**Priority:** P5 — MEDIUM

---

### P6: Long Video Chunking (MEDIUM impact, HIGH effort)

**Problem Statement:**
Video >60 menit di ZenClip di-sampling secara uniform (setiap Nth phrase). Ini berisiko kehilangan momen penting. AutoClip memecah video jadi chunk 30 menit, lalu proses tiap chunk secara terpisah.

**Bagaimana AutoClip Implementasi:**
```python
# step1_outline.py
chunks = self.text_processor.chunk_srt_data(srt_data, interval_minutes=30)
# Simpan chunk per-file
self._save_chunks_to_files(chunks)
self._save_srt_chunks(chunks)
# Proses tiap chunk dengan LLM terpisah
for chunk_file in chunk_files:
    response = self.llm_client.call_with_retry(prompt, chunk_text)
    outlines.extend(self._parse_outline_response(response, chunk_index))
```

**Adaptasi untuk ZenClip:**
Untuk video >45 menit, split transcript jadi chunk 30 menit. Proses tiap chunk dengan LLM call terpisah, lalu merge hasilnya.

**Files to create/modify:**
- CREATE: `services/ai/transcript_chunker.py`
- MODIFY: `llm_analyzer.py` — Tambah chunking logic untuk video panjang
- MODIFY: `job_runner.py` — Cek durasi video, route ke chunked vs single-call

**Effort:** 12-16 jam  
**Priority:** P6 — MEDIUM (bisa ditunda)

---

### P7: Full Multi-Step Pipeline (HIGH impact, HIGH effort)

**Problem Statement:**
ZenClip melakukan semua dalam 1 LLM call. Untuk video panjang, ini kurang optimal karena prompt terlalu padat dan konteks terlalu besar. AutoClip's 6-step pipeline (outline → timeline → scoring → title → clustering → video) menghasilkan output lebih terstruktur.

**Adaptasi untuk ZenClip:**
JANGAN ganti arsitektur single-call sepenuhnya. Gunakan pendekatan **hybrid**:
- Video pendek (<15 menit): Tetap single-call (sudah bagus)
- Video menengah (15-45 menit): Single-call + post-processing (scoring, title)
- Video panjang (>45 menit): Multi-step pipeline dengan chunking

Ini adalah evolusi, bukan revolusi. Lihat ADR-1 di bawah.

**Files to modify:**
- MODIFY: `llm_analyzer.py` — Tambah mode selection
- MODIFY: `job_runner.py` — Route berdasarkan durasi
- CREATE: `services/ai/pipeline_modes.py` — Mode selector

**Effort:** 16-24 jam  
**Priority:** P7 — HIGH (tapi Phase 3, setelah quick wins)

---

## 4. Implementation Roadmap

### Phase 1: Quick Wins (1-2 minggu)
**Fitur:** P1 (Scoring) + P3 (Type-Specific Scoring) + P4 (Title Generation)

**Target:** Tambah scoring dan title generation tanpa mengubah core flow.

```
BEFORE:
Transcript → [Single LLM Call] → Raw Clips → Cutting → Done

AFTER Phase 1:
Transcript → [Single LLM Call] → Raw Clips → [Score Post-Process] → [Title Gen] → Cutting → Done
```

### Phase 2: Organization (2-3 minggu)
**Fitur:** P2 (Clustering) + P5 (Resumability)

**Target:** Tambah pengelompokan clip dan step-level resume.

```
AFTER Phase 2:
Transcript → [LLM] → Raw Clips → [Score] → [Title] → [Cluster (opt)] → [Cut] → Done
                                                    └── Each step saves artifact
```

### Phase 3: Scale (3-4 minggu)
**Fitur:** P6 (Chunking) + P7 (Multi-Step Pipeline)

**Target:** Dukung video panjang dengan pipeline multi-step.

```
AFTER Phase 3 (Short video, <15min):
Transcript → [Single LLM] → Clips → [Score] → [Title] → [Cut]

AFTER Phase 3 (Long video, >45min):
Transcript → [Chunk 30min] → [Per-chunk: LLM] → [Merge] → [Score] → [Title] → [Cluster] → [Cut]
```

---

## 5. Per-Phase Technical Spec

### Phase 1 Technical Spec

#### New Files to Create

**`backend/src/services/ai/clip_scorer.py`**
```python
"""
Clip Scorer — Post-processing scoring untuk clip ZenClip.
Menggunakan LLM terpisah untuk memberi skor viral potential.
"""

import json
import logging
from typing import List, Dict, Optional
from services.ai.llm_provider import generate_llm_response

logger = logging.getLogger(__name__)

# --- Scoring Prompt Template ---

BASE_SCORING_PROMPT = """ROLE: Kamu adalah ahli analisis konten viral untuk platform Short/Reels/TikTok.

TASK: Berikan skor viral potential (0.0-1.0) untuk setiap clip video berdasarkan 4 kriteria bobot:
1. EMOTIONAL HOOK (bobot 30%): Apakah clip ini bisa trigger emosi kuat dalam 3 detik pertama?
2. VIRAL SHAREABILITY (bobot 25%): Apakah ada quotable moment atau "wow factor" yang bikin orang share?
3. INFORMATION DENSITY (bobot 25%): Apakah kontennya padat informasi/insight, bukan filler?
4. STRUCTURAL COMPLETENESS (bobot 20%): Apakah clip ini punya awal-tengah-akhir yang jelas?

INPUT FORMAT: JSON array clips.
OUTPUT FORMAT: JSON array dengan tambahan field "viral_score" (0.0-1.0) dan "score_reason" (1 kalimat).

CONTOH INPUT:
[{"id": "0", "topic": "Kenapa orang gagal investasi", "reason": "Strong hook tentang 90% orang salah", "duration": 45}]

CONTOH OUTPUT:
[{"id": "0", "topic": "Kenapa orang gagal investasi", "reason": "Strong hook tentang 90% orang salah", "duration": 45, "viral_score": 0.85, "score_reason": "Hook kuat + statistik shocking + payoff jelas"}]

PENTING: Output HANYA JSON array. Tidak ada penjelasan tambahan."""

PODCAST_SCORING_ADDON = """
KONTEKS TAMBAHAN (Podcast):
- Nilai lebih tinggi untuk: quote menarik dari narasumber, momen "mind-blown", insight langka
- Nilai lebih rendah untuk: pembukaan basi, recap yang tidak perlu, konten filler
- Podcast viral biasanya punya 1 kalimat yang "bikin orang berhenti scroll" """

GAMING_SCORING_ADDON = """
KONTEKS TAMBAHAN (Gaming):
- Nilai lebih tinggi untuk: clutch moment, reaksi ekstrem, fail lucu, skill tinggi
- Nilai lebih rendah untuk: grinding monoton, loading screen, setup yang panjang
- Gaming viral = visual + reaksi + momen tak terduga"""

EDUCATION_SCORING_ADDON = """
KONTEKS TAMBAHAN (Education):
- Nilai lebih tinggi untuk: "Aha! moment", mitos yang dibantah, tips langsung pakai
- Nilai lebih rendah untuk: teori tanpa contoh, penjelasan bertele-tele, konten terlalu teknis
- Education viral = "Wait, really?" moment + actionable takeaway"""

MOTIVATIONAL_SCORING_ADDON = """
KONTEKS TAMBAHAN (Motivational):
- Nilai lebih tinggi untuk: kutipan bijak yang powerful, cerita zero-to-hero, wake-up call
- Nilai lebih rendah untuk: platitudes, motivasi kosong tanpa substansi
- Motivational viral = kalimat yang bisa dijadikan quote poster"""

COMEDY_SCORING_ADDON = """
KONTEKS TAMBAHAN (Comedy):
- Nilai lebih tinggi untuk: punchline tak terduga, timing komedi sempurna, reaksi natural
- Nilai lebih rendah untuk: joke yang terlalu dipaksakan, komedi cringe, setup terlalu panjang
- Comedy viral = "tawa yang menular" + relatable"""

SCORING_PROMPTS = {
    'general': BASE_SCORING_PROMPT,
    'podcast': BASE_SCORING_PROMPT + PODCAST_SCORING_ADDON,
    'gaming': BASE_SCORING_PROMPT + GAMING_SCORING_ADDON,
    'education': BASE_SCORING_PROMPT + EDUCATION_SCORING_ADDON,
    'motivational': BASE_SCORING_PROMPT + MOTIVATIONAL_SCORING_ADDON,
    'comedy': BASE_SCORING_PROMPT + COMEDY_SCORING_ADDON,
}


class ClipScorer:
    def __init__(self, api_key: str = None, provider: str = 'deepseek'):
        self.api_key = api_key
        self.provider = provider
    
    def score_clips(
        self,
        clips: List[Dict],
        video_type: str = 'general',
        check_cancelled=None
    ) -> List[Dict]:
        """
        Score clip yang sudah ada. Tambahkan viral_score dan score_reason.
        
        Args:
            clips: List of clip dicts dari analyze_transcript_with_llm
            video_type: Genre video (general, podcast, gaming, etc)
            check_cancelled: Callback untuk cek cancellation
        
        Returns:
            Clips dengan tambahan viral_score dan score_reason, sorted by score desc
        """
        if not clips:
            return clips
        
        if check_cancelled and check_cancelled():
            raise Exception("Job Cancelled")
        
        # Siapkan input
        clips_input = []
        for i, clip in enumerate(clips):
            clips_input.append({
                "id": str(i),
                "topic": clip.get("topic", ""),
                "reason": clip.get("reason", ""),
                "duration": round(clip.get("end_time", 0) - clip.get("start_time", 0), 1)
            })
        
        prompt_text = json.dumps(clips_input, ensure_ascii=False, indent=2)
        system_prompt = SCORING_PROMPTS.get(video_type, BASE_SCORING_PROMPT)
        
        logger.info(f"Scoring {len(clips)} clips (type={video_type}) via {self.provider}")
        
        try:
            response = generate_llm_response(
                prompt=prompt_text,
                system_instruction=system_prompt,
                api_key=self.api_key,
                provider=self.provider,
                temperature=0.2
            )
            
            # Parse response
            scored_data = self._parse_scoring_response(response)
            
            # Merge scores ke clips asli
            for i, clip in enumerate(clips):
                clip_id = str(i)
                if clip_id in scored_data:
                    clip['viral_score'] = scored_data[clip_id].get('viral_score', 0.5)
                    clip['score_reason'] = scored_data[clip_id].get('score_reason', 'Scoring failed')
                else:
                    clip['viral_score'] = 0.5  # Default middle score
                    clip['score_reason'] = 'Scoring unavailable'
            
            # Sort by score descending
            clips.sort(key=lambda x: x.get('viral_score', 0), reverse=True)
            logger.info(f"Scoring complete. Top clip: {clips[0].get('viral_score', 0):.2f}")
            
            return clips
            
        except Exception as e:
            logger.error(f"Scoring failed: {e}. Using default scores.")
            for clip in clips:
                clip['viral_score'] = 0.5
                clip['score_reason'] = f'Scoring failed: {str(e)[:50]}'
            return clips
    
    def _parse_scoring_response(self, response: str) -> Dict:
        """Parse LLM scoring response."""
        import re
        clean = response.replace("```json", "").replace("```", "").strip()
        
        try:
            data = json.loads(clean)
            if isinstance(data, list):
                return {str(item.get('id', i)): item for i, item in enumerate(data)}
            elif isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
        
        # Fallback: regex
        pattern = r'"id"\s*:\s*"(\d+)"[^}]*"viral_score"\s*:\s*([\d.]+)'
        matches = re.findall(pattern, response)
        result = {}
        for clip_id, score in matches:
            result[clip_id] = {'viral_score': float(score), 'score_reason': 'Parsed from fallback'}
        return result


def score_clips(
    clips: List[Dict],
    video_type: str = 'general',
    api_key: str = None,
    provider: str = 'deepseek',
    check_cancelled=None
) -> List[Dict]:
    """Convenience function."""
    scorer = ClipScorer(api_key=api_key, provider=provider)
    return scorer.score_clips(clips, video_type, check_cancelled)
```

**`backend/src/services/ai/title_generator.py`**
```python
"""
Title Generator — Generate judul YouTube-quality untuk clip.
Terpisah dari viral_caption (pendek) — ini lebih panjang dan deskriptif.
"""

import json
import logging
from typing import List, Dict, Optional
from services.ai.llm_provider import generate_llm_response

logger = logging.getLogger(__name__)

TITLE_PROMPT = """ROLE: Kamu adalah ahli pembuat judul video viral untuk YouTube/TikTok.

TASK: Buat 1 judul TERBAIK untuk setiap clip. Judul harus:
1. JUJUR — harus sesuai konten clip, JANGAN berbohong atau exaggerate
2. SINGKAT PADAT — 15-25 kata, tidak lebih
3. HOOK DI AWAL — kata pertama harus bikin penasaran
4. SPESIFIK — sebutkan topik/angka/nama, bukan generik
5. BAHASA — sesuai bahasa clip (Indonesia/English)

HINDARI:
- "MENGAGUMKAN!", "TERBAIK!", "WAJIB TONTON!" — klikbait murahan
- Judul yang terlalu panjang (>25 kata)
- Bahasa campur aduk (Indo-English tanpa alasan)

INPUT: JSON array clips dengan id, topic, reason, viral_score
OUTPUT: JSON object {"id": "judul"}

CONTOH OUTPUT:
{
  "0": "Kenapa 90% Orang Gagal Investasi: 3 Kesalahan yang Gua Juga Pernah Buat",
  "1": "Cara Dapat Kerja Tanpa Pengalaman: Tips dari HRD yang Jarang Orang Tahu",
  "2": "Detik-Detik Clutch Mustahil di Final: Audience Tidak Menyangka Ini Bisa Terjadi"
}

OUTPUT HANYA JSON OBJECT. Tidak ada penjelasan tambahan."""


class TitleGenerator:
    def __init__(self, api_key: str = None, provider: str = 'deepseek'):
        self.api_key = api_key
        self.provider = provider
    
    def generate_titles(
        self,
        clips: List[Dict],
        language: str = 'en',
        check_cancelled=None
    ) -> List[Dict]:
        """
        Generate title untuk setiap clip.
        
        Args:
            clips: List of clip dicts (harus sudah punya viral_score)
            language: Bahasa output ('en', 'id', dll)
            check_cancelled: Cancellation callback
        
        Returns:
            Clips dengan tambahan generated_title
        """
        if not clips:
            return clips
        
        if check_cancelled and check_cancelled():
            raise Exception("Job Cancelled")
        
        # Siapkan input
        clips_input = []
        for i, clip in enumerate(clips):
            clips_input.append({
                "id": str(i),
                "topic": clip.get("topic", ""),
                "reason": clip.get("reason", ""),
                "viral_score": clip.get("viral_score", 0.5)
            })
        
        prompt_text = json.dumps(clips_input, ensure_ascii=False, indent=2)
        
        # Tambah bahasa instruction
        lang_instruction = f"\n\nBAHASA OUTPUT: {language.upper()}"
        if language in ['id', 'indonesian', 'indonesia']:
            lang_instruction += "\nTulis judul dalam Bahasa Indonesia yang natural."
        
        full_prompt = TITLE_PROMPT + lang_instruction
        
        logger.info(f"Generating titles for {len(clips)} clips via {self.provider}")
        
        try:
            response = generate_llm_response(
                prompt=prompt_text,
                system_instruction=full_prompt,
                api_key=self.api_key,
                provider=self.provider,
                temperature=0.4  # Sedikit lebih kreatif dari scoring
            )
            
            titles = self._parse_title_response(response)
            
            for i, clip in enumerate(clips):
                clip_id = str(i)
                clip['generated_title'] = titles.get(clip_id, clip.get('topic', f'Clip {i+1}'))
            
            logger.info(f"Title generation complete")
            return clips
            
        except Exception as e:
            logger.error(f"Title generation failed: {e}. Using topic as fallback.")
            for i, clip in enumerate(clips):
                clip['generated_title'] = clip.get('topic', f'Clip {i+1}')
            return clips
    
    def _parse_title_response(self, response: str) -> Dict:
        """Parse LLM title response."""
        import re
        clean = response.replace("```json", "").replace("```", "").strip()
        
        try:
            data = json.loads(clean)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except json.JSONDecodeError:
            pass
        
        # Fallback: try to extract "id": "title" patterns
        pattern = r'"(\d+)"\s*:\s*"([^"]+)"'
        matches = re.findall(pattern, clean)
        return {clip_id: title for clip_id, title in matches}


def generate_titles(
    clips: List[Dict],
    language: str = 'en',
    api_key: str = None,
    provider: str = 'deepseek',
    check_cancelled=None
) -> List[Dict]:
    """Convenience function."""
    gen = TitleGenerator(api_key=api_key, provider=provider)
    return gen.generate_titles(clips, language, check_cancelled)
```

#### Existing Files to Modify

**`services/core/job_runner.py`** — Tambah scoring dan title step:

```python
# Di dalam method run(), setelah step ANALYZING:

# 3.5 SCORING (Post-processing)
scoring_path = os.path.join(self.job_dir, "scoring.json")
if os.path.exists(scoring_path):
    clips_data = self._load_artifact("scoring.json")
    log.info(f"Resuming: scoring found", module="JobRunner")
else:
    from services.ai.clip_scorer import score_clips as score_clips_fn
    clips_data = score_clips_fn(
        clips_data,
        video_type=data.get('video_type', 'general'),
        api_key=data.get('api_key'),
        provider=data.get('api_provider', 'deepseek'),
        check_cancelled=self._is_cancelled
    )
    self._save_artifact("scoring.json", clips_data)

# 3.6 TITLE GENERATION (Post-processing)
title_path = os.path.join(self.job_dir, "titles.json")
if os.path.exists(title_path):
    clips_data = self._load_artifact("titles.json")
    log.info(f"Resuming: titles found", module="JobRunner")
else:
    from services.ai.title_generator import generate_titles as gen_titles_fn
    clips_data = gen_titles_fn(
        clips_data,
        language=language,
        api_key=data.get('api_key'),
        provider=data.get('api_provider', 'deepseek'),
        check_cancelled=self._is_cancelled
    )
    self._save_artifact("titles.json", clips_data)
```

**`services/ai/llm_analyzer.py`** — Update ViralClip model:

```python
class ViralClip(BaseModel):
    # ... existing fields ...
    
    # New fields (optional, populated by post-processing)
    viral_score: Optional[float] = Field(default=None, ge=0, le=1)
    score_reason: Optional[str] = None
    generated_title: Optional[str] = None
    collection_id: Optional[str] = None
```

#### Data Structures / JSON Schemas

**Output `scoring.json`:**
```json
[
  {
    "start_time": 12.5,
    "end_time": 55.2,
    "topic": "Kenapa orang gagal investasi",
    "reason": "Hook kuat + statistik shocking",
    "viral_caption": "Wait for the end...",
    "hook_heading": "MONEY TRAP",
    "hook_subheading": "90% salah",
    "hook_top_text": "WATCH THIS",
    "viral_score": 0.85,
    "score_reason": "Hook kuat tentang 90% orang salah + statistik shocking + payoff jelas"
  },
  {
    "start_time": 120.0,
    "end_time": 155.5,
    "topic": "Tips karir dari CEO",
    "reason": "Insight langka dari pengalaman nyata",
    "viral_caption": "CEO spills the tea",
    "hook_heading": "CEO SECRET",
    "hook_subheading": "Rare advice",
    "hook_top_text": "LISTEN UP",
    "viral_score": 0.72,
    "score_reason": "Insight unik tapi hook agak lambat di 5 detik pertama"
  }
]
```

**Output `titles.json`:**
```json
[
  {
    "start_time": 12.5,
    "end_time": 55.2,
    "topic": "Kenapa orang gagal investasi",
    "viral_score": 0.85,
    "generated_title": "Kenapa 90% Orang Gagal Investasi: 3 Kesalahan yang Gua Juga Pernah Buat"
  }
]
```

#### API Changes

```python
# Di app.py, endpoint POST /api/process:
# Tambah parameter opsional:
{
    "enable_scoring": true,       # default: true (Phase 1 onward)
    "enable_title_gen": true,     # default: true (Phase 1 onward)
    "min_score_threshold": 0.5,   # default: 0.0 (no filter) — bisa di-set user
    "enable_clustering": false    # default: false (Phase 2 onward)
}

# Response clips akan punya field baru:
{
    "clips": [
        {
            "start_time": 12.5,
            "end_time": 55.2,
            "viral_score": 0.85,
            "score_reason": "...",
            "generated_title": "...",
            "collection_id": null  // atau "1" jika clustering enabled
        }
    ]
}
```

#### Testing Strategy

```python
# tests/test_clip_scorer.py

def test_scorer_parses_valid_response():
    """Test parsing LLM scoring response."""
    scorer = ClipScorer()
    response = '[{"id": "0", "viral_score": 0.85, "score_reason": "Great hook"}]'
    result = scorer._parse_scoring_response(response)
    assert result["0"]["viral_score"] == 0.85

def test_scorer_handles_invalid_response():
    """Test fallback when LLM returns garbage."""
    scorer = ClipScorer()
    clips = [{"start_time": 0, "end_time": 30, "topic": "test"}]
    result = scorer.score_clips(clips, "general")
    assert result[0]["viral_score"] == 0.5  # Default fallback

def test_scorer_sorts_by_score():
    """Test clips sorted by viral_score desc."""
    scorer = ClipScorer()
    clips = [
        {"start_time": 0, "end_time": 30, "topic": "low"},
        {"start_time": 30, "end_time": 60, "topic": "high"}
    ]
    # Mock LLM response
    # ... verify high-score clip is first

# tests/test_title_generator.py

def test_title_generator_uses_topic_as_fallback():
    """Test fallback to topic when LLM fails."""
    gen = TitleGenerator()
    clips = [{"start_time": 0, "end_time": 30, "topic": "Original Topic"}]
    result = gen.generate_titles(clips, "en")
    assert result[0]["generated_title"] == "Original Topic"
```

---

### Phase 2 Technical Spec

#### New Files to Create

**`backend/src/services/ai/clip_clusterer.py`**
```python
"""
Clip Clusterer — Mengelompokkan clip berdasarkan tema/konten.
Hybrid approach: keyword pre-clustering + LLM refinement.
"""

import json
import logging
from typing import List, Dict, Optional, Set
from collections import defaultdict
from services.ai.llm_provider import generate_llm_response

logger = logging.getLogger(__name__)

# Keyword dictionary — bisa diperluas
# Mapping dari genre ZenClip ke tema cluster
CLUSTER_KEYWORDS = {
    'finance_investment': {
        'keywords': ['investasi', 'saham', 'trading', 'uang', 'keuangan', 'crypto', 'reksadana',
                      'profit', 'loss', 'portfolio', 'dividen', 'ipo', 'bank', 'pinjaman',
                      'investment', 'stock', 'money', 'finance', 'trading', 'crypto'],
        'title': 'Investasi & Keuangan',
        'description': 'Diskusi seputar strategi investasi, saham, dan manajemen keuangan'
    },
    'career_growth': {
        'keywords': ['karir', 'kerja', 'skill', 'belajar', 'cv', 'interview', 'gaji',
                      'promotion', 'leadership', 'career', 'job', 'resume', 'salary'],
        'title': 'Karir & Pengembangan Diri',
        'description': 'Tips karir, skill development, dan pengalaman profesional'
    },
    'tech_digital': {
        'keywords': ['AI', 'teknologi', 'programming', 'app', 'software', 'startup',
                      'coding', 'developer', 'digital', 'data', 'machine learning', 'robot'],
        'title': 'Teknologi & Digital',
        'description': 'Tren teknologi, programming, dan ekosistem digital'
    },
    'lifestyle_health': {
        'keywords': ['kesehatan', 'olahraga', 'diet', 'mental', 'workout', 'fitness',
                      'health', 'exercise', 'meditasi', 'yoga', 'tidur', 'makanan sehat'],
        'title': 'Gaya Hidup & Kesehatan',
        'description': 'Tips kesehatan, fitness, dan wellness'
    },
    'entertainment_gaming': {
        'keywords': ['game', 'gaming', 'film', 'musik', 'anime', 'streaming',
                      'esport', 'console', 'PC gaming', 'mobile game', 'review film'],
        'title': 'Hiburan & Gaming',
        'description': 'Review game, diskusi hiburan, dan momen gaming viral'
    },
    'relationship_social': {
        'keywords': ['pacar', 'relationship', 'nikah', 'keluarga', 'teman', 'dating',
                      'marriage', 'friendship', 'social', 'komunikasi', 'konflik'],
        'title': 'Relasi & Sosial',
        'description': 'Diskusi relationship, dinamika sosial, dan komunikasi interpersonal'
    },
    'education_knowledge': {
        'keywords': ['belajar', 'sains', 'sejarah', 'pendidikan', 'fakta', 'riset',
                      'science', 'history', 'education', 'research', 'university', 'study'],
        'title': 'Edukasi & Pengetahuan',
        'description': 'Fakta menarik, penjelasan sains, dan konten edukatif'
    }
}

CLUSTERING_PROMPT = """ROLE: Kamu adalah ahli pengelompokan konten video.

TASK: Kelompokkan clip video berikut ke dalam koleksi/series berdasarkan tema.

ATURAN:
1. Setiap koleksi minimal 2 clip, maksimal 8 clip
2. Clip yang tidak cocok ke koleksi manapun, biarkan tanpa collection_id
3. Nama koleksi harus spesifik dan menarik (bukan generik seperti "Koleksi 1")
4. Deskripsi koleksi maksimal 50 kata

INPUT: JSON array clips dengan id, topic, reason, viral_score
OUTPUT: JSON array collections

FORMAT OUTPUT:
[
  {
    "collection_id": "finance_01",
    "collection_title": "Rahasia Investasi untuk Pemula",
    "collection_description": "3 clip tentang kesalahan umum investor pemula",
    "clip_ids": ["0", "2", "5"]
  }
]

OUTPUT HANYA JSON ARRAY. Tidak ada penjelasan tambahan."""


class ClipClusterer:
    def __init__(self, api_key: str = None, provider: str = 'deepseek'):
        self.api_key = api_key
        self.provider = provider
    
    def cluster_clips(
        self,
        clips: List[Dict],
        check_cancelled=None
    ) -> Dict[str, Dict]:
        """
        Kelompokkan clip ke dalam collections.
        
        Returns:
            Dict mapping collection_id -> collection metadata
        """
        if len(clips) < 4:
            logger.info(f"Too few clips ({len(clips)}) for clustering, skipping")
            return {}
        
        if check_cancelled and check_cancelled():
            raise Exception("Job Cancelled")
        
        # Step 1: Keyword pre-clustering
        pre_clusters = self._pre_cluster_by_keywords(clips)
        
        # Step 2: LLM refinement
        try:
            clips_input = []
            for i, clip in enumerate(clips):
                clips_input.append({
                    "id": str(i),
                    "topic": clip.get("topic", ""),
                    "reason": clip.get("reason", ""),
                    "viral_score": clip.get("viral_score", 0)
                })
            
            # Tambah pre-cluster info ke prompt
            pre_cluster_info = ""
            if pre_clusters:
                pre_cluster_info = "\n\nREFERENSI PRE-CLUSTERING (opsional):\n"
                for theme, data in pre_clusters.items():
                    pre_cluster_info += f"- {data['title']}: clip IDs {data['clip_ids']}\n"
            
            prompt_text = json.dumps(clips_input, ensure_ascii=False, indent=2)
            
            response = generate_llm_response(
                prompt=prompt_text,
                system_instruction=CLUSTERING_PROMPT + pre_cluster_info,
                api_key=self.api_key,
                provider=self.provider,
                temperature=0.2
            )
            
            collections = self._parse_clustering_response(response, clips)
            
            if len(collections) >= 1:
                logger.info(f"LLM clustering: {len(collections)} collections created")
                return collections
            
        except Exception as e:
            logger.warning(f"LLM clustering failed: {e}, using pre-clusters")
        
        # Step 3: Fallback ke pre-clusters
        return self._create_collections_from_pre_clusters(pre_clusters, clips)
    
    def _pre_cluster_by_keywords(self, clips: List[Dict]) -> Dict[str, Dict]:
        """Keyword-based pre-clustering."""
        clusters = {}
        
        for theme_key, theme_data in CLUSTER_KEYWORDS.items():
            matched_ids = []
            for i, clip in enumerate(clips):
                text = f"{clip.get('topic', '')} {clip.get('reason', '')}".lower()
                score = sum(1 for kw in theme_data['keywords'] if kw.lower() in text)
                if score >= 2:  # Minimal 2 keyword match
                    matched_ids.append(str(i))
            
            if len(matched_ids) >= 2:
                clusters[theme_key] = {
                    'title': theme_data['title'],
                    'description': theme_data['description'],
                    'clip_ids': matched_ids
                }
        
        return clusters
    
    def _create_collections_from_pre_clusters(self, pre_clusters: Dict, clips: List[Dict]) -> Dict[str, Dict]:
        """Convert pre-clusters to collection format."""
        collections = {}
        for theme_key, data in pre_clusters.items():
            cid = f"{theme_key}_01"
            collections[cid] = {
                'collection_id': cid,
                'collection_title': data['title'],
                'collection_description': data['description'],
                'clip_ids': data['clip_ids']
            }
        return collections
    
    def _parse_clustering_response(self, response: str, clips: List[Dict]) -> Dict[str, Dict]:
        """Parse LLM clustering response."""
        clean = response.replace("```json", "").replace("```", "").strip()
        
        try:
            data = json.loads(clean)
            if isinstance(data, list):
                collections = {}
                for coll in data:
                    cid = coll.get('collection_id', f"coll_{len(collections)}")
                    collections[cid] = {
                        'collection_id': cid,
                        'collection_title': coll.get('collection_title', 'Untitled'),
                        'collection_description': coll.get('collection_description', ''),
                        'clip_ids': coll.get('clip_ids', [])
                    }
                return collections
        except json.JSONDecodeError:
            pass
        
        return {}
    
    def assign_collection_ids(self, clips: List[Dict], collections: Dict[str, Dict]) -> List[Dict]:
        """Assign collection_id ke setiap clip."""
        # Build reverse mapping: clip_id -> collection_id
        clip_to_collection = {}
        for cid, coll_data in collections.items():
            for clip_id in coll_data.get('clip_ids', []):
                clip_to_collection[clip_id] = cid
        
        for i, clip in enumerate(clips):
            clip['collection_id'] = clip_to_collection.get(str(i))
        
        return clips


def cluster_clips(
    clips: List[Dict],
    api_key: str = None,
    provider: str = 'deepseek',
    check_cancelled=None
) -> tuple:
    """
    Convenience function.
    Returns: (clips_with_collection_ids, collections_dict)
    """
    clusterer = ClipClusterer(api_key=api_key, provider=provider)
    collections = clusterer.cluster_clips(clips, check_cancelled)
    clips = clusterer.assign_collection_ids(clips, collections)
    return clips, collections
```

#### Data Structures / JSON Schemas

**Output `collections.json`:**
```json
{
  "finance_01": {
    "collection_id": "finance_01",
    "collection_title": "Rahasia Investasi untuk Pemula",
    "collection_description": "3 clip tentang kesalahan umum investor pemula yang hampir semua orang buat",
    "clip_ids": ["0", "2", "5"]
  },
  "career_01": {
    "collection_id": "career_01",
    "collection_title": "Tips Karir dari Praktisi",
    "collection_description": "Pengalaman nyata dari profesional tentang cara naik karir",
    "clip_ids": ["1", "3"]
  }
}
```

---

### Phase 3 Technical Spec

#### New Files to Create

**`backend/src/services/ai/transcript_chunker.py`**
```python
"""
Transcript Chunker — Split transcript panjang jadi chunk untuk processing terpisah.
Digunakan untuk video >45 menit.
"""

import logging
from typing import List, Dict, Tuple

logger = logging.getLogger(__name__)

CHUNK_DURATION_SECONDS = 30 * 60  # 30 menit per chunk
OVERLAP_SECONDS = 60  # 1 menit overlap antar chunk untuk konteks


class TranscriptChunker:
    def __init__(self, chunk_duration: int = CHUNK_DURATION_SECONDS, overlap: int = OVERLAP_SECONDS):
        self.chunk_duration = chunk_duration
        self.overlap = overlap
    
    def should_chunk(self, transcript: List[Dict]) -> bool:
        """Cek apakah transcript perlu di-chunk."""
        if not transcript:
            return False
        total_duration = transcript[-1].get('e', transcript[-1].get('end_time', 0))
        return total_duration > self.chunk_duration
    
    def chunk_transcript(self, transcript: List[Dict]) -> List[List[Dict]]:
        """
        Split transcript jadi chunk berdasarkan durasi.
        
        Returns:
            List of transcript chunks, each with metadata.
        """
        if not self.should_chunk(transcript):
            return [{'index': 0, 'start': 0, 'end': total_duration(transcript), 'data': transcript}]
        
        total_duration = transcript[-1].get('e', transcript[-1].get('end_time', 0))
        chunks = []
        
        chunk_start = 0
        chunk_index = 0
        
        while chunk_start < total_duration:
            chunk_end = chunk_start + self.chunk_duration
            
            # Find phrases within this range
            chunk_data = []
            for phrase in transcript:
                phrase_end = phrase.get('e', phrase.get('end_time', 0))
                phrase_start = phrase.get('s', phrase.get('start_time', 0))
                
                # Include phrase if it overlaps with chunk range
                # Include overlap from previous chunk
                effective_start = max(0, chunk_start - self.overlap) if chunk_index > 0 else 0
                if phrase_start < chunk_end and phrase_end > effective_start:
                    chunk_data.append(phrase)
            
            if chunk_data:
                chunks.append({
                    'index': chunk_index,
                    'start': chunk_start,
                    'end': min(chunk_end, total_duration),
                    'data': chunk_data
                })
            
            chunk_start = chunk_end
            chunk_index += 1
        
        logger.info(f"Chunked transcript into {len(chunks)} chunks")
        return chunks


def total_duration(transcript: List[Dict]) -> float:
    """Get total duration of transcript."""
    if not transcript:
        return 0
    return transcript[-1].get('e', transcript[-1].get('end_time', 0))
```

**`backend/src/services/ai/pipeline_modes.py`**
```python
"""
Pipeline Mode Selector — Memilih pipeline mode berdasarkan input.

MODES:
- SINGLE_CALL: Video pendek (<15 min), 1 LLM call
- ENHANCED: Video menengah (15-45 min), 1 call + post-processing
- MULTI_STEP: Video panjang (>45 min), chunked multi-step
"""

import logging
from typing import Literal

logger = logging.getLogger(__name__)

PipelineMode = Literal['single_call', 'enhanced', 'multi_step']

SHORT_VIDEO_THRESHOLD = 15 * 60    # 15 menit
LONG_VIDEO_THRESHOLD = 45 * 60     # 45 menit


def select_pipeline_mode(video_duration_seconds: float, enable_post_processing: bool = True) -> PipelineMode:
    """
    Pilih pipeline mode berdasarkan durasi video.
    
    Args:
        video_duration_seconds: Durasi video dalam detik
        enable_post_processing: Apakah post-processing (scoring, title) diaktifkan
    
    Returns:
        Pipeline mode string
    """
    if video_duration_seconds <= SHORT_VIDEO_THRESHOLD:
        mode = 'single_call'
    elif video_duration_seconds <= LONG_VIDEO_THRESHOLD:
        mode = 'enhanced' if enable_post_processing else 'single_call'
    else:
        mode = 'multi_step'
    
    logger.info(f"Pipeline mode: {mode} (duration: {video_duration_seconds:.0f}s)")
    return mode
```

---

## 6. Architecture Decision Records (ADR)

### ADR-1: Keep Single-Call for Short Videos, Add Multi-Step for Long

**Status:** Accepted  
**Context:** ZenClip saat ini menggunakan 1 LLM call untuk semua analisis. AutoClip menggunakan 6 LLM call terpisah. Keduanya punya trade-off.

**Decision:**
- Video <15 menit: Tetap **single-call** (sudah bekerja bagus, latensi rendah, hemat token)
- Video 15-45 menit: Single-call + **post-processing** (scoring + title generation)
- Video >45 menit: **Multi-step pipeline** dengan chunking

**Rationale:**
- Single-call sudah optimal untuk video pendek — tidak ada alasan untuk menambah latency
- Post-processing (scoring/title) tidak memerlukan transcript ulang, jadi latency tambahan minimal
- Video panjang butuh chunking karena context window terbatas dan sampling uniform berisiko

**Consequences:**
- + Latensi rendah untuk use case paling umum (video pendek)
- + Biaya LLM lebih efisien
- + Kompleksitas bertahap, tidak all-or-nothing
- - Perlu maintain 3 code path yang berbeda

---

### ADR-2: Scoring as Post-Processing Step

**Status:** Accepted  
**Context:** Ada dua opsi: (a) Replace LLM's clip selection dengan scoring, atau (b) Tambahkan scoring setelah clip sudah dipilih.

**Decision:** Scoring sebagai **post-processing** yang menambahkan `viral_score` ke clip yang sudah ada. Jangan ganti clip selection logic LLM.

**Rationale:**
- LLM sudah bagus dalam memilih clip yang relevan — scoring menambahkan *perspective* baru, bukan mengganti
- Post-processing berarti scoring gagal = clip tetap ada (dengan default score), bukan error total
- ZenClip's anti-hallucination logic (retry with feedback) tetap berlaku untuk clip selection
- User bisa tetap pakai clip tanpa score kalau scoring dimatikan

**Consequences:**
- + Backward compatible — existing flow tidak berubah
- + Scoring bisa di-toggle on/off
- + Scoring failure tidak break pipeline
- - Tambahan 1 LLM call (tapi promptnya kecil, ~500 tokens)

---

### ADR-3: Clustering as Optional Post-Processing

**Status:** Accepted  
**Context:** AutoClip selalu menjalankan clustering. Tapi tidak semua user ZenClip butuh clustering (misal video pendek 3 clip).

**Decision:** Clustering **optional**, diaktifkan via `enable_clustering: true`. Flat list tetap jadi default.

**Rationale:**
- Clustering hanya berguna kalau ada >=4 clip (minimal 2 per collection)
- Video pendek dengan 2-3 clip tidak perlu clustering
- Keyword dictionary perlu disesuaikan per bahasa (Indo vs English)
- User yang cuma mau cut 3 clip dari podcast tidak peduli dengan collection

**Consequences:**
- + Tidak ada overhead kalau tidak dipakai
- + Flat list tetap jadi default behavior
- - User harus tahu kapan mengaktifkan clustering
- - Keyword dictionary perlu maintenance

---

### ADR-4: Content-Type Detection Reuse ZenClip's Genre System

**Status:** Accepted  
**Context:** ZenClip sudah punya 6 genre: general, podcast, gaming, motivational, comedy, education. AutoClip punya 7 content type: business, content_review, entertainment, experience, knowledge, opinion, speech.

**Decision:** **Pertahankan** genre system ZenClip. Mapping AutoClip's content-type-specific scoring logic ke genre yang sesuai.

**Rationale:**
- Genre ZenClip sudah terintegrasi ke UI dan prompt system
- User sudah familiar dengan pilihan genre
- AutoClip's 7 type sebenarnya bisa di-mapping ke 6 genre ZenClip:
  - business → general (atau tambah 'business' ke ZenClip)
  - content_review → education
  - entertainment → comedy
  - experience → general
  - knowledge → education
  - opinion → podcast (atau general)
  - speech → podcast

**Consequences:**
- + Tidak perlu ubah UI
- + Konsisten dengan existing user experience
- - Beberapa AutoClip type tidak ada mapping 1:1 yang sempurna
- - Opsional: Tambah genre 'business' di masa depan

---

## 7. Risk Assessment

### HIGH Risk

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| LLM scoring tidak konsisten (beda provider beda score) | High | Medium | Gunakan temperature 0.2 untuk scoring. Tambah normalization: z-score relative antar clip dalam batch |
| Scoring LLM call gagal (quota/rate limit) | Medium | Low | Fallback ke default score 0.5. Scoring adalah nice-to-have, bukan critical |
| Keyword clustering tidak akurat untuk bahasa Indonesia campur English | High | Medium | Gunakan bilingual keyword list. LLM refinement sebagai backup |

### MEDIUM Risk

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Multi-step pipeline untuk video panjang makan banyak token | Medium | High | Estimate token dulu sebelum run. Beri warning ke user. Batasi max chunk |
| Breaking change ke ViralClip model | Low | High | Semua field baru optional (default None). Tidak ada required field baru |
| Clustering menghasilkan collection yang terlalu besar/kecil | Medium | Low | Hard limit: min 2, max 8 clip per collection |

### LOW Risk

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Title generation menghasilkan judul yang mirip antar clip | Low | Low | Tambah dedup logic: cek similarity >80% → regenerate |

---

## 8. Success Metrics

### Quantitative Metrics

| Metric | Current | Target (Post-Phase 1) | Target (Post-Phase 3) |
|--------|---------|----------------------|----------------------|
| Avg clip relevance (user rating) | Unknown (no rating) | 3.5/5 | 4.0/5 |
| Scoring consistency (same input → same score ±0.1) | N/A | 80% | 90% |
| Pipeline success rate (no errors) | ~85% | 90% | 95% |
| Long video support (>45 min) | Broken (sampling) | Sampling improved | Full chunking |
| Avg clips per job | 3 (fixed) | 3-10 (scored, user picks) | 3-20 (clustered) |

### Qualitative Metrics

- User bisa melihat *why* sebuah clip dianggap viral (score_reason)
- User bisa publish clip sebagai series/collection
- Judul clip lebih menarik dan tidak klikbait murahan
- Video podcast 2 jam bisa di-proses tanpa kehilangan momen penting

---

## 9. What NOT to Change

Ini adalah keunggulan ZenClip yang **HARUS dipertahankan**:

### 1. Multi-LLM Provider (6 providers + fallback)
AutoClip hanya pakai 1-2 provider (DashScope + OpenAI fallback). ZenClip punya deepseek, openai, gemini, anthropic, local, openrouter — dengan automatic fallback ke OpenRouter. Ini keunggulan kompetitif yang **JANGAN** diubah.

### 2. 8 Subtitle Styles
ZenClip punya 8 subtitle rendering style. AutoClip tidak punya subtitle system. Ini fitur unik ZenClip.

### 3. 4 Hook Presets (preset-1, preset-2, dll)
Hook system ZenClip sudah bagus dengan hook_heading, hook_subheading, hook_top_text, dan preset2_content. AutoClip tidak punya setara.

### 4. Face-Aware Smart Crop
ZenClip punya face detection untuk crop video. AutoClip tidak punya. Pertahankan.

### 5. Anti-Hallucination (Retry with Feedback)
`llm_analyzer.py` punya retry logic dengan feedback ke LLM ketika clip terlalu pendek. Ini sangat efektif dan tidak ada di AutoClip.

### 6. GPU Acceleration
ZenClip mendukung GPU untuk transcription dan video processing. Pertahankan.

### 7. Genre Detection
ZenClip sudah punya genre system yang bekerja. Jangan ganti dengan AutoClip's content type — map saja (lihat ADR-4).

### 8. Minified Transcript Format
Format `{"s": start, "e": end, "t": text}` sudah efisien untuk hemat token. Pertahankan.

---

## Appendix A: File Reference Summary

### ZenClip Files (Current)
```
backend/src/services/
├── ai/
│   ├── llm_analyzer.py          # ~590 LOC, core LLM logic (MODIFY)
│   ├── llm_provider.py          # ~230 LOC, multi-provider (KEEP)
│   ├── clip_scorer.py           # [NEW] Phase 1
│   ├── title_generator.py       # [NEW] Phase 1
│   ├── clip_clusterer.py        # [NEW] Phase 2
│   ├── transcript_chunker.py    # [NEW] Phase 3
│   └── pipeline_modes.py        # [NEW] Phase 3
├── core/
│   ├── job_runner.py            # ~230 LOC, pipeline orchestrator (MODIFY)
│   └── tasks_stateless.py       # Stateless task functions (MODIFY)
```

### AutoClip Files (Reference)
```
backend/pipeline/
├── step1_outline.py    # Outline extraction + chunking (30 min chunks)
├── step2_timeline.py   # Timeline/timestamp alignment
├── step3_scoring.py    # LLM-based scoring (0-10 scale)
├── step4_title.py      # Separate title generation
├── step5_clustering.py # Hybrid keyword + LLM clustering
└── step6_video.py      # Video cutting

backend/prompt/
├── 推荐理由.txt         # Base scoring prompt (4 criteria)
├── 标题生成.txt         # Title generation prompt
├── 主题聚类.txt         # Clustering prompt
├── 大纲.txt             # Outline extraction prompt
├── 时间点.txt           # Timeline alignment prompt
├── collection_title.txt # Collection title prompt
├── entertainment/       # Content-type specific prompts
├── speech/
├── knowledge/
├── business/
├── content_review/
├── experience/
└── opinion/
```

---

## Appendix B: Effort Summary

| Phase | Fitur | Effort (jam) | Dependencies |
|-------|-------|-------------|-------------|
| Phase 1 | P1: Scoring | 4-6 | None |
| Phase 1 | P3: Type-Specific Scoring | 2-3 | P1 |
| Phase 1 | P4: Title Generation | 3-4 | None |
| Phase 1 | **Subtotal** | **9-13** | |
| Phase 2 | P2: Clustering | 8-12 | P1 |
| Phase 2 | P5: Resumability | 2-3 | P1, P4 |
| Phase 2 | **Subtotal** | **10-15** | Phase 1 |
| Phase 3 | P6: Chunking | 12-16 | None |
| Phase 3 | P7: Multi-Step Pipeline | 16-24 | P1-P6 |
| Phase 3 | **Subtotal** | **28-40** | Phase 2 |
| **TOTAL** | | **47-68 jam** | |

---

## Appendix C: Prompt Template Quick Reference

### Scoring Prompt (Base)
Lihat `SCORING_PROMPTS` di `clip_scorer.py` — 4 kriteria weighted: Emotional Hook (30%), Viral Shareability (25%), Information Density (25%), Structural Completeness (20%). Variants per genre: podcast (fokus quote + mind-blown), gaming (fokus clutch + reaksi), education (fokus aha moment), motivational (fokus quote bijak), comedy (fokus punchline).

### Title Generation Prompt
Lihat `TITLE_PROMPT` di `title_generator.py` — 15-25 kata, jujur, tidak klikbait, hook di awal, bahasa sesuai input.

### Clustering Prompt
Lihat `CLUSTERING_PROMPT` di `clip_clusterer.py` — Hybrid keyword pre-clustering + LLM refinement. Min 2, max 8 clip per collection.

---

*Dokumen ini adalah developer handoff. Code snippets bisa langsung dipakai sebagai starting point. Prompt templates sudah diuji pattern-nya dari AutoClip dan diadaptasi untuk konteks ZenClip (Indonesia/English bilingual).*
