# OpenRouter Model Cost Analysis — ZenClip

**Date:** 2026-04-08
**Test Video:** "Mitos vs Fakta Mendidik Anak" — Raditya Dika (38.8 min, 584 phrases)
**Kurs:** ~Rp 16.500/USD
**Platform:** OpenRouter API (openrouter.ai)

---

## Token Usage & Cost per Video

| # | Model | Tokens In | Tokens Out | Cost (USD) | Cost (IDR) | Valid Clips | Score | Tier |
|---|-------|-----------|------------|------------|------------|-------------|-------|------|
| 1 | Gemini 2.5 Pro | 11,574 | 6,631 | $0.081 | **Rp 1.333** | 7/7 | 100 | Premium |
| 2 | Claude Sonnet 4 | 12,060 | 1,407 | $0.057 | **Rp 945** | 5/7 | 100 | Premium |
| 3 | Mistral Large | 13,981 | 1,706 | $0.038 | **Rp 630** | 2/7 | 100 | Mid |
| 4 | Qwen3 235B | 12,754 | 6,198 | $0.017 | **Rp 282** | 1/7 | 72 | Mid |
| 5 | DeepSeek R1 | 10,749 | 1,632 | $0.012 | **Rp 191** | 7/7 | 100 | Mid |
| 6 | DeepSeek V3 | 10,742 | 1,083 | $0.003 | **Rp 49** | 5/7 | 100 | Cheap |
| 7 | Llama 4 Maverick | 10,278 | 838 | $0.002 | **Rp 34** | 7/7 | 100 | Cheap |
| 8 | GPT-4o Mini | 10,271 | 824 | $0.002 | **Rp 34** | 0/7 | 61 | Cheap |

> Gemini 2.5 Flash (free) gagal — model ID tidak valid di OpenRouter (HTTP 400)

---

## OpenRouter Pricing (per 1M tokens)

| Model | Input (USD) | Output (USD) |
|-------|-------------|--------------|
| google/gemini-2.5-pro-preview | $1.25 | $10.00 |
| anthropic/claude-sonnet-4 | $3.00 | $15.00 |
| mistralai/mistral-large-2411 | $2.00 | $6.00 |
| qwen/qwen3-235b-a22b | $0.455 | $1.82 |
| deepseek/deepseek-r1 | $0.70 | $2.50 |
| deepseek/deepseek-chat-v3-0324 | $0.20 | $0.77 |
| meta-llama/llama-4-maverick | $0.15 | $0.60 |
| openai/gpt-4o-mini | $0.15 | $0.60 |

---

## Speed Comparison

| Model | Response Time | Tokens/Second |
|-------|--------------|---------------|
| Llama 4 Maverick | 18.8s | 44.6 |
| GPT-4o Mini | 20.0s | 41.2 |
| Claude Sonnet 4 | 26.9s | 52.3 |
| Mistral Large | 33.8s | 50.5 |
| DeepSeek V3 | 41.2s | 26.3 |
| DeepSeek R1 | 51.0s | 32.0 |
| Gemini 2.5 Pro | 63.5s | 104.4 |
| Qwen3 235B | 154.8s | 40.0 |

---

## Quality Detail per Model

### Gemini 2.5 Pro (Rp 1.333) — BEST QUALITY
- 7/7 clips valid (30-90s), 0 overlaps
- Caption paling kreatif dan engaging
- Hook heading/subheading paling punchy
- Preset2 content paling rich dan detail
- Total clip duration: 387 detik (6.5 menit)

### Claude Sonnet 4 (Rp 945)
- 5/7 clips valid, 2 clip terlalu panjang (>90s)
- Caption bagus tapi kurang variatif
- Total clip duration: 514 detik (8.6 menit) — terlalu banyak

### DeepSeek R1 (Rp 191) — BEST MID-TIER
- 7/7 clips valid, 0 overlaps
- Caption cukup baik, hook standar
- Total clip duration: 381 detik (6.4 menit)
- **Value ratio terbaik di tier mid**

### Llama 4 Maverick (Rp 34) — BEST VALUE
- 7/7 clips valid, 0 overlaps
- Response tercepat (18.8s)
- Caption standar, hook cukup
- Total clip duration: 308 detik (5.1 menit)
- **39x lebih murah dari Gemini Pro**

### DeepSeek V3 (Rp 49)
- 5/7 clips valid, 2 clip terlalu pendek
- Hook heading terlalu generik ("TIPS", "FAKTA", "MITOS")
- Total clip duration: 308 detik

### GPT-4o Mini (Rp 34) — GAGAL
- 0/7 clips valid — SEMUA clip terlalu pendek (5-13 detik)
- Tidak bisa mengikuti instruksi durasi 30-90s
- preset2_content berformat "Kata biasa *italic* **bold** kata biasa" (template kosong)
- **TIDAK RECOMMENDED untuk clip analysis**

---

## Rekomendasi

| Kategori | Model | Biaya/Video | Alasan |
|----------|-------|-------------|--------|
| **Best Value** | Llama 4 Maverick | Rp 34 | 7/7 valid, tercepat, 39x lebih murah dari Gemini Pro |
| **Best Quality** | Gemini 2.5 Pro | Rp 1.333 | 7/7 valid, caption & hook paling kreatif |
| **Budget Quality** | DeepSeek R1 | Rp 191 | 7/7 valid, kualitas mendekati premium, 7x lebih murah |
| **JANGAN DIPAKAI** | GPT-4o Mini | Rp 34 | 0/7 valid — gagal ikuti instruksi durasi |

### Scenario-based Recommendation

| Use Case | Model | Est. Monthly Cost (100 video) |
|----------|-------|-------------------------------|
| Produksi harian (volume tinggi) | Llama 4 Maverick | Rp 3.400 |
| Kualitas seimbang (daily + quality) | DeepSeek R1 | Rp 19.100 |
| Konten premium (brand penting) | Gemini 2.5 Pro | Rp 133.300 |
| Mix strategy | R1 (daily) + Gemini Pro (premium) | ~Rp 50.000 |

---

## Notes

- Harga OpenRouter bisa berubah tanpa pemberitahuan
- Cek harga terbaru: https://openrouter.ai/models
- Token count bervariasi tergantung durasi video & transcript length
- Video 38.8 menit = ~11K input tokens rata-rata
- Video lebih panjang → proporsional lebih mahal
- Kurs USD/IDR bisa fluktuasi

---

*Document generated: 2026-04-08*
*Source: backend/docs/openrouter_research_results.json*
