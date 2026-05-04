import React, { useState, useEffect } from 'react';

type SettingsValue = string | number | boolean | null | undefined;
type SettingsMap = Record<string, SettingsValue>;

const ss = (map: SettingsMap, key: string, fallback: string): string =>
  (typeof map[key] === 'string' ? map[key] : fallback) as string;

const sn = (map: SettingsMap, key: string, fallback: number): number =>
  (typeof map[key] === 'number' ? map[key] : fallback) as number;

interface SettingsPanelProps {
  onSave?: (settings: SettingsMap) => void;
}

export function SettingsPanel({ onSave }: SettingsPanelProps) {
  const [settings, setSettings] = useState<SettingsMap>({});
  const [apiKey, setApiKey] = useState('');
  const [openrouterApiKey, setOpenrouterApiKey] = useState('');
  const [apiProvider, setApiProvider] = useState('gemini');
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => { loadSettings(); }, []);

  const loadSettings = async () => {
    try {
      const res = await fetch('/api/settings');
      const data = await res.json();
      setSettings(data);
      setApiKey(data.apiKey || '');
      setOpenrouterApiKey(data.openrouterApiKey || '');
      setApiProvider(data.apiProvider || 'gemini');
    } catch (error) {
      console.error('Failed to load settings:', error);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setMessage('');
    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...settings, apiKey, openrouterApiKey, apiProvider }),
      });
      if (res.ok) {
        setMessage('Settings saved successfully');
        onSave?.({ ...settings, apiKey, apiProvider });
      } else {
        setMessage('Failed to save settings');
      }
    } catch (error) {
      setMessage('Error saving settings');
    } finally {
      setIsLoading(false);
    }
  };

  const handleChange = (key: string, value: SettingsValue) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  };

  const s = settings;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-semibold">Settings</h2>
        {message && (
          <span className={message.includes('success') ? 'text-green-600' : 'text-red-600'}>
            {message}
          </span>
        )}
      </div>

      <form onSubmit={handleSave} className="space-y-4">
        {/* API Configuration */}
        <div className="border rounded p-4 space-y-4">
          <h3 className="font-medium">API Configuration</h3>
          <div>
            <label className="block text-sm font-medium mb-2">API Provider</label>
            <select value={apiProvider} onChange={(e) => setApiProvider(e.target.value)} className="block w-full border rounded px-3 py-2">
              <option value="gemini">Google Gemini</option>
              <option value="openrouter">OpenRouter</option>
              <option value="deepseek">DeepSeek</option>
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
              <option value="local">Local LLM (Ollama)</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-2">API Key (Primary)</label>
            <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="Enter your API key" className="block w-full border rounded px-3 py-2" />
          </div>
          <div>
            <label className="block text-sm font-medium mb-2">OpenRouter API Key (Fallback)</label>
            <input type="password" value={openrouterApiKey} onChange={(e) => setOpenrouterApiKey(e.target.value)} placeholder="sk-or-v1-..." className="block w-full border rounded px-3 py-2" />
            <p className="text-xs text-gray-500 mt-1">Used as fallback when primary provider is down</p>
          </div>
        </div>

        {/* Processing Defaults */}
        <div className="border rounded p-4 space-y-4">
          <h3 className="font-medium">Processing Defaults</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-2">Default Aspect Ratio</label>
              <select value={ss(s, 'defaultAspectRatio', '9:16')} onChange={(e) => handleChange('defaultAspectRatio', e.target.value)} className="block w-full border rounded px-3 py-2">
                <option value="9:16">9:16 (Vertical)</option>
                <option value="16:9">16:9 (Horizontal)</option>
                <option value="1:1">1:1 (Square)</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Default Subtitle Style</label>
              <select value={ss(s, 'defaultSubtitleStyle', 'shadow')} onChange={(e) => handleChange('defaultSubtitleStyle', e.target.value)} className="block w-full border rounded px-3 py-2">
                <option value="shadow">Shadow — Classic + shadow</option>
                <option value="elegant">Elegant — Cinematic dual-font</option>
                <option value="boxies">Boxies — Colored box</option>
                <option value="karaoke">Karaoke — Sing-along highlight</option>
                <option value="mozi">Mozi — Word highlight sweep</option>
                <option value="pod_d">Pod D — Pastel pink + pop</option>
                <option value="rapid_fire">Rapid Fire — One word pop</option>
                <option value="rapid_pro">Rapid Pro — Neon glow</option>
                <option value="prince">Prince — Premium dual-font</option>
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-2">Default Clip Count</label>
              <input type="number" min="1" max="20" value={sn(s, 'defaultClipCount', 3)} onChange={(e) => handleChange('defaultClipCount', parseInt(e.target.value))} className="block w-full border rounded px-3 py-2" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Min Duration (seconds)</label>
              <input type="number" min="10" max="120" value={sn(s, 'minDuration', 30)} onChange={(e) => handleChange('minDuration', parseInt(e.target.value))} className="block w-full border rounded px-3 py-2" />
            </div>
          </div>
        </div>

        {/* Features */}
        <div className="border rounded p-4 space-y-2">
          <h3 className="font-medium mb-4">Features</h3>
          <label className="flex items-center gap-2"><input type="checkbox" checked={s.addSubtitlesByDefault !== false} onChange={(e) => handleChange('addSubtitlesByDefault', e.target.checked)} /><span className="text-sm">Add subtitles by default</span></label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={s.addHookByDefault !== false} onChange={(e) => handleChange('addHookByDefault', e.target.checked)} /><span className="text-sm">Add viral hook by default</span></label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={s.randomizeMetadata === true} onChange={(e) => handleChange('randomizeMetadata', e.target.checked)} /><span className="text-sm">Randomize metadata</span></label>
        </div>

        {/* Save */}
        <button type="submit" disabled={isLoading} className="w-full bg-blue-600 text-white py-2 px-4 rounded disabled:opacity-50">
          {isLoading ? 'Saving...' : 'Save Settings'}
        </button>
      </form>
    </div>
  );
}
