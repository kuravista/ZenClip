from moviepy import TextClip, CompositeVideoClip

try:
    from moviepy.video.fx import CrossFadeIn
except ImportError:
    CrossFadeIn = None

from services.media.subtitle.utils.text import measure_real_height
from services.media.subtitle.utils.fonts import get_font_path

MOZI_CONFIG = {
    "chunk_size": 5,
    "max_width_ratio": 0.80,
    "word_spacing_px": 8,
    "line_gap_px": -10,
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
    Mozi-style subtitles with STABLE positioning.

    Key design decisions to prevent jumping:
      1. FIXED ANCHOR: All chunks anchor to the same bottom-Y baseline,
         so 1-line and 2-line chunks share the same bottom position.
      2. DYNAMIC WRAP: Line breaks are computed from actual pixel widths,
         not a hardcoded 3/2 split.
      3. SLOT-BASED LAYOUT: Each word gets a fixed slot sized for the
         GREEN (highlight) state.  The actual clip (white or green) is
         centred inside that slot, so switching never shifts neighbours.
    """
    print(
        f"[INFO] Generating Mozi subtitles for clip {clip_start:.1f}s - {clip_end:.1f}s"
    )

    video_w, video_h = video_clip.size
    audio_offset = config.get("audio_offset", 0.0)

    # ── Layout constants (same for every chunk) ───────────────────────
    max_line_width = video_w * MOZI_CONFIG["max_width_ratio"]
    word_spacing = MOZI_CONFIG["word_spacing_px"]
    line_gap = MOZI_CONFIG["line_gap_px"]
    # Fixed anchor: bottom edge of text block always sits here
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

    # ── 2. Chunking ───────────────────────────────────────────────────
    CHUNK_SIZE = MOZI_CONFIG["chunk_size"]
    chunks = [
        all_words[i : i + CHUNK_SIZE] for i in range(0, len(all_words), CHUNK_SIZE)
    ]

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

        # ── 3. Pre-render white + green clips ─────────────────────────
        word_clips = {}
        for idx, word in enumerate(chunk):
            white_clip = _generate_mozi_text_clip(
                word["text"], config, is_highlight=False
            )
            green_clip = _generate_mozi_text_clip(
                word["text"], config, is_highlight=True
            )

            w_start_rel = max(
                0, word["start"] - clip_start + audio_offset - rel_chunk_start
            )
            w_end_rel = min(
                chunk_duration,
                word["end"] - clip_start + audio_offset - rel_chunk_start,
            )

            word_clips[idx] = {
                "white": white_clip,
                "green": green_clip,
                "white_w": white_clip.w,
                "white_h": white_clip.h,
                "green_w": green_clip.w,
                "green_h": green_clip.h,
                "start": w_start_rel,
                "end": w_end_rel,
            }

        # ── 4. Dynamic line wrap (pixel-based, replaces hardcoded 3/2) ─
        # Use GREEN dimensions for slot allocation so highlight never overflows.
        lines = []  # list[list[int]]  — each inner list is word indices
        current_line = []
        current_line_w = 0

        for idx in range(len(chunk)):
            slot_w = word_clips[idx]["green_w"]
            spacing = word_spacing if current_line else 0
            if current_line and (current_line_w + spacing + slot_w > max_line_width):
                lines.append(current_line)
                current_line = [idx]
                current_line_w = slot_w
            else:
                current_line.append(idx)
                current_line_w += spacing + slot_w
        if current_line:
            lines.append(current_line)

        # ── 5. Slot-based layout (FIXED positions) ────────────────────
        # Line height = tallest GREEN clip in that line
        line_heights = [max(word_clips[i]["green_h"] for i in line) for line in lines]
        total_block_h = sum(line_heights) + line_gap * max(0, len(lines) - 1)

        # Anchor BOTTOM of block at anchor_y  →  stable across chunks
        current_y = anchor_y - total_block_h

        fixed_slots = {}  # idx → (slot_x, slot_y, slot_w, slot_h)
        for line_idx, line in enumerate(lines):
            line_h = line_heights[line_idx]
            # Total line width based on GREEN (max) slots
            total_w = sum(word_clips[i]["green_w"] for i in line) + word_spacing * (
                len(line) - 1
            )
            start_x = (video_w - total_w) // 2

            curr_x = start_x
            for idx in line:
                gw = word_clips[idx]["green_w"]
                gh = word_clips[idx]["green_h"]
                fixed_slots[idx] = (curr_x, current_y, gw, gh)
                curr_x += gw + word_spacing

            current_y += line_h + line_gap

        # ── 6. Generate time-segment clips using fixed slots ──────────
        time_points = {0.0, chunk_duration}
        for idx in word_clips:
            t = word_clips[idx]
            if t["start"] > 0:
                time_points.add(t["start"])
            if t["end"] < chunk_duration:
                time_points.add(t["end"])
        sorted_points = sorted(time_points)

        chunk_sub_clips = []

        for seg_i in range(len(sorted_points) - 1):
            t0 = sorted_points[seg_i]
            t1 = sorted_points[seg_i + 1]
            dur = t1 - t0
            if dur < 0.01:
                continue

            active_indices = {
                idx
                for idx in word_clips
                if word_clips[idx]["start"] <= t0 and t1 <= word_clips[idx]["end"]
            }

            for idx in range(len(chunk)):
                if idx not in fixed_slots:
                    continue
                is_active = idx in active_indices
                clip = (
                    word_clips[idx]["green"] if is_active else word_clips[idx]["white"]
                )
                slot_x, slot_y, slot_w, slot_h = fixed_slots[idx]

                # Centre actual clip inside its fixed slot
                x_pos = slot_x + (slot_w - clip.w) // 2
                y_pos = slot_y + (slot_h - clip.h) // 2

                final_clip = (
                    clip.with_position((x_pos, y_pos)).with_start(t0).with_duration(dur)
                )
                chunk_sub_clips.append(final_clip)

        # ── 7. Composite the chunk ────────────────────────────────────
        if chunk_sub_clips:
            comp = CompositeVideoClip(chunk_sub_clips, size=(video_w, video_h))
            comp = comp.with_start(rel_chunk_start).with_duration(chunk_duration)

            if CrossFadeIn:
                comp = comp.with_effects([CrossFadeIn(duration=0.1)])
            else:
                comp = comp.with_opacity(lambda t: min(1.0, t / 0.1))

            subtitle_clips.append(comp)

    return subtitle_clips
