#!/usr/bin/env python3
"""
OpenRouter Model Research - Transcript Analysis Comparison
Tests multiple LLM models to find which one identifies the most/best viral clips.

Usage:
    cd backend
    python src/tests/research_openrouter_models.py
"""

import json
import os
import sys
import time
import requests

sys.stdout.reconfigure(encoding="utf-8")

# --- Config ---
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Load transcript from the test job
TRANSCRIPT_PATH = "jobs_data/d6ade67c-e6d6-4e7e-a134-c226064b72db/transcript.json"

# Models to test - mix of free, cheap, and premium
MODELS = [
    {
        "id": "google/gemini-2.5-flash-preview:free",
        "name": "Gemini 2.5 Flash (free)",
        "tier": "free",
    },
    {
        "id": "google/gemini-2.5-pro-preview",
        "name": "Gemini 2.5 Pro",
        "tier": "premium",
    },
    {"id": "deepseek/deepseek-chat-v3-0324", "name": "DeepSeek V3", "tier": "cheap"},
    {"id": "deepseek/deepseek-r1", "name": "DeepSeek R1", "tier": "mid"},
    {"id": "anthropic/claude-sonnet-4", "name": "Claude Sonnet 4", "tier": "premium"},
    {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini", "tier": "cheap"},
    {"id": "meta-llama/llama-4-maverick", "name": "Llama 4 Maverick", "tier": "mid"},
    {"id": "qwen/qwen3-235b-a22b", "name": "Qwen3 235B", "tier": "mid"},
    {"id": "mistralai/mistral-large-2411", "name": "Mistral Large", "tier": "mid"},
]

# How many clips to ask for
NUM_CLIPS = 7
MIN_DURATION = 30

# --- Load & Prepare Transcript ---


def load_transcript():
    """Load transcript and minify for LLM."""
    with open(TRANSCRIPT_PATH, encoding="utf-8") as f:
        raw = json.load(f)

    # Minify: keep only s, e, t fields
    minified = []
    for p in raw:
        minified.append(
            {
                "s": round(float(p.get("start", 0)), 2),
                "e": round(float(p.get("end", 0)), 2),
                "t": p.get("text", ""),
            }
        )
    return minified


def smart_sample(phrases, target=200):
    """Sample transcript if too long."""
    if len(phrases) <= target:
        return phrases
    step = max(1, len(phrases) // target)
    return phrases[::step]


def build_prompt(transcript_json):
    """Build the analysis prompt."""
    return f"""ROLE: Kamu adalah expert Viral Video Editor untuk konten Indonesia (Shorts/Reels/TikTok).

TASK: Analisis transcript podcast Indonesia "Mitos vs Fakta Mendidik Anak" oleh Raditya Dika (38.8 menit).
Temukan TOP {NUM_CLIPS} segmen paling viral yang bisa dijadikan clip pendek.

TRANSCRIPT FORMAT:
- "s": start time (detik)
- "e": end time (detik)
- "t": text content

RULES:
1. Setiap clip HARUS 30-90 detik. Aim for 45-75 detik.
2. Start/end harus di batas kalimat yang lengkap (lihat "s" dan "e" dari transcript).
3. Cari minimal {NUM_CLIPS} segmen yang BERBEDA - jangan overlap.
4. Fokus pada: momen mengejutkan, insight mendalam, debat, cerita personal, tips praktis.
5. Pastikan clip tersebar di seluruh video (awal, tengah, akhir), bukan cluster di satu area.
6. Semua output WAJIB dalam Bahasa Indonesia.

OUTPUT FORMAT - HANYA JSON ARRAY, TANPA MARKDOWN, TANPA PENJELASAN:
[
  {{
    "start_time": 12.5,
    "end_time": 55.0,
    "topic": "Topik utama clip",
    "reason": "Kenapa ini viral",
    "viral_caption": "Caption pendek untuk social media",
    "hook_heading": "MAX 3 KATA",
    "hook_subheading": "MAX 5 KATA",
    "preset2_content": "Kata biasa *italic kata* **BOLD HIGHLIGHT** kata biasa"
  }}
]

TRANSCRIPT:
{transcript_json}"""


def call_openrouter(model_id, prompt, temperature=0.3):
    """Call OpenRouter API."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://zenclip.local",
    }

    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": 16000,
    }

    start = time.time()
    try:
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=180)
        elapsed = time.time() - start

        if resp.status_code != 200:
            return {
                "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
                "elapsed": elapsed,
            }

        data = resp.json()

        # Check for API-level errors
        if "error" in data:
            return {
                "error": f"API: {data['error'].get('message', str(data['error']))[:200]}",
                "elapsed": elapsed,
            }

        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Get usage stats
        usage = data.get("usage", {})

        return {
            "content": content,
            "elapsed": elapsed,
            "tokens_in": usage.get("prompt_tokens", 0),
            "tokens_out": usage.get("completion_tokens", 0),
            "total_cost": 0,  # Will calculate later
        }
    except requests.exceptions.Timeout:
        return {"error": "Timeout (180s)", "elapsed": time.time() - start}
    except Exception as e:
        return {"error": str(e)[:200], "elapsed": time.time() - start}


def parse_clips(response_text):
    """Try to extract clips from model response."""
    # Clean markdown
    text = response_text.replace("```json", "").replace("```", "").strip()

    # Try direct parse
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except:
        pass

    # Try find [ ... ]
    try:
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
    except:
        pass

    return None


def score_clips(clips, total_video_duration=2331):
    """Score clips on multiple criteria."""
    if not clips:
        return {"total": 0, "score": 0, "issues": ["No clips parsed"]}

    score = 0
    issues = []
    total_clip_duration = 0
    valid_clips = 0

    # 1. Number of clips (target: 7)
    num_clips = len(clips)
    if num_clips >= 7:
        score += 25
    elif num_clips >= 5:
        score += 15
    elif num_clips >= 3:
        score += 8
    else:
        issues.append(f"Too few clips: {num_clips}")

    # 2. Duration validity (30-90s each)
    for i, c in enumerate(clips):
        start = c.get("start_time", 0)
        end = c.get("end_time", 0)
        dur = end - start

        if dur < 10:
            issues.append(f"Clip {i + 1}: too short ({dur:.0f}s)")
        elif dur < 30:
            issues.append(f"Clip {i + 1}: under 30s ({dur:.0f}s)")
            score += 3
        elif dur <= 90:
            score += 5
            valid_clips += 1
        else:
            issues.append(f"Clip {i + 1}: over 90s ({dur:.0f}s)")
            score += 3

        total_clip_duration += dur

    # 3. Spread across video
    if clips:
        starts = [c.get("start_time", 0) for c in clips]
        video_thirds = total_video_duration / 3
        first_third = sum(1 for s in starts if s < video_thirds)
        mid_third = sum(1 for s in starts if video_thirds <= s < video_thirds * 2)
        last_third = sum(1 for s in starts if s >= video_thirds * 2)

        if first_third > 0 and mid_third > 0 and last_third > 0:
            score += 20  # Good spread
        elif first_third > 0 and mid_third > 0:
            score += 10
        else:
            issues.append(
                f"Clips clustered: 1st={first_third}, mid={mid_third}, last={last_third}"
            )

    # 4. Topic quality (has all required fields)
    complete_clips = 0
    for c in clips:
        has_topic = bool(c.get("topic"))
        has_reason = bool(c.get("reason"))
        has_heading = bool(c.get("hook_heading"))
        has_preset2 = bool(c.get("preset2_content"))

        if has_topic and has_reason and has_heading:
            complete_clips += 1
        if not has_preset2:
            pass  # Not critical

    score += min(complete_clips * 3, 15)

    # 5. No overlap
    sorted_clips = sorted(clips, key=lambda x: x.get("start_time", 0))
    overlaps = 0
    for i in range(len(sorted_clips) - 1):
        if sorted_clips[i].get("end_time", 0) > sorted_clips[i + 1].get(
            "start_time", 0
        ):
            overlaps += 1

    if overlaps == 0:
        score += 15
    else:
        issues.append(f"{overlaps} overlapping clips")

    return {
        "total": len(clips),
        "valid": valid_clips,
        "complete": complete_clips,
        "total_duration": round(total_clip_duration),
        "overlaps": overlaps,
        "score": min(score, 100),
        "issues": issues if issues else ["All good"],
    }


def print_clip_detail(clips):
    """Print clip details for comparison."""
    for i, c in enumerate(clips):
        start = c.get("start_time", 0)
        end = c.get("end_time", 0)
        dur = end - start
        topic = c.get("topic", "?")
        heading = c.get("hook_heading", "?")
        preset2 = c.get("preset2_content", "NONE")

        mins_s, secs_s = divmod(int(start), 60)
        mins_e, secs_e = divmod(int(end), 60)

        print(
            f"    {i + 1}. [{mins_s}:{secs_s:02d}-{mins_e}:{secs_e:02d}] ({dur:.0f}s) {topic}"
        )
        print(f"       Hook: {heading} | Preset2: {preset2[:60]}")


# --- Main ---


def main():
    print("=" * 70)
    print("OPENROUTER MODEL RESEARCH - Viral Clip Analysis")
    print("=" * 70)

    # Load transcript
    raw_transcript = load_transcript()
    print(f"\nTranscript: {len(raw_transcript)} phrases")

    sampled = smart_sample(raw_transcript, target=200)
    transcript_json = json.dumps(sampled, ensure_ascii=False)
    print(f"Sampled: {len(sampled)} phrases ({len(transcript_json)} chars)")

    prompt = build_prompt(transcript_json)
    print(f"Prompt: {len(prompt)} chars (~{len(prompt) // 3} tokens)")
    print(f"Target: {NUM_CLIPS} clips, min {MIN_DURATION}s each")
    print()

    # Results storage
    results = []

    # Test each model
    for model in MODELS:
        model_id = model["id"]
        model_name = model["name"]
        tier = model["tier"]

        print(f"--- Testing: {model_name} ({tier}) ---")

        resp = call_openrouter(model_id, prompt)

        if "error" in resp:
            print(f"  ERROR: {resp['error']}")
            print(f"  Time: {resp['elapsed']:.1f}s")
            results.append(
                {
                    "model": model_name,
                    "tier": tier,
                    "status": "error",
                    "error": resp["error"],
                    "elapsed": resp["elapsed"],
                }
            )
            print()
            continue

        content = resp["content"]
        elapsed = resp["elapsed"]
        tokens_in = resp["tokens_in"]
        tokens_out = resp["tokens_out"]

        # Parse
        clips = parse_clips(content)

        if clips is None:
            print(f"  Time: {elapsed:.1f}s | Tokens: {tokens_in}→{tokens_out}")
            print(f"  PARSE FAILED (response not valid JSON)")
            print(f"  Response preview: {content[:200]}...")
            results.append(
                {
                    "model": model_name,
                    "tier": tier,
                    "status": "parse_failed",
                    "elapsed": elapsed,
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "response_len": len(content),
                }
            )
            print()
            continue

        # Score
        scoring = score_clips(clips)

        print(f"  Time: {elapsed:.1f}s | Tokens: {tokens_in}→{tokens_out}")
        print(
            f"  Clips found: {len(clips)} | Valid: {scoring['valid']} | Score: {scoring['score']}/100"
        )
        print(
            f"  Total clip duration: {scoring['total_duration']}s ({scoring['total_duration'] / 60:.1f} min)"
        )
        if scoring["issues"]:
            for issue in scoring["issues"]:
                print(f"  Issue: {issue}")

        print_clip_detail(clips)

        results.append(
            {
                "model": model_name,
                "tier": tier,
                "status": "success",
                "elapsed": elapsed,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "response_len": len(content),
                "clips_count": len(clips),
                "clips_valid": scoring["valid"],
                "clips_complete": scoring["complete"],
                "score": scoring["score"],
                "total_duration": scoring["total_duration"],
                "overlaps": scoring["overlaps"],
                "clips": clips,
            }
        )

        print()

        # Rate limit protection
        time.sleep(3)

    # --- Summary ---
    print("\n" + "=" * 70)
    print("COMPARISON SUMMARY")
    print("=" * 70)

    # Sort by score
    successful = [r for r in results if r["status"] == "success"]
    successful.sort(key=lambda x: x["score"], reverse=True)

    print(
        f"\n{'Rank':<5} {'Model':<25} {'Clips':<7} {'Valid':<7} {'Score':<7} {'Time':<8} {'Tokens':<12} {'Tier'}"
    )
    print("-" * 90)

    for rank, r in enumerate(successful, 1):
        print(
            f"{rank:<5} {r['model']:<25} {r['clips_count']:<7} {r['clips_valid']:<7} "
            f"{r['score']:<7} {r['elapsed']:<8.1f} {r['tokens_in']}→{r['tokens_out']:<6} {r['tier']}"
        )

    # Failed models
    failed = [r for r in results if r["status"] != "success"]
    if failed:
        print(f"\nFailed models:")
        for r in failed:
            print(f"  - {r['model']}: {r.get('error', r['status'])}")

    # Winner
    if successful:
        winner = successful[0]
        print(f"\n{'=' * 50}")
        print(f"BEST MODEL: {winner['model']}")
        print(f"  Score: {winner['score']}/100")
        print(f"  Clips: {winner['clips_count']} found, {winner['clips_valid']} valid")
        print(f"  Speed: {winner['elapsed']:.1f}s")
        print(f"  Tier: {winner['tier']}")
        print(f"{'=' * 50}")

    # Save full results
    output_path = "docs/openrouter_research_results.json"
    os.makedirs("docs", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nFull results saved to: {output_path}")


if __name__ == "__main__":
    main()
