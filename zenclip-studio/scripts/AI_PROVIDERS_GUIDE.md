# AI Provider Setup Guide

## Supported Providers

| Provider | API Key Variable | Get API Key | Model |
|----------|-----------------|-------------|-------|
| DeepSeek | `DEEPSEEK_API_KEY` | https://platform.deepseek.com | deepseek-chat |
| OpenAI | `OPENAI_API_KEY` | https://platform.openai.com | gpt-4o-mini |
| Gemini | `GEMINI_API_KEY` | https://aistudio.google.com | gemini-2.5-flash |
| Anthropic | `ANTHROPIC_API_KEY` | https://console.anthropic.com | claude-3-haiku-20240307 |
| Local (Ollama) | None | https://ollama.ai | mistral |

---

## VERIFIED: Gemini 2.5 Flash Pipeline

### Full AI Pipeline Test (2026-04-06)
**Video:** 10-minute podcast about trading/investing (Indonesian)
**Result:** 5 viral clips auto-selected by Gemini AI

| Step | Tool | Time | Output |
|------|------|------|--------|
| 1. Audio extraction | FFmpeg | ~5s | WAV 16kHz mono |
| 2. ASR transcription | Faster Whisper (base) | ~105s | 299 phrases, lang=id |
| 3. AI clip selection | Gemini 2.5 Flash | ~15s | 5 clips with hooks |
| 4. Video cutting | OpenCV + FFmpeg | ~30min | 5 clips, 193MB |

### Important Notes
- **Model:** Use `gemini-2.5-flash` (NOT `gemini-1.5-flash` which returns 404)
- **API endpoint:** `v1beta/models/{model}:generateContent?key={api_key}`
- **Response format:** JSON wrapped in markdown code blocks (handled by parser)
- **Language support:** Indonesian detected and handled correctly

### Gemini Clips Generated (Example)
```
Clip 1: GAME VS DIRI (59s) - "Jangan cuma karakter game yang naik level, dirimu juga!"
Clip 2: JANGAN FORECAST (36s) - "Stop forecasting! Cukup bereaksi di pasar modal."
Clip 3: TANDA BAHAYA (73s) - "Kenali tanda-tanda EQ uang rendah agar tidak rugi investasi!"
Clip 4: KISAH NYATA (79s) - "Setelah 10 tahun, malah rugi 8 juta! Kenapa bisa?"
Clip 5: WADAH UANG (57s) - "Setiap orang punya 'wadah uang' yang membatasi kekayaanmu!"
```

---

## Setup Methods

### Method 1: Environment Variable
```cmd
REM Windows CMD
set GEMINI_API_KEY=AIzaxxxxx

REM Then run backend
python run_backend.py
```

### Method 2: Settings API
```cmd
curl -X POST http://127.0.0.1:8000/api/settings ^
  -H "Content-Type: application/json" ^
  -d "{\"apiKey\":\"YOUR_API_KEY\",\"apiProvider\":\"gemini\"}"
```

### Method 3: In Request
```json
{
  "video_path": "...",
  "phrase_timings": [...],
  "clips_data": [...],
  "api_key": "AIzaxxxxx",
  "api_provider": "gemini"
}
```

---

## Manual AI Pipeline (Without Backend)

If backend doesn't auto-trigger AI analysis:

```bash
# Step 1: Extract audio
ffmpeg -i video.mp4 -vn -acodec pcm_s16le -ar 16000 -ac 1 audio.wav

# Step 2: Transcribe with Python
cd audit/recovery-workspace/backend
python -c "
from faster_whisper import WhisperModel
import json
model = WhisperModel('base', device='cpu', compute_type='int8')
segments, info = model.transcribe('audio.wav', beam_size=3, vad_filter=True)
phrases = [{'text': s.text.strip(), 'start': round(s.start, 2), 'end': round(s.end, 2)} for s in segments]
json.dump(phrases, open('transcript.json', 'w'), indent=2, ensure_ascii=False)
print(f'{len(phrases)} phrases, lang={info.language}')
"

# Step 3: Call Gemini API (use llm_analyzer.py or direct API)

# Step 4: Submit with clips_data
curl -X POST http://127.0.0.1:8000/manual_transcript_import \
  -H "Content-Type: application/json" \
  -d '{"video_path":"...","phrase_timings":[...],"clips_data":[...]}'
```

---

## Related Documentation

- [README.md](README.md) - Full usage guide
- [HOOK_PRESETS_GUIDE.md](HOOK_PRESETS_GUIDE.md) - Hook overlay customization (4 presets)
- [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md) - CLI configuration reference

---

## Cost Comparison

| Provider | Input/1K tokens | Output/1K tokens | Notes |
|----------|----------------|------------------|-------|
| DeepSeek | $0.001 | $0.002 | Cheapest |
| OpenAI GPT-4o-mini | $0.00015 | $0.0006 | Very cheap |
| Gemini Flash | Free tier | Free tier | Best free option |
| Claude 3 Haiku | $0.00025 | $0.00125 | Good quality |
| Local (Ollama) | Free | Free | Requires GPU |

---

## Recommendations

1. **Free tier:** Use Gemini (free, works great for Indonesian)
2. **Cheapest paid:** DeepSeek or OpenAI GPT-4o-mini
3. **Best quality:** Claude 3.5 Sonnet
4. **No internet:** Local Ollama

---

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `DEEPSEEK_API_KEY` | - | DeepSeek API key |
| `OPENAI_API_KEY` | - | OpenAI API key |
| `GEMINI_API_KEY` | - | Google Gemini API key |
| `ANTHROPIC_API_KEY` | - | Anthropic API key |
| `LOCAL_LLM_URL` | http://localhost:11434/v1 | Ollama URL |
| `LOCAL_LLM_MODEL` | mistral | Model to use |

---

*Updated: 2026-04-06 - Gemini pipeline verified with real content*
