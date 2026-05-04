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
        'general': """FRAMEWORK VIRAL UNIVERSAL (SEMUA NICHE):

1. HOOK 3 DETIK PERTAMA (WAJIB - pilih yang cocok dengan niche):
   
   TIPE HOOK UNIVERSAL:
   • Pertanyaan shock → "Kenapa ini ga ada yang jelasin?"
   • Surprising stats/numbers -> "90% of people don't know this..."
   • Kontradiksi → "Yang bilang X itu SALAH, ini faktanya..."
   • Before/After → "Dulu gua X, sekarang Y"
   • Challenge/Dare → "Coba tebak apa yang terjadi..."
   • Secret reveal → "Rahasia yang ga akan dibagiin siapapun"
   • Relatable pain → "Pernah ngerasa X? Gua juga..."
   • FOMO trigger → "Semua orang udah tau kecuali lu"

2. RETENTION MECHANICS (minimal 2 dari list ini):
   
   • Loop/Callback → Setup di awal, payoff di akhir
   • Cliffhanger → "Tapi yang paling penting..." (di 40-60% video)
   • List format → "Ada 3 hal yang harus lu tau..."
   • Storytelling → Ada konflik → tension → resolusi
   • Educational → Problem → Explanation → Solution
   • Pattern breaks → Unexpected twist/reveal
   • Curiosity gap → Open question yang baru dijawab di akhir""",

        'podcast': """FRAMEWORK VIRAL PODCAST:

1. HOOK:
   • Quote kontroversial atau mengejutkan dari narasumber.
   • Controversial or surprising quote from the speaker.
   • Cerita personal yang relate dengan audiens.
   • Insight mendalam yang mengubah perspektif ("Mind-blown moment").
   • Pertanyaan tajam dari host yang bikin penasaran.

2. FOKUS KONTEN:
   • Storytelling yang kuat (awal-tengah-akhir).
   • Debat atau diskusi panas.
   • Tips praktis atau life hack.
   • Momen emosional (sedih, inspiratif, lucu).
   • "Behind the scenes" atau rahasia industri.""",

        'gaming': """FRAMEWORK VIRAL GAMING:

1. HOOK:
   • Momen "Clutch" atau kemenangan mustahil.
   • Reaksi lucu/kaget/marah yang ekstrem (Rage quit, funny fail).
   • Glitch aneh atau penemuan rahasia (Easter egg).
   • Skill tingkat dewa (Pro play).

2. FOKUS KONTEN:
   • High intensity action.
   • Komedi dan interaksi konyol.
   • Tutorial cepat atau tips tersembunyi.
   • Plot twist dalam gameplay.
   • Relatable gamer moments (lag, teammate noob, dll).""",

        'motivational': """FRAMEWORK VIRAL MOTIVATIONAL:

1. HOOK:
   • Pertanyaan retoris tentang kegagalan/kesuksesan.
   • Pernyataan keras yang menampar realita ("Wake up call").
   • Kata-kata bijak yang langsung relate ke insecurity orang.

2. FOKUS KONTEN:
   • Inspiring speech.
   • Cerita perjuangan (Zero to Hero).
   • Filosofi hidup (Stoic, Minimalist, dll).
   • Musik latar yang mendukung (tone serius).
   • Call to Action untuk berubah.""",

        'comedy': """FRAMEWORK VIRAL COMEDY/HIBURAN:

1. HOOK:
   • Setup situasi absurd.
   • Premis yang relatable tapi dibelokkan.
   • Karakter yang unik/mimik wajah lucu.

2. FOKUS KONTEN:
   • Punchline yang tidak terduga.
   • Sketsa singkat.
   • Parodi tren terkini.
   • Timing komedi yang pas.
   • Tawa yang menular.""",
   
        'education': """FRAMEWORK VIRAL EDUCATION/EDUTECH:

1. HOOK:
   • "Stop lakukan X, mulai lakukan Y."
   • Fakta sains/sejarah yang jarang diketahui.
   • Solusi cepat untuk masalah umum.

2. FOKUS KONTEN:
   • Penjelasan visual yang simpel.
   • Langkah-langkah konkret (How-to).
   • Mitos vs Fakta.
   • Studi kasus singkat.
   • Aha! moment."""
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
    SPECIAL INSTRUCTION FOR 'preset2_content':
    You must generate a field called "preset2_content" for each clip.
    The content MUST follow this EXACT word pattern (Total 8-9 words):
    - Words 1-3: Regular text (e.g. "This might be")
    - Words 4-5: *Italic text* (e.g. "*the best*")
    - Word 6: **BOLD HIGHLIGHT** (e.g. "**BUDGET**")
    - Words 7-9: Regular text (e.g. "wireless microphone")
    
    String format example: "This might be *the best* **BUDGET** wireless microphone"
    
    RULES:
    1. Line 1: Must be 3 words.
    2. Line 2: Must be 3 words (2 italic + 1 bold highlight).
    3. Line 3: Must be 2-3 words.
    4. IT MUST BE CATCHY AND HIGH QUALITY.
    """

    system_prompt = f"""
    ROLE: You are an expert Viral Video Editor & Content Strategist for Shorts/Reels/TikTok.
    TASK: Analyze the provided transcript relative to a {video_type.upper()} video and identify the TOP {num_clips} sections capable of going VIRAL.
    
    INPUT DATA FORMAT:
    The transcript is minified JSON:
    - "s": start time (seconds)
    - "e": end time (seconds)
    - "t": text content
    
    {prompts.get(video_type, prompts['general'])}
    
    CRITICAL CONSTRAINTS:
    1. EACH CLIP MUST BE {actual_min_duration}-90 seconds.
       - AIM FOR {actual_min_duration + 5} SECONDS TO BE SAFE.
       - CLIPS UNDER {actual_min_duration} SECONDS WILL BE REJECTED INSTANTLY.
    2. START and END times must match exactly with the flow in the transcript (use "s" and "e" from input).
    3. DO NOT cut mid-sentence. Ensure the clip starts and ends on complete sentences.
    4. LANGUAGE INSTRUCTION (CRITICAL):
       - The detected language is: {language.upper()}
       - ALL output fields (topic, reason, viral_caption, hook_heading, hook_subheading, preset2_content) MUST be in {language.upper()}.
       - If {language.upper()} is INDONESIAN, write entirely in INDONESIAN.
       - If {language.upper()} is ENGLISH, write entirely in ENGLISH.
       - Do not mix languages. Match the output language to the input language exactly.
    5. CONTEXT PADDING: If a viral moment is short, include the setup (sentence before) and payoff (sentence after) to meet the duration requirement.
    6. HOOK TEXT CONSTRAINTS (CRITICAL):
       - "hook_heading" (Main Headline): MAX 3 WORDS. Short & Punchy. MANDATORY for ALL clips.
       - "hook_subheading": MAX 5 WORDS. MANDATORY for ALL clips.
       - "hook_top_text" (Top Label): MAX 5 WORDS. MANDATORY for ALL clips (e.g. "WATCH THIS", "DID YOU KNOW").
       - "viral_caption": Short & Engaging (Max 10 words). MANDATORY.

    {preset2_instruction}

    CHAIN OF THOUGHT (REQUIRED):
    Before generating the JSON, you MUST analyze the transcript step-by-step:
    1. Scan for "Emotional Spikes" (laughter, yelling, crying, intense focus).
    2. Look for "Information Gaps" (questions asked but not immediately answered).
    3. Identify "Relatable Moments" using the Universal Hooks.
    4. For each candidate, ask: "Does this stand alone? Is the start/end distinct?"

    OUTPUT INSTRUCTION:
    - You can include your reasoning/analysis matching the steps above.
    - BUT you MUST include the final JSON array at the very end.
    - The JSON array must be valid and parseable.

    OUTPUT FORMAT (Pure JSON):
    [
      {{
        "start_time": 12.5,
        "end_time": 45.2,
        "topic": "Why this goes viral",
        "reason": "Strong hook + relatable payoff",
        "viral_caption": "Wait for the end...",
        "hook_top_text": "WATCH THIS",
        "hook_heading": "SHOCKING TRUTH",
        "hook_subheading": "You won't believe this",
        "preset2_content": "Ini mungkin adalah *microphone terbaik* **TERMURAH** untuk konten kreator"
      }}
    ]
    """
    
    if custom_prompt:
        system_prompt += f"\\n\\nUSER OVERRIDE:\\n{custom_prompt}"
        
    user_prompt = f"TRANSCRIPT:\\n{minified_json}"
    
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
                 current_system_prompt += f"\n\nIMPORTANT FEEDBACK FROM PREVIOUS ATTEMPT:\n{retry_feedback}"

            # Normalize provider
            provider_lower = api_provider.lower()
            logger.info(f"Using LLM Provider: {provider_lower}")

            if provider_lower == 'deepseek':
                import openai
                # Fallback to env var if not provided
                final_api_key = api_key or os.environ.get('DEEPSEEK_API_KEY')
                if not final_api_key: raise ValueError("DeepSeek API Key missing")
                
                client = openai.OpenAI(api_key=final_api_key, base_url="https://api.deepseek.com")
                resp = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": current_system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=config.base_temperature + (attempt * 0.1),
                    stream=False
                )
                response_text = resp.choices[0].message.content

            else:
                raise ValueError(f"Unknown or Unsupported API Provider: {api_provider}. Only 'deepseek' is supported.")

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
                        msg = f"Generated {len(clips)} clips but ALL were too short (<{actual_min_duration}s)."
                        retry_feedback = f"Your previous response had {len(clips)} clips but they were ALL rejected because they were TOO SHORT. \nCRITICAL: You MUST make clips longer than {actual_min_duration} seconds. Merge adjacent segments if needed."
                        logger.warning(f"Validation failed: {msg}. Retrying with feedback.")
                        # Pass the raw clips model dumps so we can recover them in fallback
                        raise ValidationError(clips=[c.model_dump() for c in clips], reason=msg)
                    else:
                        msg = "LLM returned valid JSON but 0 clips."
                        retry_feedback = "You returned an empty list. Please identify at least 1 viral clip."
                        raise ValidationError(clips=[], reason=msg)
                
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
