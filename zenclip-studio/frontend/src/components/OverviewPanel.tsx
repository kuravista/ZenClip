import React from 'react';

import { JobStatusPanel } from './JobStatusPanel';

interface OverviewPanelProps {
  onRefresh: () => void;
  onSettingsChange: () => void;
}

export function OverviewPanel({ onRefresh, onSettingsChange: _onSettingsChange }: OverviewPanelProps) {
  const [health, setHealth] = React.useState<string>('unknown');
  const [jobIdInput, setJobIdInput] = React.useState('');

  const loadOverview = React.useCallback(async () => {
    try {
      const res = await fetch('/health');
      if (res.ok) {
        const data = (await res.json()) as { status?: string };
        setHealth(data.status ?? 'ok');
      } else {
        setHealth(`error ${res.status}`);
      }
    } catch {
      setHealth('unreachable');
    }
  }, []);

  React.useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  return (
    <div className="space-y-6 p-4">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-lg font-semibold">Overview</h2>
        <button
          type="button"
          onClick={() => {
            void loadOverview();
            onRefresh();
          }}
          className="rounded bg-gray-200 px-3 py-1 text-sm"
        >
          Refresh
        </button>
      </div>

      <div className="rounded border p-3 text-sm">
        <span className="font-medium">API health</span>: {health}
      </div>

      <div className="space-y-2">
        <h3 className="text-md font-medium">Job progress</h3>
        <p className="text-xs text-gray-600">
          Paste a <code className="rounded bg-gray-100 px-1">job_id</code> from the process response to poll{' '}
          <code className="rounded bg-gray-100 px-1">GET /status/&lt;id&gt;</code>.
        </p>
        <input
          type="text"
          value={jobIdInput}
          onChange={(e) => setJobIdInput(e.target.value.trim())}
          placeholder="job UUID"
          className="block w-full max-w-md rounded border px-3 py-2 text-sm"
        />
        {jobIdInput ? <JobStatusPanel jobId={jobIdInput} pollMs={2000} /> : null}
      </div>
    </div>
  );
}
