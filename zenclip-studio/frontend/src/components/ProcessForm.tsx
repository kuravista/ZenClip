import React from 'react';
import { HookPreview } from './HookPreview';

const API_URL = 'http://127.0.0.1:9478';

interface ProcessFormProps {
  onSubmit: (data: ProcessFormData) => void;
  isProcessing: boolean;
}

export interface ProcessFormData {
  video: File | null;
  videoSource: 'file' | 'url';
  videoUrl: string;
  ytQuality: string;
  aspectRatio: string;
  subtitleStyle: string;
  hookStyle: string;
  addSubtitles: boolean;
  addHook: boolean;
  addWatermark: boolean;
  targetDuration: number;
  clipCount: number;
  reviewTranscript: boolean;
  // Hook customization
  hookFont: string;
  hookFontSize: number;
  hookHeadingColor: string;
  hookStrokeColor: string;
  hookStrokeWidth: number;
  hookPosition: string;
  hookTopText: string;
  hookHeadline: string;
  hookSubheading: string;
  hookPreset2Text: string;
  hookHighlightColor: string;
  hookFullDuration: boolean;
  qualityPreset: string;
}

interface YtPreviewMetadata {
  title: string;
  duration: number | null;
  thumbnail: string | null;
  description: string;
  uploader: string;
  available_qualities: string[];
}

const SUBTITLE_STYLES: Record<string, { name: string; desc: string; visual: string; anim: string }> = {
  shadow:     { name: 'Shadow',       desc: 'Classic subtitle look',        visual: 'White text + deep black shadow',            anim: 'Slide-up + fade' },
  elegant:    { name: 'Elegant',      desc: 'Cinematic dual-font',          visual: 'Poppins white + Playfair green italic',     anim: 'Blur-to-focus reveal' },
  boxies:     { name: 'Boxies',       desc: 'Two-line with colored box',    visual: 'UPPERCASE line 1 + blue box behind line 2', anim: 'Delayed fade-in line 2' },
  mozi:       { name: 'Mozi',         desc: 'Word-by-word highlight',       visual: 'Active word bright green + 1.5x size',      anim: 'Per-word highlight sweep' },
  pod_d:      { name: 'Pod D',        desc: 'Soft pastel look',             visual: 'Pastel pink text + thick black stroke',     anim: 'Pop-in scale bounce' },
  rapid_fire: { name: 'Rapid Fire',   desc: 'One word at a time',           visual: 'Single huge word + thick black outline',    anim: 'Pop-in scale 120%\u2192100%' },
  rapid_pro:  { name: 'Rapid Pro',    desc: 'Neon glow effect',             visual: 'Yellow highlighted words + soft glow',      anim: 'Dual-layer glow + fade' },
  karaoke:    { name: 'Karaoke',      desc: 'Sing-along highlight',         visual: 'Active word yellow + blue box, rest dim',   anim: 'Word-by-word color sweep' },
  prince:     { name: 'Prince',       desc: 'Premium dual-font',            visual: 'Poppins + Playfair italic for key words',   anim: 'Zoom-in + fade' },
};

const PRESET_INFO: Record<string, { name: string; desc: string }> = {
  'preset-1': { name: 'Classic Box', desc: 'Background image + heading + subheading overlay' },
  'preset-2': { name: 'Glow Text', desc: 'Word-by-word highlight with neon glow effect' },
  'preset-3': { name: 'Viral Stack', desc: '3-line stacked text: colored + white + badge' },
  'preset-4': { name: 'Simple Box', desc: 'All text inside a rounded-corner colored box' },
};

export function ProcessForm({ onSubmit, isProcessing }: ProcessFormProps) {
  const [formData, setFormData] = React.useState<Partial<ProcessFormData>>({
    aspectRatio: '9:16',
    subtitleStyle: 'shadow',
    hookStyle: 'preset-2',
    addSubtitles: true,
    addHook: true,
    addWatermark: false,
    reviewTranscript: false,
    targetDuration: 60,
    clipCount: 5,
    // Hook defaults
    hookFont: 'Impact',
    hookFontSize: 80,
    hookHeadingColor: '#FF0000',
    hookStrokeColor: '#000000',
    hookStrokeWidth: 2,
    hookPosition: 'top',
    hookTopText: '',
    hookHeadline: '',
    hookSubheading: '',
    hookPreset2Text: '',
    hookHighlightColor: '#CBFF00',
    hookFullDuration: false,
    qualityPreset: 'balanced',
  });

  const [videoFile, setVideoFile] = React.useState<File | null>(null);
  const [showHookSettings, setShowHookSettings] = React.useState(false);
  const [videoSource, setVideoSource] = React.useState<'file' | 'url'>('file');
  const [videoUrl, setVideoUrl] = React.useState('');
  const [ytQuality, setYtQuality] = React.useState('720p');

  // Load visual defaults from backend user_settings.json
  React.useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API_URL}/api/settings`);
        if (!res.ok) return;
        const s = await res.json();
        setFormData((prev) => ({
          ...prev,
          // Hook defaults
          hookStyle: s.hook_style || prev.hookStyle,
          hookFont: s.hook_font || prev.hookFont,
          hookFontSize: s.hook_font_size ? Number(s.hook_font_size) : prev.hookFontSize,
          hookHeadingColor: s.hook_heading_color || prev.hookHeadingColor,
          hookStrokeColor: s.hook_stroke_color || prev.hookStrokeColor,
          hookStrokeWidth: s.hook_stroke_width != null ? Number(s.hook_stroke_width) : prev.hookStrokeWidth,
          hookPosition: s.hook_position || prev.hookPosition,
          hookHighlightColor: s.hook_highlight_color || prev.hookHighlightColor,
          // Subtitle defaults
          subtitleStyle: s.defaultSubtitleStyle || prev.subtitleStyle,
          // Watermark
          addWatermark: s.watermark_enabled === true,
        }));
      } catch (e) {
        // Settings load is optional — keep hardcoded defaults
      }
    })();
  }, []);
  const [ytPreview, setYtPreview] = React.useState<YtPreviewMetadata | null>(null);
  const [ytPreviewLoading, setYtPreviewLoading] = React.useState(false);
  const [ytPreviewError, setYtPreviewError] = React.useState<string | null>(null);

  const set = (key: string, value: unknown) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (videoSource === 'file' && videoFile) {
      onSubmit({ ...formData, videoSource: 'file', video: videoFile, videoUrl: '', ytQuality: '' } as ProcessFormData);
    } else if (videoSource === 'url' && ytPreview) {
      onSubmit({ ...formData, videoSource: 'url', video: null, videoUrl, ytQuality } as ProcessFormData);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) {
      setVideoFile(e.target.files[0]);
    }
  };

  const handleUrlChange = (url: string) => {
    setVideoUrl(url);
    // Clear stale preview when URL changes
    setYtPreview(null);
    setYtPreviewError(null);
  };

  const handlePreview = async () => {
    if (!videoUrl.trim()) return;
    setYtPreviewLoading(true);
    setYtPreviewError(null);
    setYtPreview(null);
    try {
      const res = await fetch(`${API_URL}/api/yt-preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: videoUrl.trim() }),
      });
      const data = await res.json();
      if (!res.ok) {
        setYtPreviewError(data.error || 'Failed to fetch video info');
        return;
      }
      setYtPreview(data.metadata);
      // Auto-select first available quality if current not available
      const qualities: string[] = data.metadata.available_qualities || [];
      if (qualities.length && !qualities.includes(ytQuality)) {
        setYtQuality(qualities[0]);
      }
    } catch {
      setYtPreviewError('Network error. Is the backend running?');
    } finally {
      setYtPreviewLoading(false);
    }
  };

  const handleSourceSwitch = (source: 'file' | 'url') => {
    setVideoSource(source);
    if (source === 'file') {
      setYtPreview(null);
      setYtPreviewError(null);
    } else {
      setVideoFile(null);
    }
  };

  const formatDuration = (seconds: number | null): string => {
    if (seconds == null) return 'Unknown';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  const canSubmit = videoSource === 'file' ? !!videoFile : !!ytPreview;

  const preset = formData.hookStyle || 'preset-2';
  const presetInfo = PRESET_INFO[preset];

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Video Source Tabs */}
      <div>
        <div className="flex border-b mb-3">
          <button
            type="button"
            onClick={() => handleSourceSwitch('file')}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              videoSource === 'file'
                ? 'border-b-2 border-blue-600 text-blue-600'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            Upload File
          </button>
          <button
            type="button"
            onClick={() => handleSourceSwitch('url')}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              videoSource === 'url'
                ? 'border-b-2 border-blue-600 text-blue-600'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            YouTube / URL
          </button>
        </div>

        {/* File Upload */}
        {videoSource === 'file' && (
          <div>
            <input
              type="file"
              accept="video/*"
              onChange={handleFileChange}
              className="block w-full text-sm text-gray-500 file:mr-4 py-2 px-3 border rounded"
            />
            {videoFile && <p className="text-sm text-green-600 mt-1">{videoFile.name}</p>}
          </div>
        )}

        {/* URL Input + Preview */}
        {videoSource === 'url' && (
          <div className="space-y-3">
            <div className="flex gap-2">
              <input
                type="text"
                value={videoUrl}
                onChange={(e) => handleUrlChange(e.target.value)}
                placeholder="https://www.youtube.com/watch?v=..."
                className="block w-full border rounded px-3 py-2 text-sm"
              />
              <button
                type="button"
                onClick={handlePreview}
                disabled={!videoUrl.trim() || ytPreviewLoading}
                className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-sm font-medium rounded disabled:opacity-50 whitespace-nowrap"
              >
                {ytPreviewLoading ? 'Loading...' : 'Preview'}
              </button>
            </div>

            {ytPreviewError && (
              <p className="text-sm text-red-600">{ytPreviewError}</p>
            )}

            {ytPreview && (
              <div className="border rounded-lg p-3 bg-gray-50 flex gap-3">
                {ytPreview.thumbnail && (
                  <img
                    src={ytPreview.thumbnail}
                    alt="Thumbnail"
                    className="w-32 h-20 object-cover rounded"
                  />
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-800 truncate">{ytPreview.title}</p>
                  <p className="text-xs text-gray-500 mt-1">
                    {formatDuration(ytPreview.duration)}
                    {ytPreview.uploader && ` · ${ytPreview.uploader}`}
                  </p>
                  <div className="mt-2">
                    <select
                      value={ytQuality}
                      onChange={(e) => setYtQuality(e.target.value)}
                      className="border rounded px-2 py-1 text-xs"
                    >
                      {ytPreview.available_qualities.map((q) => (
                        <option key={q} value={q}>{q}</option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Aspect Ratio */}
      <div>
        <label className="block text-sm font-medium mb-2">Aspect Ratio</label>
        <select
          value={formData.aspectRatio}
          onChange={(e) => set('aspectRatio', e.target.value)}
          className="block w-full border rounded px-3 py-2"
        >
          <option value="9:16">9:16 (Vertical)</option>
          <option value="16:9">16:9 (Horizontal)</option>
          <option value="1:1">1:1 (Square)</option>
        </select>
      </div>

      {/* Subtitle Style */}
      <div>
        <label className="block text-sm font-medium mb-2">Subtitle Style</label>
        <select
          value={formData.subtitleStyle}
          onChange={(e) => set('subtitleStyle', e.target.value)}
          className="block w-full border rounded px-3 py-2 mb-2"
        >
          {Object.entries(SUBTITLE_STYLES).map(([key, info]) => (
            <option key={key} value={key}>{info.name} — {info.desc}</option>
          ))}
        </select>
        {/* Style info card */}
        {formData.subtitleStyle && SUBTITLE_STYLES[formData.subtitleStyle] && (
          <div className="bg-gray-50 border rounded-lg p-3 text-xs space-y-1">
            <div className="flex items-center gap-2 font-semibold text-sm text-gray-800">
              <span>{SUBTITLE_STYLES[formData.subtitleStyle].name}</span>
              <span className="font-normal text-gray-500">— {SUBTITLE_STYLES[formData.subtitleStyle].desc}</span>
            </div>
            <div className="flex gap-4 text-gray-600">
              <span><span className="font-medium text-gray-700">Visual:</span> {SUBTITLE_STYLES[formData.subtitleStyle].visual}</span>
            </div>
            <div className="flex gap-4 text-gray-600">
              <span><span className="font-medium text-gray-700">Animation:</span> {SUBTITLE_STYLES[formData.subtitleStyle].anim}</span>
            </div>
          </div>
        )}
      </div>

      {/* Clip Settings */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium mb-2">Target Duration (s)</label>
          <input
            type="number"
            value={formData.targetDuration}
            onChange={(e) => set('targetDuration', parseInt(e.target.value) || 60)}
            className="block w-full border rounded px-3 py-2"
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-2">Clip Count</label>
          <input
            type="number"
            value={formData.clipCount}
            onChange={(e) => set('clipCount', parseInt(e.target.value) || 5)}
            className="block w-full border rounded px-3 py-2"
          />
        </div>
      </div>

      {/* Quality / Speed Preset */}
      <div>
        <label className="block text-sm font-medium mb-2">Quality / Speed</label>
        <select
          value={formData.qualityPreset}
          onChange={(e) => set('qualityPreset', e.target.value)}
          className="block w-full border rounded px-3 py-2"
        >
          <option value="draft">Draft (fastest, lower quality)</option>
          <option value="balanced">Balanced (recommended)</option>
          <option value="quality">Quality (slower, best output)</option>
        </select>
      </div>

      {/* Toggles */}
      <div className="space-y-2">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={formData.addSubtitles}
            onChange={(e) => set('addSubtitles', e.target.checked)}
          />
          <span className="text-sm">Enable Captions</span>
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={formData.addHook}
            onChange={(e) => set('addHook', e.target.checked)}
          />
          <span className="text-sm">Add Viral Hook</span>
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={formData.addWatermark}
            onChange={(e) => set('addWatermark', e.target.checked)}
          />
          <span className="text-sm">Add Watermark</span>
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={formData.reviewTranscript}
            onChange={(e) => set('reviewTranscript', e.target.checked)}
          />
          <span className="text-sm">Review transcript before cutting</span>
          <span className="text-xs text-gray-400">(edit AI result manually)</span>
        </label>
      </div>

      {/* Hook Customization Panel */}
      {formData.addHook && (
        <div className="border rounded-lg overflow-hidden">
          {/* Header - click to expand */}
          <button
            type="button"
            onClick={() => setShowHookSettings(!showHookSettings)}
            className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100 text-left"
          >
            <div>
              <span className="text-sm font-medium">Hook Customization</span>
              <span className="ml-2 text-xs text-gray-500">
                ({presetInfo?.name || 'Unknown'})
              </span>
            </div>
            <span className="text-gray-400 text-xs">
              {showHookSettings ? 'Close' : 'Expand'}
            </span>
          </button>

          {showHookSettings && (
            <div className="p-4 border-t">
              <div className="flex gap-6">
                {/* Left: Preview */}
                <div className="shrink-0">
                  <HookPreview
                    preset={preset}
                    topText={formData.hookTopText || ''}
                    headline={formData.hookHeadline || ''}
                    subheading={formData.hookSubheading || ''}
                    preset2Text={formData.hookPreset2Text || ''}
                    headingColor={formData.hookHeadingColor || '#FF0000'}
                    highlightColor={formData.hookHighlightColor || '#CBFF00'}
                    strokeColor={formData.hookStrokeColor || '#000000'}
                    position={formData.hookPosition || 'top'}
                    fullDuration={formData.hookFullDuration || false}
                  />
                </div>

                {/* Right: Controls */}
                <div className="flex-1 space-y-4 min-w-0">
              {/* Preset Selector */}
              <div>
                <label className="block text-sm font-medium mb-2">Hook Preset</label>
                <div className="grid grid-cols-2 gap-2">
                  {Object.entries(PRESET_INFO).map(([key, info]) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => set('hookStyle', key)}
                      className={`p-3 border rounded text-left transition-colors ${
                        preset === key
                          ? 'border-blue-500 bg-blue-50 ring-1 ring-blue-500'
                          : 'border-gray-200 hover:border-gray-300'
                      }`}
                    >
                      <p className="text-sm font-medium">{info.name}</p>
                      <p className="text-xs text-gray-500">{info.desc}</p>
                    </button>
                  ))}
                </div>
              </div>

              {/* Preset 2 specific: content text */}
              {preset === 'preset-2' && (
                <div>
                  <label className="block text-sm font-medium mb-1">
                    Hook Text
                    <span className="font-normal text-gray-500 ml-1">
                      (use **bold** for highlight, *italic* for style)
                    </span>
                  </label>
                  <textarea
                    value={formData.hookPreset2Text}
                    onChange={(e) => set('hookPreset2Text', e.target.value)}
                    placeholder="This is **amazing** and *incredible* to see"
                    className="block w-full border rounded px-3 py-2 text-sm"
                    rows={2}
                  />
                  <p className="text-xs text-gray-400 mt-1">
                    Leave empty to let AI generate hook text automatically
                  </p>
                </div>
              )}

              {/* Preset 1, 3, 4: text fields */}
              {(preset === 'preset-1' || preset === 'preset-3' || preset === 'preset-4') && (
                <div className="space-y-3">
                  <div>
                    <label className="block text-sm font-medium mb-1">Top Label</label>
                    <input
                      type="text"
                      value={formData.hookTopText}
                      onChange={(e) => set('hookTopText', e.target.value)}
                      placeholder="e.g. WATCH THIS"
                      className="block w-full border rounded px-3 py-2 text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Headline</label>
                    <input
                      type="text"
                      value={formData.hookHeadline}
                      onChange={(e) => set('hookHeadline', e.target.value)}
                      placeholder="e.g. VIRAL MOMENT"
                      className="block w-full border rounded px-3 py-2 text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Subheading</label>
                    <input
                      type="text"
                      value={formData.hookSubheading}
                      onChange={(e) => set('hookSubheading', e.target.value)}
                      placeholder="e.g. You won't believe this"
                      className="block w-full border rounded px-3 py-2 text-sm"
                    />
                  </div>
                </div>
              )}

              {/* Style Settings - common */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium mb-1">Font Size</label>
                  <input
                    type="number"
                    min={20}
                    max={200}
                    value={formData.hookFontSize}
                    onChange={(e) => set('hookFontSize', parseInt(e.target.value) || 80)}
                    className="block w-full border rounded px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Stroke Width</label>
                  <input
                    type="number"
                    min={0}
                    max={10}
                    value={formData.hookStrokeWidth}
                    onChange={(e) => set('hookStrokeWidth', parseInt(e.target.value) || 2)}
                    className="block w-full border rounded px-3 py-2 text-sm"
                  />
                </div>
              </div>

              {/* Colors */}
              <div className="grid grid-cols-2 gap-3">
                {preset === 'preset-2' ? (
                  <div>
                    <label className="block text-sm font-medium mb-1">Highlight Color</label>
                    <div className="flex items-center gap-2">
                      <input
                        type="color"
                        value={formData.hookHighlightColor || '#CBFF00'}
                        onChange={(e) => set('hookHighlightColor', e.target.value)}
                        className="w-10 h-8 rounded border cursor-pointer"
                      />
                      <input
                        type="text"
                        value={formData.hookHighlightColor}
                        onChange={(e) => set('hookHighlightColor', e.target.value)}
                        className="block w-full border rounded px-2 py-1 text-sm font-mono"
                      />
                    </div>
                  </div>
                ) : (
                  <div>
                    <label className="block text-sm font-medium mb-1">Heading Color</label>
                    <div className="flex items-center gap-2">
                      <input
                        type="color"
                        value={formData.hookHeadingColor || '#FF0000'}
                        onChange={(e) => set('hookHeadingColor', e.target.value)}
                        className="w-10 h-8 rounded border cursor-pointer"
                      />
                      <input
                        type="text"
                        value={formData.hookHeadingColor}
                        onChange={(e) => set('hookHeadingColor', e.target.value)}
                        className="block w-full border rounded px-2 py-1 text-sm font-mono"
                      />
                    </div>
                  </div>
                )}
                <div>
                  <label className="block text-sm font-medium mb-1">Stroke Color</label>
                  <div className="flex items-center gap-2">
                    <input
                      type="color"
                      value={formData.hookStrokeColor || '#000000'}
                      onChange={(e) => set('hookStrokeColor', e.target.value)}
                      className="w-10 h-8 rounded border cursor-pointer"
                    />
                    <input
                      type="text"
                      value={formData.hookStrokeColor}
                      onChange={(e) => set('hookStrokeColor', e.target.value)}
                      className="block w-full border rounded px-2 py-1 text-sm font-mono"
                    />
                  </div>
                </div>
              </div>

              {/* Position (preset 1) */}
              {preset === 'preset-1' && (
                <div>
                  <label className="block text-sm font-medium mb-1">Position</label>
                  <select
                    value={formData.hookPosition}
                    onChange={(e) => set('hookPosition', e.target.value)}
                    className="block w-full border rounded px-3 py-2 text-sm"
                  >
                    <option value="top">Top</option>
                    <option value="center">Center</option>
                    <option value="bottom">Bottom</option>
                  </select>
                </div>
              )}

              {/* Full duration toggle */}
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={formData.hookFullDuration}
                  onChange={(e) => set('hookFullDuration', e.target.checked)}
                />
                <span className="text-sm">Show hook for entire clip duration</span>
                <span className="text-xs text-gray-400">
                  (default: 3.5s intro only)
                </span>
              </label>

              <p className="text-xs text-gray-400">
                Text fields left empty will be auto-generated by AI based on video content.
              </p>
                </div>{/* end controls */}
              </div>{/* end flex */}
            </div>
          )}
        </div>
      )}

      {/* Submit */}
      <button
        type="submit"
        disabled={isProcessing || !canSubmit}
        className="w-full bg-blue-600 text-white py-2 px-4 rounded disabled:opacity-50"
      >
        {isProcessing ? 'Processing...' : videoSource === 'url' ? 'Process from URL' : 'Start Processing'}
      </button>
    </form>
  );
}
