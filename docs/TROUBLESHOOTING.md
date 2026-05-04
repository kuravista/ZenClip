# ZenClip Troubleshooting Guide

## Subtitle System Issues

### 1. Subtitle Styles Look Identical / No Visual Difference

**Symptom:** All 9 subtitle styles (shadow, elegant, boxies, karaoke, mozi, pod_d, rapid_fire, rapid_pro, prince) render the same — plain white text, no animation.

**Root Causes & Fixes:**

| # | Root Cause | Fix | Commit |
|---|-----------|-----|--------|
| 1 | `rapid_fire` name mismatch: frontend sends `rapid_fire`, backend checked `rapid` | Normalization added in both `ass_generator.py` and `generator.py` | `2423255` |
| 2 | `karaoke` and `boxies` had empty/stub ASS generators | Implemented full generators | `2423255` |
| 3 | `prince` style not in UI dropdown | Added to ProcessForm + SettingsPanel | `277967d` |

---

### 2. Subtitle Animations Not Working (Fonts Not Found by FFmpeg)

**Symptom:** ASS file is generated but FFmpeg renders plain text without any styling — no colors, no borders, wrong font.

**Root Cause:** FFmpeg's subtitle filter couldn't find the font files. The `fontsdir` parameter was either not passed or pointed to a wrong path.

**Fix (commit `b6b0739`):**
- `ffmpeg_pipeline.py` now copies font files to the clip output directory before subtitle pass
- `fonts_dir` fallback chain resolves correctly to `backend/static/fonts/`
- Path: `os.path.join(os.path.dirname(__file__), '..', '..', 'static', 'fonts')` from `subtitle/ass_generator.py`
- Fonts are also embedded as base64 in the ASS `[Fonts]` section for self-containment

**Available fonts** in `backend/static/fonts/`:
- `Montserrat-Black.otf`, `Montserrat-Bold.otf`
- `Poppins-Regular.ttf`, `Poppins-Bold.ttf`, `Poppins-Black.ttf`, `Poppins-SemiBold.ttf`
- `PlayfairDisplay-Italic.ttf`

---

### 3. Subtitle Pass Fails — Colon in Filename

**Symptom:** FFmpeg error: `Unable to parse option value as image size` when burning subtitles. Happens when video topic/title contains `:` or `'` characters (e.g. "Shadow Projection:", "Konsep_'Wadah_Uang'").

**Root Cause:** FFmpeg's `subtitles` filter treats `:` as option separator and `'` causes path parsing errors.

**Fix (commit `aedfb61`):**
- ASS filename is now always the safe name `subs.ass` (no topic text in filename)
- Written to clip output directory, referenced with relative path
- `cwd=clip_dir` passed to subprocess so relative path works

---

### 4. Karaoke Word-by-Word Sweep Animation Not Working

**Symptom:** Karaoke/mozi styles show text but no smooth word-by-word color sweep. Instead: flickering slideshow or static text.

**Root Cause (fundamental architecture):** The original approach created multiple overlapping Dialogue events per word — one event per highlight transition. This produces flickering, not smooth animation, because each event instantly replaces the previous one.

**Fix (commit this session):**
- Rewrote both `generate_karaoke_events()` and `generate_mozi_events()` to use ASS native `\kf` tags
- Each chunk of words is now a **single Dialogue event** spanning the full chunk duration
- `\kf<centiseconds>` tags between words tell libass to smoothly sweep color from SecondaryColour to PrimaryColour
- Added two new ASS style definitions to the header:
  - `KaraokeYellow`: PrimaryColour=yellow, SecondaryColour=dim gray
  - `KaraokeGreen`: PrimaryColour=green, SecondaryColour=dim gray

**How `\kf` works:**
```
Style: KaraokeYellow, ..., PrimaryColour=&H0000FFFF, SecondaryColour=&H00999999, ...
Dialogue: 0,0:00:00.00,0:00:02.00,KaraokeYellow,,0,0,0,,{\kf50}Hello {\kf50}world {\kf30}this
```
- Before `\kf` duration elapses: word is SecondaryColour (dim gray)
- During/After: word smoothly transitions to PrimaryColour (yellow/green)
- The number is centiseconds (1/100th second) — `{\kf50}` = 0.5 seconds

**`\k` vs `\kf`:**
- `\k<cs>` = instant switch (hard cut)
- `\kf<cs>` = smooth gradient sweep (use this for karaoke feel)

---

### 5. `\t` Animations Unreliable in FFmpeg Burn-in

**Symptom:** Styles using `\t()` transform animations (scale pop-in, blur-to-focus, zoom) don't animate when burned via FFmpeg's `subtitles` filter.

**Root Cause:** `\t()` transform timing depends on frame rendering cadence. FFmpeg burn-in renders subtitles per-frame, but `\t` interpolation doesn't reliably produce visible animation at typical framerates (24-30fps). The animation may complete too fast (within 1-2 frames) or not interpolate at all.

**Fix:** Removed all `\t` animations from all styles. Each style now uses:
- `\fad(fadein_ms, fadeout_ms)` — reliable, works consistently
- Static visual tags for distinct identity: colors (`\c`, `\3c`), fonts (`\fn`), sizes (`\fs`), borders (`\bord`), shadows (`\shad`), blur (`\blur`)

**Styles cleaned up:**

| Style | Removed | Kept |
|-------|---------|------|
| rapid_fire | `\fscx120\fscy120\t(80,\fscx100\fscy100)` pop-in | Large font 1.5x + thick border 5px + fade |
| pod_d | `\fscx130\fscy130\t(150,\fscx100\fscy100)` pop-in | Pastel pink + thick stroke + fade |
| elegant | `\blur8\fscx115\fscy115\t(0,300,\blur0\fscx100\fscy100)` | Dual-font (Poppins + Playfair) + fade |
| prince | `\fscx105\fscy105\t(0,300,\fscx100\fscy100)` zoom | Dual-font hierarchy + thick outline + fade |
| shadow | `\move(x,y1,x,y2)` slide-up | Deep shadow `\shad8` + thick outline + `\pos` + fade |

---

## FFmpeg Pipeline Issues

### 6. Two-Pass Pipeline — Subtitle Pass Skips fonts_dir

**Symptom:** PASS1 (crop/scale/overlay) works fine, PASS2 (subtitle burn-in) renders plain text without fonts.

**Root Cause:** The subtitle pass code had `# fonts_dir: skip it` — was commented out / not implemented.

**Fix (commit `aedfb61`):** Font files are copied to clip output directory before PASS2 runs, and referenced via relative path in the ASS file.

---

### 7. Fonts Dir Resolves to Wrong Path

**Symptom:** `ass_generator.py` can't find fonts — path `../../static/fonts` resolves to `src/static/fonts` instead of `backend/static/fonts/`.

**Root Cause:** Wrong relative path depth. From `backend/src/services/media/subtitle/`, going up 2 levels lands in `src/`, not `backend/`.

**Fix (commit `aedfb61`):** Changed to `../../../static/fonts` (3 levels up from `subtitle/`) which correctly resolves to `backend/static/fonts/`.

---

## Style Visual Identity Reference

Each style has a distinct visual identity through reliable static ASS tags:

| Style | Font | Color Scheme | Key Visual | Layout |
|-------|------|-------------|------------|--------|
| shadow | Poppins Bold | White + black outline + deep shadow | `\shad8` deep drop shadow | 2-line, max 8 words |
| elegant | Poppins + Playfair Display | White + lime green italic | Dual-font, key words get Playfair italic | 1-line, max 3 words |
| boxies | Poppins Bold | White + blue box (#2563EB) | Line 2 has thick blue border as box effect | 2-line split, max 5 words |
| karaoke | Montserrat Black | Yellow (active) + gray (pre) | `\kf` smooth color sweep | 2-line, max 6 words |
| mozi | Montserrat Black | Green (active) + gray (pre) | `\kf` smooth color sweep | 2-line (3/2), max 5 words |
| pod_d | Poppins Bold | Pastel pink + yellow highlight | Thick black stroke (3-4px) | 1-line, max 3 words |
| rapid_fire | Poppins Bold | White/yellow, 1.5x size | Single huge word + thick border 5px | 1 word per event |
| rapid_pro | Poppins Bold | Yellow glow + white lead | Dual-layer: glow (blur25) + sharp text | 1-line, max 3 words |
| prince | Poppins + Playfair Display | White, dual-size | Important words get Playfair italic + 1.2x | 2-line (3/3), max 6 words |

---

## ASS Tag Reliability Matrix

Tested with FFmpeg `subtitles=file.ass` filter (libass):

| Tag | Reliable? | Notes |
|-----|-----------|-------|
| `\c` (color) | YES | Primary text color |
| `\fn` (font) | YES | Font family name |
| `\fs` (size) | YES | Font size in points |
| `\b` (bold) | YES | 0=off, 1=on, -1=true |
| `\i` (italic) | YES | 0=off, 1=on |
| `\bord` (border) | YES | Outline width |
| `\3c` (outline color) | YES | Outline/border color |
| `\shad` (shadow) | YES | Shadow offset distance |
| `\4c` (shadow color) | YES | Shadow color |
| `\blur` (blur) | YES | Gaussian blur radius |
| `\fad` (fade) | YES | `\fad(in_ms, out_ms)` — reliable |
| `\pos` (position) | YES | `\pos(x,y)` absolute position |
| `\N` (line break) | YES | Hard line break in text |
| `\kf` (karaoke sweep) | YES | Smooth color sweep, centiseconds |
| `\k` (karaoke instant) | YES | Instant color switch |
| `\t` (transform) | NO | Timing unreliable in FFmpeg burn-in |
| `\move` (move) | NO | Janky or not visible in burn-in |
| `\fscx/\fscy` (scale) | PARTIAL | Static scale works, animated via `\t` does NOT |
| `\fr` (rotation) | PARTIAL | Not tested extensively |

---

*Last updated: 2026-04-20*
