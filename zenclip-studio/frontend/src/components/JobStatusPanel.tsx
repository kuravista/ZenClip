import React from 'react';

export interface JobStatusPayload {
  job_id: string;
  status: string;
  progress?: string | number;
  message?: string;
  percentage?: number;
  error?: string;
}

interface JobStatusPanelProps {
  jobId: string;
  pollMs?: number;
  statusPath?: (id: string) => string;
}

export function JobStatusPanel({
  jobId,
  pollMs = 2000,
  statusPath = (id) => `/status/${id}`,
}: JobStatusPanelProps) {
  const [state, setState] = React.useState<JobStatusPayload | null>(null);
  const [err, setErr] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!jobId) {
      return;
    }
    let cancelled = false;

    const tick = async () => {
      try {
        const res = await fetch(statusPath(jobId));
        if (!res.ok) {
          if (!cancelled) {
            setErr(`HTTP ${res.status}`);
          }
          return;
        }
        const body = (await res.json()) as JobStatusPayload;
        if (!cancelled) {
          setState(body);
          setErr(null);
        }
      } catch (e) {
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : String(e));
        }
      }
    };

    void tick();
    const id = window.setInterval(() => void tick(), pollMs);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [jobId, pollMs, statusPath]);

  if (!jobId) {
    return null;
  }

  if (err && !state) {
    return <p className="text-sm text-red-600">Job status: {err}</p>;
  }

  if (!state) {
    return <p className="text-sm text-gray-600">Loading job status…</p>;
  }

  const msg = state.message ?? (typeof state.progress === 'string' ? state.progress : '');

  return (
    <div className="rounded border border-gray-200 p-3 space-y-1 text-sm bg-gray-50">
      <div>
        <span className="font-medium">Job</span> {state.job_id}
      </div>
      <div>
        <span className="font-medium">Status</span> {state.status}
      </div>
      {typeof state.percentage === 'number' ? (
        <div>
          <span className="font-medium">Progress</span> {state.percentage}%
          <div className="mt-1 h-2 w-full rounded bg-gray-200 overflow-hidden">
            <div
              className="h-full bg-blue-600 transition-all"
              style={{ width: `${Math.min(100, Math.max(0, state.percentage))}%` }}
            />
          </div>
        </div>
      ) : null}
      {msg ? (
        <div>
          <span className="font-medium">Message</span> {msg}
        </div>
      ) : null}
      {state.error ? (
        <div className="text-red-600">
          <span className="font-medium">Error</span> {state.error}
        </div>
      ) : null}
    </div>
  );
}
