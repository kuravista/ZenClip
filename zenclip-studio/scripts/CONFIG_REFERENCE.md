# ZenClip CLI Configuration Reference

## Quick Commands

### 1. Basic Process (Auto ASR)
```cmd
curl -X POST http://127.0.0.1:8000/process ^
  -F "video=@D:/path/video.mp4" ^
  -F "num_clips=5" ^
  -F "min_duration=30" ^
  -F "aspect_ratio=9:16" ^
  -F "add_subtitles=true" ^
  -F "subtitle_style=shadow"
```

### 2. Manual Transcript Import (Bypass ASR)
```cmd
curl -X POST http://127.0.0.1:8000/manual_transcript_import ^
  -H "Content-Type: application/json" ^
  -d @config.json
```

---

## All Configuration Options

### CLIP SETTINGS
| Parameter | Type | Default | Options |
|-----------|------|---------|---------|
| `num_clips` | int | 3 | 1-20 |
| `min_duration` | int | 30 | seconds |
| `video_aspect` | string | "9:16" | "9:16", "16:9", "1:1" |
| `video_type` | string | "general" | "general", "podcast", "tutorial" |

### SUBTITLE SETTINGS
| Parameter | Type | Default | Options |
|-----------|------|---------|---------|
| `add_subtitles` | bool | true | true, false |
| `subtitle_style` | string | "shadow" | See styles below |
| `subtitle_font` | string | "Poppins-Bold.otf" | See fonts below |
| `subtitle_font_size` | int | 24 | 16-48 |
| `subtitle_color` | string | "#FFFFFF" | Any hex color |
| `subtitle_outline` | int | 2 | 0-4 |
| `subtitle_position` | string | "bottom" | "top", "center", "bottom" |

### SUBTITLE STYLES
```
shadow      - Soft shadow (default)
elegant     - Clean without shadow
boxies      - Box background
mozi        - Mozi style
pod_d       - Podcast style
rapid_fire  - Fast paced
rapid_pro   - Professional fast
karaoke     - Highlight active word
```

### HOOK SETTINGS
| Parameter | Type | Default | Options |
|-----------|------|---------|---------|
| `add_viral_hook` | bool | false | true, false |
| `hook_style` | string | "preset2" | preset1-4 |
| `hook_font` | string | "Montserrat-Black.otf" | See fonts |
| `hook_font_size` | int | 48 | 24-72 |

### HOOK STYLES
```
preset1 - Simple text
preset2 - Heading + Subheading (default)
preset3 - Animated
preset4 - Bold impact
```

### WATERMARK SETTINGS
| Parameter | Type | Default | Options |
|-----------|------|---------|---------|
| `add_watermark` | bool | false | true, false |
| `watermark_text` | string | "" | Any text |
| `watermark_position` | string | "bottom-right" | "top-left", "top-right", "bottom-left", "bottom-right" |

### ENCODING SETTINGS
| Parameter | Type | Default | Options |
|-----------|------|---------|---------|
| `encoding_preset` | string | "medium" | "fast", "medium", "slow" |
| `randomize_metadata` | bool | false | true, false |

### LANGUAGE
| Parameter | Type | Default | Options |
|-----------|------|---------|---------|
| `language` | string | "en" | "en", "id", "es", "fr", etc. |

---

## Available Fonts

### Subtitle Fonts (Recommended)
```
Poppins-Bold.otf        ← Default
Poppins-SemiBold.ttf
Poppins-Regular.ttf
Poppins-Black.ttf
```

### Hook Fonts (Recommended)
```
Montserrat-Black.otf    ← Default
Montserrat-Bold.otf
```

### Decorative Fonts
```
PlayfairDisplay-Italic.ttf  - Elegant
JetBrainsMono-Bold.ttf      - Monospace
Handron-Solid.otf           - Display
Mango Superb.ttf            - Display
```

### Khmer Fonts
```
Nokora-Regular.ttf
Nokora-Black.ttf
```

---

## JSON Template

```json
{
  "video_path": "D:/path/to/video.mp4",
  "phrase_timings": [
    {"text": "Your transcript text", "start": 0.0, "end": 5.0}
  ],
  "clips_data": [
    {
      "start_time": 0,
      "end_time": 30,
      "topic": "Clip Topic",
      "hook_heading": "Hook Title",
      "hook_subheading": "Hook Subtitle"
    }
  ],

  "num_clips": 3,
  "min_duration": 30,
  "video_aspect": "9:16",
  "video_type": "general",

  "add_subtitles": true,
  "subtitle_style": "shadow",
  "subtitle_font": "Poppins-Bold.otf",
  "subtitle_font_size": 24,
  "subtitle_color": "#FFFFFF",
  "subtitle_outline": 2,
  "subtitle_position": "bottom",

  "add_viral_hook": true,
  "hook_style": "preset2",
  "hook_font": "Montserrat-Black.otf",
  "hook_font_size": 48,

  "add_watermark": false,
  "watermark_text": "",
  "watermark_position": "bottom-right",

  "encoding_preset": "medium",
  "randomize_metadata": false,
  "language": "en"
}
```

---

## Examples

### Example 1: TikTok Vertical Video
```cmd
curl -X POST http://127.0.0.1:8000/manual_transcript_import ^
  -H "Content-Type: application/json" ^
  -d "{\"video_path\":\"D:/video.mp4\",\"phrase_timings\":[...],\"clips_data\":[...],\"num_clips\":5,\"video_aspect\":\"9:16\",\"add_subtitles\":true,\"subtitle_style\":\"shadow\",\"add_viral_hook\":true,\"hook_style\":\"preset2\"}"
```

### Example 2: YouTube Horizontal Video
```cmd
curl -X POST http://127.0.0.1:8000/manual_transcript_import ^
  -H "Content-Type: application/json" ^
  -d "{\"video_path\":\"D:/video.mp4\",\"phrase_timings\":[...],\"clips_data\":[...],\"num_clips\":3,\"video_aspect\":\"16:9\",\"add_subtitles\":true,\"subtitle_style\":\"elegant\",\"add_viral_hook\":false}"
```

### Example 3: Large Font for Mobile
```cmd
curl -X POST http://127.0.0.1:8000/manual_transcript_import ^
  -H "Content-Type: application/json" ^
  -d "{\"video_path\":\"D:/video.mp4\",\"phrase_timings\":[...],\"clips_data\":[...],\"subtitle_font_size\":32,\"subtitle_outline\":3}"
```

---

## Check Status

```cmd
curl http://127.0.0.1:8000/status/{job_id}
```

## List Output

```cmd
curl http://127.0.0.1:8000/api/videos
```

## Get Fonts

```cmd
curl http://127.0.0.1:8000/api/fonts
```

## Get Settings

```cmd
curl http://127.0.0.1:8000/api/settings
```

## Update Settings

```cmd
curl -X POST http://127.0.0.1:8000/api/settings ^
  -H "Content-Type: application/json" ^
  -d "{\"apiKey\":\"your-key\",\"apiProvider\":\"deepseek\"}"
```
