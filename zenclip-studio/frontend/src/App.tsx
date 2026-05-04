import React, { useState, useEffect, useCallback, useRef } from 'react';
import { ProcessForm, GalleryGrid, TranscriptEditor, OverviewPanel, JobStatusPanel, SettingsPanel, LibraryPanel } from './components';

const API_URL = 'http://127.0.0.1:9478';

type Tab = 'process' | 'gallery' | 'transcript' | 'overview' | 'settings';

interface Video {
  path: string;
  filename: string;
  thumbnail?: string;
  duration?: number;
  size?: number;
  created?: number;
}

interface Phrase {
  text: string;
  start: number;
  end: number;
  words?: { text: string; start: number; end: number }[];
}

interface JobProgress {
  status: string;
  percentage: number;
  message: string;
  error?: string;
  clips?: { filename: string; path: string }[];
}

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>('process');
  const [isProcessing, setIsProcessing] = useState(false);
  const [statusMessage, setStatusMessage] = useState('');
  const [videos, setVideos] = useState<Video[]>([]);
  const [phrases, setPhrases] = useState<Phrase[]>([]);
  const [galleryLoading, setGalleryLoading] = useState(false);

  // Job tracking
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [jobProgress, setJobProgress] = useState<JobProgress | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startTimeRef = useRef<number>(0);

  // Smooth progress interpolation
  const [displayPercentage, setDisplayPercentage] = useState(0);
  const targetPercentageRef = useRef(0);
  const interpolateRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // System resources
  const [sysResources, setSysResources] = useState<{
    cpu: number; cpuCores: number; ramTotal: number; ramUsed: number; ramAvail: number;
  } | null>(null);
  const resPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const pollResources = useCallback(() => {
    if (resPollRef.current) clearInterval(resPollRef.current);
    const tick = async () => {
      try {
        const res = await fetch('/api/resources');
        if (res.ok) {
          const d = await res.json();
          setSysResources({
            cpu: d.cpu?.usage_percent ?? 0,
            cpuCores: d.cpu?.total_cores ?? 0,
            ramTotal: d.memory?.total_gb ?? 0,
            ramUsed: d.memory?.used_percent ?? 0,
            ramAvail: d.memory?.available_gb ?? 0,
          });
        }
      } catch { /* ignore */ }
    };
    void tick();
    resPollRef.current = setInterval(tick, 3000);
  }, []);

  // Start resource polling when processing
  useEffect(() => {
    if (isProcessing) {
      pollResources();
    } else {
      if (resPollRef.current) { clearInterval(resPollRef.current); resPollRef.current = null; }
    }
    return () => { if (resPollRef.current) clearInterval(resPollRef.current); };
  }, [isProcessing, pollResources]);

  // Load saved settings (API key, provider)
  const [savedSettings, setSavedSettings] = useState<{ apiKey?: string; apiProvider?: string; openrouterApiKey?: string }>({});

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API_URL}/api/settings`);
        if (res.ok) {
          const data = await res.json();
          setSavedSettings(data);
        }
      } catch (e) {
        console.error('Settings load error:', e);
      }
    })();
  }, []);

  const fetchGallery = useCallback(async () => {
    setGalleryLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/videos`);
      if (res.ok) {
        const data = await res.json();
        const allVideos = [
          ...(data.clips || []),
          ...(data.uploads || []),
          ...(data.downloads || []),
        ];
        setVideos(allVideos);
      }
    } catch (e) {
      console.error('Gallery fetch error:', e);
    } finally {
      setGalleryLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchGallery();
  }, [fetchGallery]);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (interpolateRef.current) clearInterval(interpolateRef.current);
    };
  }, []);

  // Start smooth interpolation animation
  const startInterpolation = () => {
    if (interpolateRef.current) clearInterval(interpolateRef.current);

    interpolateRef.current = setInterval(() => {
      setDisplayPercentage((prev) => {
        const target = targetPercentageRef.current;
        if (prev >= target) return prev;
        // Move 0.5% closer every 200ms = smooth ramp
        const step = Math.max(0.3, (target - prev) * 0.08);
        const next = prev + step;
        return next >= target ? target : next;
      });
    }, 200);
  };

  const stopInterpolation = () => {
    if (interpolateRef.current) {
      clearInterval(interpolateRef.current);
      interpolateRef.current = null;
    }
  };

  const startPolling = (jobId: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    startInterpolation();

    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${API_URL}/status/${jobId}`);
        if (!res.ok) return;
        const data = await res.json();

        const rawPct = data.progress || 0;
        targetPercentageRef.current = rawPct;

        const progress: JobProgress = {
          status: data.status,
          percentage: rawPct,
          message: data.msg || data.status,
          error: data.error,
          clips: data.clips,
        };
        setJobProgress(progress);

        // Stop polling when done
        if (['complete', 'error', 'cancelled'].includes(data.status)) {
          if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
          setDisplayPercentage(rawPct);
          stopInterpolation();
          setIsProcessing(false);

          if (data.status === 'complete') {
            const elapsed = ((Date.now() - startTimeRef.current) / 1000);
            const mins = Math.floor(elapsed / 60);
            const secs = Math.floor(elapsed % 60);
            const timeStr = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
            setStatusMessage(`Done! ${data.clips?.length || 0} clips generated in ${timeStr}.`);
            fetchGallery();
          } else if (data.status === 'error') {
            setStatusMessage(`Error: ${data.error || 'Unknown error'}`);
          }
        }

        // Waiting for review - load transcript and switch tab
        if (data.status === 'waiting_review') {
          if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
          stopInterpolation();
          setIsProcessing(false);

          // Fetch full transcript data
          try {
            const tr = await fetch(`${API_URL}/get_transcript/${jobId}`);
            if (tr.ok) {
              const trData = await tr.json();
              if (trData.phrase_timings) {
                setPhrases(trData.phrase_timings);
              }
            }
          } catch (e) {
            console.error('Transcript fetch error:', e);
          }

          setStatusMessage('Transcript ready for review. Go to Transcript tab to edit.');
          setJobProgress(prev => prev ? { ...prev, status: 'waiting_review', percentage: 70, message: 'Waiting for review...' } : null);
          setActiveTab('transcript');
        }
      } catch (e) {
        console.error('Poll error:', e);
      }
    }, 2000);
  };

  const handleCancelJob = async () => {
    if (!activeJobId) return;
    try {
      await fetch(`${API_URL}/api/cancel_job/${activeJobId}`, { method: 'POST' });
      setStatusMessage('Job cancelled.');
      setIsProcessing(false);
      setJobProgress(null);
      setActiveJobId(null);
      stopInterpolation();
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    } catch (e) {
      console.error('Cancel error:', e);
    }
  };

  const handleProcess = async (data: Record<string, unknown>) => {
    setIsProcessing(true);
    setJobProgress(null);
    setDisplayPercentage(0);
    targetPercentageRef.current = 0;
    startTimeRef.current = Date.now();
    setStatusMessage(data.videoSource === 'url' ? 'Downloading and processing...' : 'Uploading and processing...');
    try {
      const formData = new FormData();

      if (data.videoSource === 'url') {
        formData.append('url', String(data.videoUrl));
        formData.append('yt_quality', String(data.ytQuality || '720p'));
      } else if (data.video instanceof File) {
        formData.append('video_file', data.video);
      }

      formData.append('video_aspect', String(data.aspectRatio || '9:16'));
      formData.append('subtitle_style', String(data.subtitleStyle || 'shadow'));
      formData.append('num_clips', String(data.clipCount || 5));
      formData.append('min_duration', String(data.targetDuration || 60));
      formData.append('add_subtitles', String(data.addSubtitles ? 'true' : 'false'));
      formData.append('add_viral_hook', String(data.addHook ? 'true' : 'false'));
      formData.append('add_watermark', String(data.addWatermark ? 'true' : 'false'));

      // Watermark config from saved settings
      if (data.addWatermark) {
        formData.append('watermark_type', 'text');
        formData.append('watermark_text', savedSettings.watermark_text || 'ZenClip');
        formData.append('watermark_opacity', String(savedSettings.watermark_opacity ?? 0.5));
        formData.append('watermark_position', savedSettings.watermark_position || 'bottom_right');
        formData.append('watermark_size', String(savedSettings.watermark_size ?? 0.3));
        formData.append('watermark_font', savedSettings.watermark_font || 'Arial-Bold');
      }
      formData.append('transcription_mode', 'fast');
      formData.append('video_type', 'general');

      // Hook parameters - match backend Form() field names
      formData.append('hook_style', String(data.hookStyle || 'preset-2'));
      formData.append('hook_font', String(data.hookFont || 'Impact'));
      formData.append('hook_font_size', String(data.hookFontSize || 80));
      formData.append('hook_heading_color', String(data.hookHeadingColor || '#FF0000'));
      formData.append('hook_stroke_color', String(data.hookStrokeColor || '#000000'));
      formData.append('hook_stroke_width', String(data.hookStrokeWidth ?? 2));
      formData.append('hook_position', String(data.hookPosition || 'top'));
      formData.append('hook_top_text', String(data.hookTopText || ''));
      formData.append('hook_headline', String(data.hookHeadline || ''));
      formData.append('hook_subheading', String(data.hookSubheading || ''));
      formData.append('hook_preset2_text', String(data.hookPreset2Text || ''));
      formData.append('hook_highlight_color', String(data.hookHighlightColor || '#CBFF00'));
      formData.append('hook_full_duration', String(data.hookFullDuration ? 'true' : 'false'));

      // Quality preset
      formData.append('quality_preset', String(data.qualityPreset || 'balanced'));

      // Subtitle config from saved settings (font, colors, etc.)
      formData.append('subtitle_font_family', savedSettings.subtitle_font_family || 'Arial');
      formData.append('subtitle_font_size', String(savedSettings.subtitle_font_size ?? 45));
      formData.append('subtitle_text_color', savedSettings.subtitle_text_color || '#FFFF00');
      formData.append('subtitle_stroke_color', savedSettings.subtitle_stroke_color || '#000000');
      formData.append('subtitle_stroke_width', String(savedSettings.subtitle_stroke_width ?? 3));
      formData.append('subtitle_bg_color', savedSettings.subtitle_bg_color || '#2563eb');
      formData.append('subtitle_bg_opacity', String(savedSettings.subtitle_bg_opacity ?? 0.75));
      formData.append('subtitle_position', String(savedSettings.subtitle_position ?? 75));

      // Randomize metadata from saved settings
      formData.append('randomize_metadata', String(savedSettings.randomize_metadata === true ? 'true' : 'false'));

      // API key & provider from saved settings
      const apiProvider = savedSettings.apiProvider || 'gemini';
      let apiKey = savedSettings.apiKey || '';
      // Use provider-specific key if available
      if (apiProvider === 'openrouter' && savedSettings.openrouterApiKey) {
        apiKey = savedSettings.openrouterApiKey;
      }
      formData.append('api_key', apiKey);
      formData.append('api_provider', apiProvider);

      // Use extract_transcript endpoint if review mode, else process directly
      const endpoint = data.reviewTranscript ? '/extract_transcript' : '/process';
      const res = await fetch(`${API_URL}${endpoint}`, {
        method: 'POST',
        body: formData,
      });

      if (res.ok) {
        const result = await res.json();
        const jobId = result.job_id || 'unknown';
        setActiveJobId(jobId);
        setStatusMessage(`Job started: ${jobId}`);
        setJobProgress({ status: 'queued', percentage: 0, message: 'Queued...' });
        startPolling(jobId);
      } else {
        const err = await res.text();
        setStatusMessage(`Error: ${err}`);
        setIsProcessing(false);
      }
    } catch (e) {
      setStatusMessage(`Error: ${e instanceof Error ? e.message : 'Unknown error'}`);
      setIsProcessing(false);
    }
  };

  const handleDeleteVideos = async (paths: string[]) => {
    try {
      for (const p of paths) {
        await fetch(`${API_URL}/api/videos?path=${encodeURIComponent(p)}`, { method: 'DELETE' });
      }
      fetchGallery();
    } catch (e) {
      console.error('Delete error:', e);
    }
  };

  // Progress bar color based on status
  const getProgressColor = () => {
    if (!jobProgress) return 'bg-blue-500';
    if (jobProgress.status === 'error') return 'bg-red-500';
    if (jobProgress.status === 'complete') return 'bg-green-500';
    return 'bg-blue-500';
  };

  const getStatusBadgeColor = () => {
    if (!jobProgress) return 'bg-blue-100 text-blue-800';
    switch (jobProgress.status) {
      case 'complete': return 'bg-green-100 text-green-800';
      case 'error': return 'bg-red-100 text-red-800';
      case 'cancelled': return 'bg-gray-100 text-gray-800';
      default: return 'bg-blue-100 text-blue-800';
    }
  };

  const tabs: { id: Tab; label: string }[] = [
    { id: 'process', label: 'Process' },
    { id: 'gallery', label: 'Gallery' },
    { id: 'transcript', label: 'Transcript' },
    { id: 'overview', label: 'Overview' },
    { id: 'settings', label: 'Settings' },
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b px-6 py-3 flex items-center gap-4">
        <h1 className="text-xl font-bold text-gray-900">ZenClip <span className="text-sm font-normal text-gray-500">— Clip It Zen</span></h1>
        <nav className="flex gap-1 ml-6">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </header>

      {/* Job Progress Panel */}
      {(jobProgress || isProcessing) && (
        <div className="bg-white border-b px-6 py-4 shadow-sm">
          <div className="max-w-6xl mx-auto">
            {/* Status Header */}
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-3">
                <span className={`px-3 py-1 rounded-full text-xs font-semibold ${getStatusBadgeColor()}`}>
                  {jobProgress?.status?.toUpperCase() || 'STARTING'}
                </span>
                <span className="text-sm text-gray-700">
                  {jobProgress?.message || statusMessage}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-mono font-semibold text-gray-900">
                  {Math.round(displayPercentage)}%
                </span>
                {isProcessing && (
                  <button
                    onClick={handleCancelJob}
                    className="px-3 py-1 text-xs bg-red-100 text-red-700 rounded hover:bg-red-200"
                  >
                    Cancel
                  </button>
                )}
              </div>
            </div>

            {/* Progress Bar */}
            <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden">
              <div
                className={`h-full rounded-full ${getProgressColor()}`}
                style={{ width: `${displayPercentage}%`, transition: 'width 0.2s linear' }}
              />
            </div>

            {/* Job ID */}
            {activeJobId && (
              <p className="text-xs text-gray-400 mt-1 font-mono">
                Job: {activeJobId}
              </p>
            )}

            {/* System Resources */}
            {sysResources && isProcessing && (
              <div className="mt-3 flex gap-4">
                {/* CPU */}
                <div className="flex-1">
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-gray-600">CPU</span>
                    <span className="font-mono font-semibold">{sysResources.cpu.toFixed(1)}%</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${
                        sysResources.cpu > 90 ? 'bg-red-500' : sysResources.cpu > 70 ? 'bg-yellow-500' : 'bg-green-500'
                      }`}
                      style={{ width: `${Math.min(100, sysResources.cpu)}%` }}
                    />
                  </div>
                  <p className="text-[10px] text-gray-400 mt-0.5">{sysResources.cpuCores} cores</p>
                </div>
                {/* RAM */}
                <div className="flex-1">
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-gray-600">RAM</span>
                    <span className="font-mono font-semibold">{sysResources.ramUsed.toFixed(1)}%</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${
                        sysResources.ramUsed > 90 ? 'bg-red-500' : sysResources.ramUsed > 75 ? 'bg-yellow-500' : 'bg-green-500'
                      }`}
                      style={{ width: `${Math.min(100, sysResources.ramUsed)}%` }}
                    />
                  </div>
                  <p className="text-[10px] text-gray-400 mt-0.5">
                    {sysResources.ramAvail.toFixed(1)} / {sysResources.ramTotal.toFixed(1)} GB free
                  </p>
                </div>
              </div>
            )}

            {/* Clips result */}
            {jobProgress?.status === 'complete' && jobProgress.clips && (
              <div className="mt-3 p-3 bg-green-50 border border-green-200 rounded">
                <p className="text-sm font-medium text-green-800 mb-1">
                  {jobProgress.clips.length} clips generated successfully! {statusMessage.replace('Done! ', '')}
                </p>
                <button
                  onClick={() => { setActiveTab('gallery'); fetchGallery(); }}
                  className="text-xs text-green-700 underline"
                >
                  View in Gallery
                </button>
              </div>
            )}

            {/* Error */}
            {jobProgress?.status === 'error' && jobProgress.error && (
              <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded">
                <p className="text-sm text-red-800">{jobProgress.error}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Content */}
      <main className="max-w-6xl mx-auto p-6">
        {activeTab === 'process' && (
          <ProcessForm
            onSubmit={(data) => handleProcess(data as Record<string, unknown>)}
            isProcessing={isProcessing}
          />
        )}

        {activeTab === 'gallery' && (
          <GalleryGrid
            videos={videos}
            onPlay={(video) => console.log('Play:', video)}
            onDelete={handleDeleteVideos}
            onRefresh={fetchGallery}
            isLoading={galleryLoading}
          />
        )}

        {activeTab === 'transcript' && (
          <TranscriptEditor
            phrases={phrases}
            jobId={activeJobId}
            onSave={setPhrases}
            onProcess={() => {
              setActiveTab('process');
              if (activeJobId) {
                setIsProcessing(true);
                setJobProgress({ status: 'processing', percentage: 70, message: 'Processing with edited transcript...' });
                targetPercentageRef.current = 70;
                startPolling(activeJobId);
              }
            }}
          />
        )}

        {activeTab === 'overview' && (
          <OverviewPanel
            onRefresh={fetchGallery}
            onSettingsChange={() => setActiveTab('settings')}
          />
        )}

        {activeTab === 'settings' && (
          <SettingsPanel onSave={async (s) => console.log('Settings saved:', s)} />
        )}
      </main>
    </div>
  );
}
