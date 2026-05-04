import os
import json
import re
import time
import hashlib
import logging
from typing import List, Dict, Optional, Union, Any, Tuple
from dataclasses import dataclass
from functools import lru_cache
from pydantic import BaseModel, Field, validator, ValidationError as PydanticValidationError

# Configure logging
logger = logging.getLogger(__name__)

# --- Configuration ---

@dataclass
class LLMAnalysisConfig:
    """Configuration for LLM transcript analysis"""
    
    # Token limits per provider
    token_limits: Dict[str, int] = Field(default_factory=lambda: {
        'local': 8000,
        'deepseek': 60000
    })
    
    # Token estimation (if tiktoken unavailable)
    fallback_tokens_per_phrase: int = 50
    
    # Clip duration constraints
    auto_mode_min_duration: int = 40  # seconds
    max_clip_duration: int = 90        # seconds
    duration_validation_tolerance: float = 0.0  # STRICTLY NO UNDER
    
    # Sampling thresholds
    local_llm_sampling_threshold: int = 150  # phrases
    sampling_rate: int = 2  # Take every Nth phrase
    
    # LLM parameters
    base_temperature: float = 0.3
    temperature_increment_per_retry: float = 0.1
    max_retries: int = 2

config = LLMAnalysisConfig()

# --- Custom Exceptions ---

class TranscriptAnalysisError(Exception):
    """Base exception for transcript analysis"""
    pass

class QuotaExceededError(TranscriptAnalysisError):
    """API quota exceeded"""
    def __init__(self, provider: str, reset_time: Optional[str] = None):
        self.provider = provider
        self.reset_time = reset_time
        msg = f"API quota exceeded for {provider}"
        if reset_time:
            msg += f". Resets at {reset_time}"
        super().__init__(msg)

class InvalidResponseError(TranscriptAnalysisError):
    """LLM returned invalid/unparseable response"""
    def __init__(self, raw_response: str, reason: str):
        self.raw_response = raw_response
        self.reason = reason
        super().__init__(f"Invalid LLM response: {reason}")

class ValidationError(TranscriptAnalysisError):
    """Generated clips failed validation"""
    def __init__(self, clips: List[Dict], reason: str):
        self.clips = clips
        self.reason = reason
        super().__init__(f"Clip validation failed: {reason}")

# --- Token Estimation ---

def estimate_tokens_accurate(text: str, model: str = 'gpt-4') -> int:
    """
    Estimate tokens using character count (fallback).
    1 token ≈ 4 characters for English
    """
    # Fallback: character-based estimation
    # Rule of thumb: 1 token ≈ 4 characters for English
    # For Indonesian/mixed: 1 token ≈ 3.5 characters
    return len(text) // 4

#akan di hapus kedepannya karena tidak akan menggunakan fungsi ini


# --- Data Models ---

class ViralClip(BaseModel):
    """Schema for a viral clip"""
    start_time: float = Field(ge=0, description="Start time in seconds")
    end_time: float = Field(ge=0, description="End time in seconds")
    topic: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=1000)
    
    # Optional metadata
    highlight_map: Optional[Dict[str, str]] = Field(default_factory=dict)
    emoji_map: Optional[Dict[str, str]] = Field(default_factory=dict)
    viral_caption: Optional[str] = None
    hook_heading: Optional[str] = None
    hook_subheading: Optional[str] = None
    hook_top_text: Optional[str] = None
    preset2_content: Optional[str] = None
    
    @validator('end_time')
    def end_after_start(cls, v, values):
        if 'start_time' in values and v <= values['start_time']:
            raise ValueError('end_time must be after start_time')
        return v
    
    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

# --- Prompt Management ---

class PromptManager:
    """Centralized prompt management"""

    @staticmethod
    def get_prompts():
        return {
        'general': """FRAMEWORK SELEKSI CLIP VIRAL — UNIVERSAL:

LENGGANG EMOSIONAL (setiap clip WAJIB mengikuti struktur ini):
  HOOK (0-3 detik) → BANGUN TEGANGAN (3-60%) → PEMBUKTIAN/PAYOFF (60-85%) → PENUTUP/CTA (85-100%)

PILIHAN HOOK — Pilih tipe hook yang PALING COCOK dengan konten transkrip:
  • Pertanyaan Kejut: Pertanyaan yang melawan keyakinan umum. Pakai saat transkrip mengandung fakta mengejutkan.
  • Hook Angka: Mulai dengan statistik atau jumlah spesifik. Pakai saat transkrip menyebut angka, persentase, atau peringkat.
  • Kontradiksi: "Semua yang kamu dengar soal X itu salah." Pakai saat transkrip membantah mitos atau menantang konsensus.
  • Sebelum-Sesudah: "Dulu gua X, sekarang Y." Pakai saat transkrip menceritakan transformasi atau perbandingan.
  • Celah Rasa Ingin Tahu: Umbar hasil tanpa revealing. Pakai saat transkrip membangun ke pengungkapan akhir.
  • Nyeri yang Relate: "Pernah ngerasa gitu? Gua juga." Pakai saat transkrip bahas frustrasi yang umum.
  • Ungkap Rahasia: "Ngga ada yang bahas ini tapi..." Pakai saat transkrip share knowledge orang dalam atau fakta tersembunyi.
  • Tantangan Langsung: "Coba ini, bedain gua." Pakai saat transkrip bikin klaim berani atau pernyataan provokatif.

MEKANISME RETENSI — Terapkan minimal 2 per clip:
  • Loop Terbuka: Janjikan di awal, bayar di akhir ("Yang terakhir beneran ubah semuanya")
  • Potong Cliffhanger: Akhiri di tengah pengungkapan atau puncak tegangan
  • Format Daftar/Hitung Mundur: "3 alasan...", "Nomor 1 bakal bikin kaget"
  • Tulang Punggung Cerita: Setup → Konflik → Resolusi
  • Masalah-Solusi: Uraikan sakitnya, jelaskan obatnya
  • Pemutus Pola: Twist tak terduga yang menghancurkan prediksi penonton
  • Callback: Rujuk sesuatu dari awal clip saat penutup

PENANDA VIRAL DALAM TRANSKRIP (prioritaskan sinyal-sinyal ini):
  1. Speaker naikin suara, ketawa, atau tunjukkan emosi kuat
  2. Angka spesifik, data, atau klaim konkret (bukan pernyataan samar)
  3. Twist tak terduga atau kontradiksi terhadap pengetahuan umum
  4. Praktis — penonton bisa langsung pakai
  5. Cerita dengan awal, tengah, dan akhir yang jelas
  6. Opini kontroversial atau memecah belah
  7. Momen yang bikin "wah ini gua banget" """,

        'podcast': """FRAMEWORK SELEKSI CLIP VIRAL — PODCAST/WAWANCARA:

LENGGANG EMOSIONAL (setiap clip WAJIB mengikuti struktur ini):
  HOOK (0-3 detik) → BANGUN TEGANGAN (3-60%) → PEMBUKTIAN/PAYOFF (60-85%) → PENUTUP/CTA (85-100%)

PILIHAN HOOK — Pilih tipe hook yang PALING COCOK dengan konten:
  • Kutipan Kontroversial: Mulai dengan pernyataan paling provokatif dari pembicara
  • Godaan Cerita: "Yang terjadi selanjutnya bikin semua orang di ruangan kaget..."
  • Bom Wawasan: Realisasi yang mengubah cara pandang
  • Pendapat Panas: Opini yang memecah audiens j dua kubu
  • Emosi Mentah: Momen speaker ngedrop topengnya (nangis, marah, rentan)

MEKANISME RETENSI — Terapkan minimal 2 per clip:
  • Busur Pertanyaan-Jawaban: Host nanya tajam → tamu jawab di luar dugaan
  • Tulang Punggung Cerita: Anekdot personal dengan konflik dan resolusi jelas
  • Tegangan Debat: Dua pandangan berbenturan, penonton milih sisi
  • Jatuhkan Rahasia: Knowledge orang dalam atau reveal di balik layar
  • Puncak Emosional: Bangun sampai momen kerentanan atau terobosan

PENANDA VIRAL PODCAST DALAM TRANSKRIP:
  1. Kutipan sekuat itu orang screenshot
  2. Ketidaksetujuan atau debat panas antar pembicara
  3. Cerita personal dengan beban emosional (perjuangan, kegagalan, comeback)
  4. Saran kontra-intuitif yang nantang pemikiran mainstream
  5. Insight spesifik yang bisa langsung diterapin (bukan nasihat generik)
  6. Momen autentik — speaker ngedrop persona-polishnya""",

        'gaming': """FRAMEWORK SELEKSI CLIP VIRAL — GAMING:

LENGGUNG EMOSIONAL (setiap clip WAJIB mengikuti struktur ini):
  HOOK (0-3 detik) → BANGUN TEGANGAN (3-60%) → PEMBUKTIAN/PAYOFF (60-85%) → PENUTUP/CTA (85-100%)

PILIHAN HOOK — Pilih tipe hook yang PALING COCOK dengan konten:
  • Momen Mustahil: "Ga mungkin mereka survive ini..." menuju clutch play
  • Hook Rage/Fail: Reaksi ekstrem saat ada yang salah
  • Pamer Skill: Permainan yang absurd presisi atau cepatnya ga manusiawi
  • Penemuan: "Guanya nemu sesuatu yang belom ada yang liat"
  • Setup/Punchline: Gameplay normal yang tiba-tiba jadi kocak brutal

MEKANISME RETENSI — Terapkan minimal 2 per clip:
  • Ramp Tegangan: Situasi makin lama makin desperate
  • Ledakan Payoff: Buildup panjang → resolusi mendadak (clutch, menang, fail)
  • Eskalasi Komedi: Dari buruk → lebih buruk → absurd
  • Godaan Tutorial: "Tonton trik ini" → hasil impresif
  • Nyeri yang Relate: Lag, teammate noob, mekanik ga adil

PENANDA VIRAL GAMING DALAM TRANSKRIP:
  1. Momen berisiko tinggi dengan hasil menang/kalah jelas
  2. Reaksi emosional ekstrem (asli, bukan dipaksain)
  3. Pameran skill yang pemain rata-rata ga bisa replikasi
  4. Glitch atau bug yang bikin komedi tak terduga
  5. Kemenangan comeback melawan semua odds
  6. Momen yang semua gamer pernah alamin (teammate toxic, lag di detik terakhir)""",

        'motivational': """FRAMEWORK SELEKSI CLIP VIRAL — MOTIVASI/SELF-HELP:

LENGGUNG EMOSIONAL (setiap clip WAJIB mengikuti struktur ini):
  HOOK (0-3 detik) → TITIK NYERI (3-40%) → SOLUSI/PERUBAHAN (40-75%) → AJAKAN BERAKSI (75-100%)

PILIHAN HOOK — Pilih tipe hook yang PALING COCOK dengan konten:
  • Tamparan Bangun: Kebenaran keras yang ngekonfrontasi kepasrahan penonton
  • Pergeseran Identitas: "Kamu bukan siapa yang kamu kira..."
  • Cermin Nyeri: Deskripsi struggle penonton yang begitu tepat sampai kerasa personal
  • Hasil Duluan: Tunjukin outcome duluan, baru jelaskan cara dapetinnya
  • Tekanan Waktu: "Kalau kamu ga ubah ini sekarang, 5 tahun lagi kamu bakal..."

MEKANISME RETENSI — Terapkan minimal 2 per clip:
  • Dari Nyeri ke Kuasa: Mulai dari struggle, akhiri dengan transformasi
  • Aksi Spesifik: Satu langkah konkret yang penonton bisa LAKUKIN HARI INI
  • Bukti Cerita: Contoh nyata orang yang udah berhasil melakukan perubahan itu
  • Kontras Emosional: Titik rendah → titik tinggi dalam clip yang sama
  • Tantangan Langsung: "Kalau ini ga relevan buat kamu, scroll aja"

PENANDA VIRAL MOTIVASI DALAM TRANSKRIP:
  1. Kalimat sekuat itu orang baca ulang 3 kali
  2. Spesifik, bukan generik ("bangun jam 5 pagi" bukan "jaga disiplin")
  3. Menyentuh insecurity universal (takut gagal, waktu terbuang, penyesalan)
  4. Kontras sebelum-sesudah yang jelas
  5. Nantang penonton buat langsung ambil aksi
  6. Kerasa personal — kayak speakernya ngomong langsung ke KAMU""",

        'comedy': """FRAMEWORK SELEKSI CLIP VIRAL — KOMEDI/HIBURAN:

LENGGUNG EMOSIONAL (setiap clip WAJIB mengikuti struktur ini):
  SETUP (0-20%) → BANGUN/ESKALASI (20-60%) → PUNCHLINE/REVEAL (60-80%) → TAG/TAWA BONUS (80-100%)

PILIHAN HOOK — Pilih tipe hook yang PALING COCOK dengan konten:
  • Premis Absurd: Mulai situasi yang konyol banget sampai penonton penasaran ujungnya
  • Arah Salah: Setup ekspektasi satu hal, deliver sesuatu yang beda total
  • Momen Karakter: Sifat kepribadian spesifik yang diambil ke level ekstrem
  • Setup yang Relate: "Kita semua pernah di situasi ini..." lalu putar balik
  • Visual Kejut: Sesuatu yang mencolok atau tak terduga di frame pertama

MEKANISME RETENSI — Terapkan minimal 2 per clip:
  • Aturan Komedi 3: Setup → beat serupa → beat ketiga yang tak terduga
  • Eskalasi: Setiap lelucon ngungguli sebelumnya
  • Callback: Rujuk lelucon awal dalam konteks baru
  • Delivery Datarkan: Penyampaian serius untuk konten absurd
  • Punch Timing: Jeda sempurna sebelum punchline

PENANDA VIRAL KOMEDI DALAM TRANSKRIP:
  1. Punchline tak terduga sampai penonton bereaksi fisik (ketawa, kaget, nonton ulang)
  2. Situasi relate yang dibikin absurd
  3. Timing komedi sempurna — jeda, delivery, reaksi
  4. Bisa ditonton ulang — makin lucu kedua kalinya karena detail yang terlewat
  5. Bisa dishare — "Gua harus kirim ini ke [nama orang]"
  6. Reaksi autentik (tawa asli, bukan berakting)""",

        'education': """FRAMEWORK SELEKSI CLIP VIRAL — EDUKASI/TUTORIAL:

LENGGUNG EMOSIONAL (setiap clip WAJIB mengikuti struktur ini):
  HOOK MASALAH (0-5 detik) → KENAPA PENTING (5-20%) → SOLUSI/LANGKAH (20-75%) → HASIL/BUKTI (75-100%)

PILIHAN HOOK — Pilih tipe hook yang PALING COCOK dengan konten:
  • Ungkap Kesalahan: "Berhenti lakuin X — ini kenapa hasilnya hancur"
  • Menang Cepat: "Lakuin ini 30 detik dan liat apa yang terjadi"
  • Pembantah Mitos: "Semua yang kamu pelajarin soal X itu salah"
  • Janji: "Di akhir video ini kamu bakal tau cara..."
  • Perbaikan Mendesak: "Kalau kamu masih lakuin X di tahun ini, kamu tertinggal"

MEKANISME RETENSI — Terapkan minimal 2 per clip:
  • Langkah demi Langkah: Progresi bernomor jelas (1, 2, 3)
  • Bukti Sebelum-Sesudah: Tunjukin masalah → perbaikan → hasil
  • Momen Aha: Bangun ke insight mengejutkan yang reframing topik
  • Takeaway yang Bisa Diterapin: Satu hal spesifik yang penonton bisa langsung lakuin
  • Kesalahan Umum: Tunjukin yang orang salahin, baru cara yang bener

PENANDA VIRAL EDUKASI DALAM TRANSKRIP:
  1. Informasi begitu berguna sampai orang screenshot atau save
  2. Jelasin hal kompleks dalam 60 detik
  3. Bantah mitos yang dipercaya luas dengan bukti
  4. Kasih langkah spesifik yang bisa diterapin (bukan "makan sehat" tapi "makan 30g protein dalam 30 menit bangun tidur")
  5. Demo visual atau contoh yang jelas
  6. Jawab pertanyaan yang penonton ga nyadar mereka punya"""
    }

# --- Core Logic ---

def minify_transcript(transcript_data: List[Dict]) -> List[Dict]:
    """
    Minify transcript data for LLM consumption.
    Removes word-level data and rounds timestamps to save tokens.
    """
    minified = []
    for p in transcript_data:
        # Normalize keys (some transcript formats use 'start_time' vs 'start')
        start = p.get('start') if 'start' in p else p.get('start_time', 0)
        end = p.get('end') if 'end' in p else p.get('end_time', 0)
        text = p.get('text', "")
        
        minified.append({
            "s": round(float(start), 2), # s = start
            "e": round(float(end), 2),   # e = end
            "t": text                    # t = text
        })
    return minified

def smart_sample_transcript(transcript_data: List[Dict], target_phrases: int = 150) -> List[Dict]:
    """Smartly sample transcript if it's too long."""
    if len(transcript_data) <= target_phrases:
        return transcript_data
        
    # Uniform sampling for now, but semantic is better for future
    step = max(1, len(transcript_data) // target_phrases)
    logger.info(f"Sampling transcript: step {step}")
    return transcript_data[::step]

def parse_llm_response(response_text: str) -> List[ViralClip]:
    """
    Parse LLM response with robust extraction and validation.
    """
    # Clean markdown
    response_text = response_text.replace("```json", "").replace("```", "").strip()
    
    # Strategy 1: Direct parse
    try:
        data = json.loads(response_text)
        if isinstance(data, list):
            return [ViralClip(**clip) for clip in data]
    except (json.JSONDecodeError, PydanticValidationError) as e:
        logger.warning(f"Strategy 1 parse failed: {e}")
        pass

    # Strategy 2: Find bounds [ ... ] (Most robust for Lists)
    try:
        start_idx = response_text.find('[')
        end_idx = response_text.rfind(']')
        
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_str = response_text[start_idx : end_idx + 1]
            data = json.loads(json_str)
            if isinstance(data, list):
                return [ViralClip(**clip) for clip in data]
    except (json.JSONDecodeError, PydanticValidationError) as e:
        logger.warning(f"Strategy 2 parse failed: {e}")
        pass
    
    # Strategy 3: Extract JSON array with Regex (Fallback)
    json_pattern = r'\[\s*\{.*?\}\s*(?:,\s*\{.*?\}\s*)*\]'
    matches = re.findall(json_pattern, response_text, re.DOTALL)
    
    for match in matches:
        try:
            data = json.loads(match)
            if isinstance(data, list):
                clips = [ViralClip(**clip) for clip in data]
                if clips: return clips
        except (json.JSONDecodeError, PydanticValidationError) as e:
            logger.warning(f"Strategy 3 match parse failed: {e}")
            continue
            
    # Strategy 3: Individual objects
    object_pattern = r'\{[^{}]*"start_time"[^{}]*\}'
    matches = re.findall(object_pattern, response_text)
    
    clips = []
    for match in matches:
        try:
            clip = ViralClip(**json.loads(match))
            clips.append(clip)
        except (json.JSONDecodeError, PydanticValidationError) as e:
            logger.warning(f"Strategy 4 individual object parse failed: {e}")
            pass
            
    if clips:
        return clips
        
    raise InvalidResponseError(
        raw_response=response_text[:500],
        reason="Could not extract valid JSON array or objects"
    )

def analyze_transcript_with_llm(
    transcript_text: str,
    transcript_data: List[Dict],
    num_clips: int = 3,
    min_duration: Union[int, str] = 30,
    video_type: str = 'general',
    custom_prompt: Optional[str] = None,
    api_key: Optional[str] = None,
    api_provider: str = 'deepseek',
    progress_callback: Optional[Any] = None,

    hook_style: str = 'preset-1',
    language: str = 'en',  # ADDED
    check_cancelled=None
) -> Optional[List[Dict]]:
    """
    Analyze video transcript using LLM to identify viral-worthy segments.
    """
    
    def update_progress(msg, pct=None):
        if progress_callback:
            try:
                # Add 'progress_callback' checks inside call if needed, 
                # but we assume callback handles (msg) or (msg, pct)
                import inspect
                sig = inspect.signature(progress_callback)
                if len(sig.parameters) >= 2:
                    progress_callback(msg, pct)
                else:
                    progress_callback(msg)
            except:
                pass

    # CHECK CANCELLED
    if check_cancelled and check_cancelled():
        logger.info("Analysis cancelled by user")
        raise Exception("Job Cancelled")

    update_progress("Analyzing transcript context...", 0.1)
    
    # Minify first to save tokens
    minified_data = minify_transcript(transcript_data)
    
    # Validate token length based on MINIFIED JSON string
    # We estimate based on json dump length now, more accurate
    minified_json = json.dumps(minified_data, ensure_ascii=False)
    
    # Rough calc: 1 token ~= 3 chars for JSON
    est_prompt_tokens = len(minified_json) // 3
    
    # DeepSeek 128k limit check
    if api_provider == 'deepseek' and est_prompt_tokens > 120000:
        logger.warning(f"Transcript still too long ({est_prompt_tokens} tokens). Sampling...")
        # Emergency sampling
        minified_data = smart_sample_transcript(minified_data, target_phrases=2000) # Reduce to safe phrase count
        minified_json = json.dumps(minified_data, ensure_ascii=False)

    # Determine duration constraints
    actual_min_duration = 30
    if isinstance(min_duration, int):
        actual_min_duration = min_duration
    elif isinstance(min_duration, str) and min_duration == "auto":
        actual_min_duration = 40

    
    # Build Prompt
    prompts = PromptManager.get_prompts()
    
    # Extra instructions for Preset 2 (3-line viral hook)
    preset2_instruction = ""
    if hook_style == 'preset-2':
        preset2_instruction = """
    INSTRUKSI KHUSUS UNTUK 'preset2_content':
    Kamu WAJIB menghasilkan field "preset2_content" untuk setiap clip.
    Konten HARUS mengikuti pola kata ini (Total 8-9 kata):
    - Kata 1-3: Teks biasa (contoh: "Ini mungkin adalah")
    - Kata 4-5: *Teks miring* (contoh: "*mikrofon terbaik*")
    - Kata 6: **TEBAL HIGHLIGHT** (contoh: "**TERMURAH**")
    - Kata 7-9: Teks biasa (contoh: "buat kreator konten")

    Contoh format string: "Ini mungkin *mikrofon terbaik* **TERMURAH** buat kreator konten"

    ATURAN:
    1. Baris 1: Harus 3 kata.
    2. Baris 2: Harus 3 kata (2 miring + 1 tebal highlight).
    3. Baris 3: Harus 2-3 kata.
    4. HARUS CATCHY DAN BERKUALITAS TINGGI.
    """

    system_prompt = f"""
    PERAN: Kamu adalah editor video viral & ahli strategi konten untuk Shorts/Reels/TikTok.
    TUGAS: Analisis transkrip video {video_type.upper()} dan identifikasi TEPAT {num_clips} segmen viral. Kamu WAJIB mengembalikan tepat {num_clips} clip — tidak boleh kurang.

    FORMAT DATA INPUT:
    Transkrip dalam JSON yang sudah di-minify:
    - "s": waktu mulai (detik)
    - "e": waktu selesai (detik)
    - "t": isi teks

    {prompts.get(video_type, prompts['general'])}

    BATASAN KRITIS:
    1. KAMU WAJIB MENGEMBALIKAN TEPAT {num_clips} CLIP. Ini wajib. Kalau momen viral yang jelas kurang dari {num_clips}, berkreasi — cari sisipan menarik, reaksi lucu, momen edukatif, atau pernyataan kontroversial. JANGAN PERNAH kembalikan kurang dari {num_clips} clip.
    2. SETIAP CLIP HARUS BERDURASI {actual_min_duration}-90 detik.
       - TARGETKAN {actual_min_duration + 5} DETIK UNTUK AMAN.
       - CLIP DI BAWAH {actual_min_duration} DETIK AKAN LANGSUNG DITOLAK.
    3. Waktu START dan END harus cocok persis dengan alur transkrip (gunakan "s" dan "e" dari input).
    4. JANGAN potong di tengah kalimat. Pastikan clip mulai dan berakhir di kalimat lengkap.
    5. INSTRUKSI BAHASA (KRITIS):
       - Bahasa terdeteksi: {language.upper()}
       - SEMUA field output (topic, reason, viral_caption, hook_heading, hook_subheading, preset2_content) HARUS dalam {language.upper()}.
       - Kalau {language.upper()} adalah INDONESIA, tulis seluruhnya dalam BAHASA INDONESIA.
       - Kalau {language.upper()} adalah INGGRIS, tulis seluruhnya dalam BAHASA INGGRIS.
       - JANGAN campur bahasa. Sesuaikan bahasa output dengan bahasa input secara tepat.
    6. PADDING KONTEKS: Kalau momen viral pendek, sertakan setup (kalimat sebelum) dan payoff (kalimat sesudah) untuk memenuhi durasi minimum.
    7. BATASAN TEKS HOOK (KRITIS):
       - "hook_heading" (Judul Utama): MAKSIMAL 3 KATA. WAJIB pakai formula spesifik di bawah — JANGAN pakai kata generik seperti "FAKTA MENGEJUTKAN" atau "WAJIB TONTON":
         FORMULA: [Angka + Kata Benda] ("3 RAHASIA"), [Kata Kerja + Hasil] ("STOP BUANG WAKTU"), [Klaim Identitas] ("BICARA NYATA"), [Tantangan] ("BUKTIKAN SALAH"), [Kata Tanya + Topik] ("KENAPA INI BERHASIL"), [Negasi] ("BUKAN YANG KAMU KIRA"), [Tekanan Waktu] ("LAKUKAN SEKARANG"), [Rasa Penasaran] ("ALASAN SESUNGGUHNYA")
       - "hook_subheading": MAKSIMAL 5 KATA. Harus melengkapi atau memperluas heading. WAJIB untuk SEMUA clip.
       - "hook_top_text" (Label Atas): MAKSIMAL 5 KATA. Berfungsi sebagai pemicu rasa penasaran. WAJIB untuk SEMUA clip (contoh: "TUNGGU AKHIRNYA", "NGGA ADA YANG BAHAS INI", "BAGIAN 1", "KEBENARAN SOAL").
       - "viral_caption": Singkat & Menarik (Maks 10 kata). Harus bikin orang berhenti scroll. WAJIB.
    8. DIVERSITAS CLIP: Setiap clip harus membahas TOPIK/SEKSI BERBEDA dari video. Jangan overlap. Sebarkan sepanjang durasi video penuh.

    {preset2_instruction}

    RANTAI PIKIRAN (WAJIB — ikuti langkah ini SEBELUM menulis JSON):

    Langkah 1 — PEMINDAI sinyal kuat dalam transkrip:
      • Lonjakan emosi: speaker naikin suara, ketawa, jeda dramatis, pakai seru
      • Celah informasi: pertanyaan yang dijawab belakangan (bukan langsung)
      • Klaim konkret: angka spesifik, data, nama, atau perbandingan
      • Kontradiksi: pernyataan yang nantang apa yang kebanyakan orang percaya
      • Penanda cerita: "waktu gua...", "ada kejadian...", "yang paling gila itu..."
      • Momen aksi: instruksi, tips, "lakuin ini", "jangan lakuin itu"

    Langkah 2 — EVALUASI setiap kandidat terhadap framework viral di atas:
      • Apakah ada hook yang jelas di 3 detik pertama?
      • Apakah bagian tengah membangun tegangan atau memberi nilai?
      • Apakah ada payoff atau penutup yang memorable?
      • Apakah bisa berdiri sendiri tanpa konteks dari video utuh?
      • Apakah ada yang bakal share ini ke temen?

    Langkah 3 — PILIH tepat {num_clips} clip:
      • Pilih kandidat viral terkuat dari Langkah 2
      • Pastikan TIDAK ADA tumpang tindih waktu antar clip
      • Sebarkan clip di bagian berbeda dari video (awal, tengah, akhir)
      • Kalau kandidat kuat kurang dari {num_clips}: turunkan standar — sertakan sisipan menarik, lelucon, tips edukatif, reaksi emosional, atau perspektif unik
      • Untuk setiap clip, tetapkan tipe hook yang PALING COCOK dari framework

    Langkah 4 — BUAT teks hook pakai FORMULA di batasan 7:
      • hook_heading: Pilih formula, isi dengan konten dari clip (BUKAN pengisi generik)
      • hook_subheading: Lengkapi pemikiran dari hook_heading
      • hook_top_text: Pilih pemicu rasa penasaran yang cocok dengan energi clip
      • viral_caption: Tulis sesuatu yang bikin orang mau tap/share

    INSTRUKSI OUTPUT:
    - Kamu boleh menyertakan penalaran/analisis sesuai langkah di atas.
    - TAPI kamu WAJIB menyertakan array JSON di bagian paling akhir.
    - Array JSON HARUS berisi TEPAT {num_clips} objek.
    - Array JSON harus valid dan bisa di-parse.

    FORMAT OUTPUT (Array JSON murni dengan TEPAT {num_clips} item):
    [
      {{
        "start_time": 12.5,
        "end_time": 45.2,
        "topic": "Kenapa ini viral",
        "reason": "Hook kuat + payoff yang relate",
        "viral_caption": "Tunggu akhirnya...",
        "hook_top_text": "TUNGGU AKHIRNYA",
        "hook_heading": "ALASAN SESUNGGUHNYA",
        "hook_subheading": "Ngga ada yang bahas ini",
        "preset2_content": "Ini mungkin *mikrofon terbaik* **TERMURAH** buat kreator konten"
      }}
    ]
    """
    
    if custom_prompt:
        system_prompt += f"\\n\\nOVERRIDE PENGGUNA:\\n{custom_prompt}"
        
    user_prompt = f"TRANSKRIP:\\n{minified_json}"
    
    update_progress(f"Generating insights via {api_provider.upper()}...", 0.3)
    
    # Call LLM
    # Loop for retries with feedback
    response_text = ""
    attempt = 0
    max_retries = config.max_retries
    
    # Store feedback for next retry
    retry_feedback = ""

    while attempt < max_retries:
        # CHECK CANCELLED
        if check_cancelled and check_cancelled():
            logger.info("Analysis cancelled by user")
            raise Exception("Job Cancelled")
            
        update_progress(f"Generating insights (Attempt {attempt+1}/{max_retries})...", 0.3 + (0.1*attempt))
        
        try:
            # Append feedback if retrying
            current_system_prompt = system_prompt
            if retry_feedback:
                 current_system_prompt += f"\n\nFEEDBACK PENTING DARI PERCOBAAN SEBELUMNYA:\n{retry_feedback}"

            # Normalize provider
            provider_lower = api_provider.lower()
            logger.info(f"Using LLM Provider: {provider_lower}")

            # Fallback to env var if not provided
            final_api_key = api_key
            if not final_api_key:
                env_var = f"{provider_lower.upper()}_API_KEY"
                final_api_key = os.environ.get(env_var)

            if not final_api_key and provider_lower != 'local':
                raise ValueError(f"API Key missing for {api_provider}")

            # Use unified LLM provider
            from services.ai.llm_provider import generate_llm_response

            response_text = generate_llm_response(
                prompt=user_prompt,
                system_instruction=current_system_prompt,
                api_key=final_api_key,
                provider=provider_lower,
                temperature=config.base_temperature + (attempt * 0.1)
            )

            if not response_text:
                raise ValueError(f"Received empty response from {api_provider}")
                

                 
            # --- Parsing & Validation (Moved INSIDE loop) ---
            logger.info(f"LLM Response received (Length: {len(response_text)})")
            
            try:
                clips = parse_llm_response(response_text)
                logger.info(f"LLM returned {len(clips)} raw clips")
                
                valid_clips = []
                for clip in clips:
                    # Relaxed check - Allow cutter to extend if it's at least 50% of target or > 5s
                    # We rely on video_cutter to extend/pad provided the content is at least somewhat substantial.
                    validation_threshold = min(10.0, actual_min_duration * 0.5) 

                    if clip.duration < validation_threshold:
                        logger.warning(f"Clip rejected (too short/garbage): {clip.duration:.1f}s < {validation_threshold}s")
                        continue
                    valid_clips.append(clip.model_dump())
                
                if not valid_clips:
                    # We have parsed clips but all were rejected
                    if clips:
                        msg = f"Dihasilkan {len(clips)} clip tapi SEMUA terlalu pendek (<{actual_min_duration} detik)."
                        retry_feedback = f"Respons sebelumnya punya {len(clips)} clip tapi SEMUA ditolak karena TERLALU PENDEK (di bawah {actual_min_duration} detik).\nKRITIS: Kamu WAJIB buat clip lebih panjang dari {actual_min_duration} detik. STRATEGI: Sertakan kalimat setup SEBELUM momen viral dan kalimat payoff SESUDAHnya. Gabung frasa bersebelahan sampai mencapai {actual_min_duration} detik. Kamu WAJIB kembalikan tepat {num_clips} clip."
                        logger.warning(f"Validation failed: {msg}. Retrying with feedback.")
                        # Pass the raw clips model dumps so we can recover them in fallback
                        raise ValidationError(clips=[c.model_dump() for c in clips], reason=msg)
                    else:
                        msg = "LLM returned valid JSON but 0 clips."
                        retry_feedback = f"Kamu mengembalikan list kosong. Kamu WAJIB identifikasi minimal {num_clips} clip viral dari transkrip ini.\nSTRATEGI: 1) Pindai momen emosional apapun (penekanan speaker, tawa, jeda). 2) Cari klaim spesifik atau data. 3) Temukan beat cerita (setup, konflik, resolusi). 4) Ekstrak tips praktis atau fakta mengejutkan. Kamu WAJIB kembalikan tepat {num_clips} clip."
                        raise ValidationError(clips=[], reason=msg)

                # Check if LLM returned fewer clips than requested
                if len(valid_clips) < num_clips:
                    logger.warning(f"LLM returned {len(valid_clips)} clips but {num_clips} requested")
                    if attempt < max_retries:
                        retry_feedback = f"Kamu mengembalikan {len(valid_clips)} clip tapi gua butuh TEPAT {num_clips}.\nSTRATEGI: 1) Cek timestamp berbeda yang belum kamu cover. 2) Turunkan standar viral — sertakan fakta menarik, reaksi lucu, pernyataan mengejutkan, tips edukatif, momen emosional, atau perspektif unik. 3) Cek awal, tengah, dan akhir video buat momen yang belum dimanfaatin. 4) Cari jeda speaker, perubahan penekanan, atau perpindahan topik. Kamu WAJIB kembalikan tepat {num_clips} clip."
                        attempt += 1
                        continue

                # Success!
                update_progress(f"Found {len(valid_clips)} valid clips!", 1.0)
                return valid_clips[:num_clips]

            except (InvalidResponseError, ValidationError) as ve:
                # Caught validation error, trigger retry
                logger.warning(f"Attempt {attempt+1} failed validation: {ve}")
                attempt += 1
                if attempt >= max_retries:
                    # Check for Best Effort fallback (User Request)
                    # If we have rejected clips (e.g. too short), accept them as last resort
                    if isinstance(ve, ValidationError) and ve.clips:
                        logger.warning(f"Max retries reached ({max_retries}). FALLBACK: Accepting {len(ve.clips)} short/rejected clips.")
                        update_progress(f"⚠️ Max retries reached. Best Effort: Accepting {len(ve.clips)} clips (may be < {actual_min_duration}s).", 1.0)
                        return ve.clips[:num_clips]

                    # Out of retries, simple fail
                    update_progress(f"❌ {str(ve)}", 1.0)
                    raise ve
                time.sleep(2)
                continue
            
        except Exception as e:
            # API or Network error
            logger.error(f"LLM Error (Attempt {attempt+1}): {e}")
            attempt += 1
            if attempt >= max_retries:
                update_progress(f"Analysis failed: {str(e)}", 1.0)
                raise e
            time.sleep(2)
