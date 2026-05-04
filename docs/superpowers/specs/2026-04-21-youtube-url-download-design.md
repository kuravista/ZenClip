# YouTube/URL Download Feature — Design Spec

## Problem

Frontend only supports file upload. Users must manually download YouTube videos before processing. The backend already has full URL download support (`YtDownloader`, `/process` url param, `/api/yt-preview`) but the frontend never exposes it.

## Solution

Add a tab toggle ("Upload File" | "YouTube / URL") at the top of `ProcessForm.tsx`. When URL mode is selected, show a URL input, preview card (fetched from `/api/yt-preview`), and quality selector. On submit, send `url` + `yt_quality` to the existing `/process` endpoint instead of a file.

## Scope

- **Modified files**: `ProcessForm.tsx`, `App.tsx`
- **No backend changes** — all endpoints already exist

## Data Flow

```
User pastes URL → clicks Preview
  → POST /api/yt-preview { url }     (use API_URL directly, same as /process)
  ← { status: "success", metadata: { title, duration, thumbnail, available_qualities } }
  → Show preview card + quality dropdown

User clicks Process
  → POST /process (FormData with url + yt_quality, no video_file)
  → Backend downloads via yt-dlp, then runs full pipeline
```

## Interface Changes

### ProcessFormData

Add three fields:

```typescript
videoSource: 'file' | 'url';
videoUrl: string;
ytQuality: string;
```

### ProcessForm.tsx

**New state:**

| State | Type | Default | Purpose |
|-------|------|---------|---------|
| `videoSource` | `'file' \| 'url'` | `'file'` | Tab selection |
| `videoUrl` | `string` | `''` | Pasted URL |
| `ytQuality` | `string` | `'720p'` | Selected quality |
| `ytPreview` | `object \| null` | `null` | Metadata from `/api/yt-preview` |
| `ytPreviewLoading` | `boolean` | `false` | Loading state |
| `ytPreviewError` | `string \| null` | `null` | Error message |

**API call pattern:**

Use `API_URL` (hardcoded `http://127.0.0.1:9478`) directly for the preview fetch — consistent with how `App.tsx` calls `/process`. Do NOT use relative proxy path.

**UI layout (URL mode):**

```
[Upload File] [YouTube / URL]          ← tab toggle

[ URL input field                     ] [Preview]

┌─────────────────────────────────────────────┐
│ [thumbnail]  Title                          │
│              Duration: 12:34 · Uploader     │
│              Quality: [720p ▼]              │
└─────────────────────────────────────────────┘

(submit button: "Process from URL")
```

**Validation rules:**

- Submit disabled until either: file selected (file mode) or preview loaded (URL mode)
- Preview button disabled while: URL is empty, OR `ytPreviewLoading` is true
- URL must start with `http`

**State reset rules:**

- Switching to "Upload File" tab: clear `ytPreview`, `ytPreviewError`
- Switching to "YouTube / URL" tab: clear `videoFile`
- Changing URL input text: clear `ytPreview` and `ytPreviewError` (stale preview invalid)

### App.tsx

In `handleProcess`, the `url`/`yt_quality` append happens BEFORE the endpoint selection (`/process` vs `/extract_transcript`), so both code paths work:

```typescript
// Source: file or URL
if (data.videoSource === 'url') {
  formData.append('url', data.videoUrl);
  formData.append('yt_quality', data.ytQuality);
  // Do NOT append video_file
} else {
  formData.append('video_file', data.video);
}

// ... rest of FormData (hooks, subtitles, aspect ratio, api key/provider) ...

// Endpoint selection (both support url + yt_quality)
const endpoint = data.reviewTranscript ? '/extract_transcript' : '/process';
```

**Status message:** Update conditionally based on source:

```typescript
setStatusMessage(data.videoSource === 'url' ? 'Downloading and processing...' : 'Uploading and processing...');
```

## Error Handling

| Scenario | Behavior |
|----------|----------|
| URL not supported by yt-dlp | Extract `error` field from JSON response (`response.error`), display as string |
| Network error during preview | Show generic error message |
| Download fails during processing | Existing job error flow handles this |

Preview error extraction: `response.error` (string), NOT the full response object.

## Styling

Follows existing patterns: Tailwind utility classes, same border/rounded/padding as current form elements. Tab toggle uses same pattern as main nav tabs (`bg-blue-600 text-white` for active).
