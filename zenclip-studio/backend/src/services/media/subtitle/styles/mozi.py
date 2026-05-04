from moviepy import TextClip, CompositeVideoClip

try:
    from moviepy.video.fx import CrossFadeIn
except ImportError:
    CrossFadeIn = None

from services.media.subtitle.utils.text import measure_real_height
from services.media.subtitle.utils.fonts import get_font_path

MOZI_CONFIG = {
    "max_width_ratio": 0.80,
    "word_spacing_px": 8,
    "min_word_duration_ms": 50,
}


def _generate_mozi_text_clip(text, config, is_highlight=False):
    """Render a single word as a TextClip (white or green highlighted)."""

    font_path = get_font_path(config["font"])
    fontsize = config["fontsize"]

    if is_highlight:
        color = "#00FF00"
        fontsize = int(fontsize * 1.3)
        stroke_width = max(12, int(config.get("stroke_width", 3) * 2.5))
    else:
        color = config.get("color", "white")
        stroke_width = max(8, int(config.get("stroke_width", 3)))

    text_upper = text.upper()
    text_with_padding = f"{text_upper}\n "

    txt = TextClip(
        text=text_with_padding,
        font=font_path,
        font_size=fontsize,
        color=color,
        stroke_color=config.get("stroke_color", "black"),
        stroke_width=stroke_width,
        method="label",
    )

    try:
        real_h = measure_real_height(txt, buffer=15)
        if real_h > 0 and real_h < txt.h:
            txt = txt.cropped(y2=real_h)
    except Exception as e:
        print(f"  ⚠️ Height measurement failed: {e}")

    return txt


def create_mozi_subtitles(config, video_clip, phrase_timings, clip_start, clip_end):
    """
    Mozi-style subtitles — single-line per chunk with per-word highlight.

    Each chunk = exactly ONE line of text on screen.
    Words that don't fit the line width become a new chunk,
    so the text NEVER splits into 2 rows within the same display.
    """
    print(
        f"[INFO] Generating Mozi subtitles for clip {clip_start:.1f}s - {clip_end:.1f}s"
    )

    video_w, video_h = video_clip.size
    audio_offset = config.get("audio_offset", 0.0)
    max_line_width = video_w * MOZI_CONFIG["max_width_ratio"]
    word_spacing = MOZI_CONFIG["word_spacing_px"]

    # Fixed bottom anchor — every chunk's bottom edge sits here
    anchor_y = int(video_h * (config.get("vertical_position", 75) / 100.0))

    # ── 1. Collect words ──────────────────────────────────────────────
    all_words = []
    for phrase in phrase_timings:
        p_start, p_end = phrase["start"], phrase["end"]
        if p_end < (clip_start - 1.5) or p_start > (clip_end + 1.5):
            continue

        words = phrase.get("words", [])
        if not words:
            words = [{"text": phrase["text"], "start": p_start, "end": p_end}]

        for w in words:
            if w["end"] < (clip_start - 1.5):
                continue
            if w["start"] > (clip_end + 1.5):
                continue
            all_words.append({"text": w["text"], "start": w["start"], "end": w["end"]})

    if not all_words:
        return []

    all_words.sort(key=lambda x: x["start"])

    # ── 2. Pre-render ALL word clips first ────────────────────────────
    # This lets us measure green_w for auto-sizing chunks.
    rendered = []
    for word in all_words:
        white_clip = _generate_mozi_text_clip(word["text"], config, is_highlight=False)
        green_clip = _generate_mozi_text_clip(word["text"], config, is_highlight=True)
        rendered.append(
            {
                "text": word["text"],
                "start": word["start"],
                "end": word["end"],
                "white": white_clip,
                "green": green_clip,
                "white_w": white_clip.w,
                "white_h": white_clip.h,
                "green_w": green_clip.w,
                "green_h": green_clip.h,
            }
        )

    # ── 3. Auto-size chunks: each chunk = words that fit ONE line ─────
    chunks = []
    current_chunk = []
    current_w = 0

    for item in rendered:
        slot_w = item["green_w"]
        spacing = word_spacing if current_chunk else 0
        needed = spacing + slot_w

        if current_chunk and (current_w + needed > max_line_width):
            # This word overflows → seal current chunk, start new one
            chunks.append(current_chunk)
            current_chunk = [item]
            current_w = slot_w
        else:
            current_chunk.append(item)
            current_w += needed

    if current_chunk:
        chunks.append(current_chunk)

    # ── 4. Render each single-line chunk ──────────────────────────────
    subtitle_clips = []

    for chunk in chunks:
        if not chunk:
            continue

        # Timing
        chunk_start_abs = chunk[0]["start"]
        chunk_end_abs = chunk[-1]["end"]
        rel_chunk_start = max(0, chunk_start_abs - clip_start + audio_offset)
        rel_chunk_end = chunk_end_abs - clip_start + audio_offset
        chunk_duration = rel_chunk_end - rel_chunk_start
        if chunk_duration < 0.1:
            continue

        # Calculate relative start/end for each word within the chunk
        for item in chunk:
            item["w_start_rel"] = max(
                0, item["start"] - clip_start + audio_offset - rel_chunk_start
            )
            item["w_end_rel"] = min(
                chunk_duration,
                item["end"] - clip_start + audio_offset - rel_chunk_start,
            )

        # ── Slot layout (single line, bottom-anchored) ────────────────
        # Line height = tallest GREEN clip (the max possible height)
        line_h = max(item["green_h"] for item in chunk)
        total_w = sum(item["green_w"] for item in chunk) + word_spacing * (
            len(chunk) - 1
        )
        start_x = (video_w - total_w) // 2

        # Bottom anchor: bottom edge of line sits at anchor_y
        line_y = anchor_y - line_h

        # Assign fixed slots
        fixed_slots = []  # parallel to chunk list
        curr_x = start_x
        for item in chunk:
            fixed_slots.append((curr_x, line_y, item["green_w"], item["green_h"]))
            curr_x += item["green_w"] + word_spacing

        # ── Time segments ─────────────────────────────────────────────
        time_points = {0.0, chunk_duration}
        for item in chunk:
            if item["w_start_rel"] > 0:
                time_points.add(item["w_start_rel"])
            if item["w_end_rel"] < chunk_duration:
                time_points.add(item["w_end_rel"])
        sorted_points = sorted(time_points)

        chunk_sub_clips = []

        for seg_i in range(len(sorted_points) - 1):
            t0 = sorted_points[seg_i]
            t1 = sorted_points[seg_i + 1]
            dur = t1 - t0
            if dur < 0.01:
                continue

            for idx, item in enumerate(chunk):
                w_start = item["w_start_rel"]

                # Progressive reveal: skip words that haven't started yet
                if t1 <= w_start:
                    continue

                is_active = item["w_start_rel"] <= t0 and t1 <= item["w_end_rel"]
                clip = item["green"] if is_active else item["white"]

                # Fade-in for newly appeared words
                if t0 - w_start < 0.08:
                    opacity = min(1.0, (t1 - w_start) / 0.08)
                    clip = clip.with_opacity(opacity)

                slot_x, slot_y, slot_w, slot_h = fixed_slots[idx]

                # Centre clip inside its fixed slot
                x_pos = slot_x + (slot_w - clip.w) // 2
                y_pos = slot_y + (slot_h - clip.h) // 2

                final_clip = (
                    clip.with_position((x_pos, y_pos)).with_start(t0).with_duration(dur)
                )
                chunk_sub_clips.append(final_clip)

        # Composite
        if chunk_sub_clips:
            comp = CompositeVideoClip(chunk_sub_clips, size=(video_w, video_h))
            comp = comp.with_start(rel_chunk_start).with_duration(chunk_duration)

            if CrossFadeIn:
                comp = comp.with_effects([CrossFadeIn(duration=0.1)])
            else:
                comp = comp.with_opacity(lambda t: min(1.0, t / 0.1))

            subtitle_clips.append(comp)

    return subtitle_clips
