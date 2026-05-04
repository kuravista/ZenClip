# Hook Overlay Presets - Customization Guide

**Updated:** 2026-04-06

---

## Overview

Hook overlay adalah text yang muncul di awal video clip (biasanya 3 detik pertama). Ada 4 preset style yang bisa dipilih.

| Preset | Style | Background | Karakteristik |
|--------|-------|------------|---------------|
| **Preset 1** | Classic Box | Gambar background (`background_hook.png`) | Top text + Heading + Subheading dalam box |
| **Preset 2** | Glow Text | Transparan (tanpa background) | Text glow neon, kata-kata di-highlight |
| **Preset 3** | Viral Stack | Transparan | 3 baris: warna + putih + badge |
| **Preset 4** | Simple Box | Rounded box berwarna | Semua text dalam satu kotak |

---

## Cara Memilih Preset

### Via API
```json
{
  "hook_styles": {
    "hook_style": "preset-2"
  }
}
```

Nilai valid: `"preset-1"`, `"preset-2"`, `"preset-3"`, `"preset-4"`

### Default
Jika tidak ditentukan, menggunakan **Preset 1**.

---

## File Lokasi

| Komponen | File |
|----------|------|
| Preset 1 | `backend/src/services/media/video_cutter.py` (fungsi `create_viral_hook_overlay`) |
| Preset 2 | `backend/src/services/media/subtitle/preset2_hook.py` |
| Preset 3 | `backend/src/services/media/subtitle/preset3_hook.py` |
| Preset 4 | `backend/src/services/media/subtitle/preset4_hook.py` |
| Routing logic | `backend/src/services/media/video_cutter.py` baris ~1166-1253 |
| Background image | `backend/static/background/background_hook.png` (Preset 1 only) |
| Font files | `backend/static/fonts/` |

---

## Font Tersedia

Letakkan file font di `backend/static/fonts/`.

| File | Nama untuk Parameter |
|------|---------------------|
| `Impact.ttf` | `Impact` |
| `Poppins-Black.ttf` | `Poppins-Black` |
| `Poppins-Bold.ttf` | `Poppins-Bold` |
| `Poppins-SemiBold.ttf` | `Poppins-SemiBold` |
| `Poppins-Regular.ttf` | `Poppins-Regular` |
| `Montserrat-Black.otf` | `Montserrat-Black` |
| `Montserrat-Bold.otf` | `Montserrat-Bold` |
| `Mango Superb.ttf` | `Mango Superb` |
| `Handron-Solid.otf` | `Handron-Solid` |
| `Nokora-Black.ttf` | `Nokora-Black` |
| `Nokora-Regular.ttf` | `Nokora-Regular` |
| `PlayfairDisplay-Italic.ttf` | `PlayfairDisplay-Italic` |
| `JetBrainsMono-Bold.ttf` | `JetBrainsMono-Bold` |

---

## Preset 1 - Classic Box

### Tampilan
Text dalam box dengan background image (gradient gelap).

### Parameter

| Parameter | Default | Fungsi |
|-----------|---------|--------|
| `font` | `Impact` | Font heading |
| `color` | `#FF0000` | Warna heading |
| `font_size` | `80` | Ukuran heading |
| `top_font_size` | `30` | Ukuran text atas |
| `sub_font_size` | `28` | Ukuran subheading |
| `top_text` | `""` | Text baris atas (kecil) |
| `headline` | *(dari AI/manual)* | Text heading utama |
| `subheading` | *(dari AI/manual)* | Text subheading |
| `stroke_width` | `2` | Ketebalan outline |
| `stroke_color` | `#000000` | Warna outline |
| `line_spacing` | `-4` | Spasi antar baris |
| `top_gap` | `10` | Jarak atas heading |
| `bottom_gap` | `20` | Jarak bawah heading |
| `position` | `bottom` | Posisi: `bottom`, `center`, atau persen `80` |

### Contoh Payload
```json
{
  "hook_styles": {
    "hook_style": "preset-1",
    "top_text": "JANGAN LEWATKAN",
    "headline": "GAME VS DIRI",
    "subheading": "Filosofi trading yang jarang dibahas",
    "font": "Montserrat-Black",
    "color": "#FF0000",
    "font_size": 80,
    "stroke_width": 2
  }
}
```

### Edit Default
File: `video_cutter.py`, fungsi `create_viral_hook_overlay()`, baris ~401-416.

---

## Preset 2 - Glow Text (Transparan)

### Tampilan
Text langsung di atas video tanpa background. Kata-kata tertentu memiliki efek glow neon. Background transparan penuh.

### Format Text (`preset2_content`)
Gunakan markdown-style formatting:
- `**kata**` → Highlight color (default: kuning `#CBFF00`) + efek glow
- `*kata*` → Italic (font PlayfairDisplay-Italic)
- `kata` biasa → Base color (default: putih)
- `++kata++` → Regular text (eksplisit non-highlight)

Text otomatis dipecah per 3 kata per baris.

### Parameter

| Parameter | Default | Fungsi |
|-----------|---------|--------|
| `preset2_content` | *(wajib diisi)* | Text hook (format markdown) |
| `font` | `Impact` | Font utama |
| `font_size` | `80` | Ukuran text baris kedua (headline) |
| `top_font_size` | `50%` dari font_size | Ukuran text baris pertama (top label) |
| `sub_font_size` | `50%` dari font_size | Ukuran text baris ketiga+ (sub) |
| `highlight_color` | `#CBFF00` | Warna highlight (`**bold**`) + glow |
| `base_color` | `#FFFFFF` | Warna text normal (putih) |
| `stroke_width` | `2` | Ketebalan outline |
| `stroke_color` | `#000000` | Warna outline |
| `top_gap` | `10` | Jarak baris 1 ke baris 2 |
| `bottom_gap` | `20` | Jarak baris 2 ke baris 3 |

### Layout Baris
- **Baris 1 (3 kata pertama):** Top label, ukuran kecil
- **Baris 2 (3 kata kedua):** Headline, ukuran besar
- **Baris 3+ (sisa kata):** Subheading, ukuran kecil

### Contoh Payload
```json
{
  "hook_styles": {
    "hook_style": "preset-2",
    "preset2_content": "This might be *the best* **BUDGET** wireless **MICROPHONE** for beginners",
    "font": "Poppins-Black",
    "font_size": 100,
    "highlight_color": "#CBFF00",
    "base_color": "#FFFFFF",
    "stroke_width": 3,
    "stroke_color": "#000000"
  }
}
```

### Hasil Render
```
This might be the best      ← kecil, putih (the best italic)
BUDGET wireless MICROPHONE  ← besar, BUDGET & MICROPHONE kuning glow
for beginners               ← kecil, putih
```

### Edit Default
File: `preset2_hook.py`, baris 72-89.

### Cara Kerja Glow Effect
1. Text highlight (`**kata**`) digambar di layer terpisah (glow_canvas)
2. Layer tersebut di-blur dengan `GaussianBlur(radius=15)`
3. Blur layer di-composite 3x untuk intensitas neon
4. Text utama (dengan stroke) di-overlay di atas glow

---

## Preset 3 - Viral Stack

### Tampilan
3 baris text tanpa background. Baris pertama warna, baris kedua putih besar, baris ketiga badge (text dalam kotak warna).

### Parameter

| Parameter | Default | Fungsi |
|-----------|---------|--------|
| `top_text` | `""` | Baris 1 - text besar berwarna |
| `headline` | `""` | Baris 2 - text besar putih |
| `subheading` | `""` | Baris 3 - badge (kotak berwarna + text putih) |
| `font` | `Impact` | Font semua baris |
| `font_size` / `hook_font_size` | `100` | Ukuran baris 1 & 2 |
| `top_font_size` / `hook_top_font_size` | sama dengan font_size | Ukuran spesifik baris 1 |
| `sub_font_size` / `hook_sub_font_size` | `40%` dari font_size | Ukuran badge |
| `color` | `#2F54EB` | Warna baris 1 + warna badge |
| `stroke_width` | `2` | Ketebalan outline |
| `stroke_color` | `#000000` | Warna outline |
| `top_gap` | `10` | Jarak baris 1 ke 2 |
| `bottom_gap` | `20` | Jarak baris 2 ke badge |
| `position` | `80` | Posisi vertikal (0-100 persen) |

### Contoh Payload
```json
{
  "hook_styles": {
    "hook_style": "preset-3",
    "top_text": "VIRAL",
    "headline": "MARKETING",
    "subheading": "psychology",
    "font": "Montserrat-Black",
    "font_size": 120,
    "color": "#2F54EB",
    "position": 65
  }
}
```

### Edit Default
File: `preset3_hook.py`, baris 16-74.

---

## Preset 4 - Simple Box

### Tampilan
Semua text dalam satu rounded box berwarna. Minimalis, clean.

### Parameter

| Parameter | Default | Fungsi |
|-----------|---------|--------|
| `top_text` | `""` | Text atas (kecil) |
| `headline` | `""` | Heading utama |
| `subheading` | `""` | Subheading |
| `font` | `Impact` | Font |
| `font_size` / `hook_font_size` | `100` | Ukuran heading |
| `top_font_size` / `hook_top_font_size` | `30%` dari font_size | Ukuran text atas |
| `sub_font_size` / `hook_sub_font_size` | `40%` dari font_size | Ukuran subheading |
| `color` | `#2F54EB` | Warna background box |
| `stroke_width` | `2` | Ketebalan outline text |
| `stroke_color` | `#000000` | Warna outline |
| `top_gap` | `15` | Jarak atas heading |
| `bottom_gap` | `15` | Jarak bawah heading |
| `line_spacing` | `20` | Spasi antar baris dalam section |
| `position` | `80` | Posisi vertikal (0-100 persen) |

### Contoh Payload
```json
{
  "hook_styles": {
    "hook_style": "preset-4",
    "top_text": "TOP 5",
    "headline": "TIPS TRADING",
    "subheading": "Untuk pemula",
    "font": "Poppins-Bold",
    "font_size": 100,
    "color": "#FF5722",
    "position": 70
  }
}
```

### Fitur Khusus
- Auto-wrap text jika terlalu panjang
- Auto-scale jika text melebihi 90% lebar video
- Shadow di belakang box

### Edit Default
File: `preset4_hook.py`, baris 16-58.

---

## Referensi Warna Hex

| Warna | Kode |
|-------|------|
| Putih | `#FFFFFF` |
| Hitam | `#000000` |
| Merah | `#FF0000` |
| Kuning Neon | `#CBFF00` |
| Biru | `#2F54EB` |
| Orange | `#FF5722` |
| Hijau | `#00FF00` |
| Cyan | `#00FFFF` |
| Magenta | `#FF00FF` |
| Emas | `#FFD700` |

---

## 3 Cara Konfigurasi

### 1. Via API Request (per job)

**POST /process** (form-data):
```
hook_style: preset-2
```
Backend otomatis membuat `hook_styles` dict dari parameter form.

**POST /manual_transcript_import** (JSON):
```json
{
  "video_path": "D:/path/to/video.mp4",
  "phrase_timings": [...],
  "clips_data": [...],
  "hook_styles": {
    "hook_style": "preset-2",
    "preset2_content": "This is **AMAZING** content",
    "font": "Poppins-Black",
    "highlight_color": "#CBFF00"
  }
}
```

### 2. Edit Default di File Python (permanen)

Edit baris default di file preset yang sesuai. Contoh untuk Preset 2:

```python
# preset2_hook.py baris 77-89
highlight_color = hook_styles.get('highlight_color', '#CBFF00')  # Ganti warna default
base_color = hook_styles.get('base_color', '#FFFFFF')
font_name = hook_styles.get('font', 'Impact')  # Ganti font default
font_size = hook_styles.get('font_size', 80)    # Ganti ukuran default
```

### 3. Edit Routing Logic

Jika ingin menambah preset baru atau mengubah behavior:
- File: `video_cutter.py`, baris ~1166-1253
- Tambah kondisi `elif hook_style == 'preset-5':`
- Import renderer baru dari `services/media/subtitle/`

---

## Troubleshooting

### Hook tidak muncul
- **Preset 2:** Pastikan `preset2_content` tidak kosong. Jika kosong, akan return None dan fallback ke Preset 1.
- **Preset 1:** Pastikan file `static/background/background_hook.png` ada.
- **Semua preset:** Pastikan `hook_styles` adalah **dict** (bukan string). Payload `"hook_style": "preset2"` (string) TIDAK bekerja — gunakan `"hook_styles": {"hook_style": "preset-2"}`.

### Font tidak berubah
- Pastikan nama font sesuai dengan file di `static/fonts/` (tanpa ekstensi).
- Jika font tidak ditemukan, fallback ke Impact → Arial → Default.
- Periksa log console untuk `[WARN] Font Load Failed`.

### Text terpotong
- Preset 3 & 4 memiliki auto-fit (ukuran font dikurangi sampai muat).
- Preset 1 & 2 tidak auto-fit — kurangi `font_size` atau persingkat text.

### Glow tidak terlihat (Preset 2)
- Glow hanya muncul pada text yang di-highlight (`**kata**`).
- Pastikan ada `**` di sekitar kata yang ingin di-highlight.
- Jika background video terlalu terang, glow mungkin kurang terlihat — naikkan `stroke_width`.

---

*Guide updated: 2026-04-06*
