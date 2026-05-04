import React, { useState } from 'react';

interface Phrase {
  text: string;
  start: number;
  end: number;
  words?: { text: string; start: number; end: number }[];
}

interface TranscriptEditorProps {
  phrases: Phrase[];
  jobId: string | null;
  onSave: (phrases: Phrase[]) => void;
  onProcess: () => void;
}

const API_URL = 'http://127.0.0.1:9478';

export function TranscriptEditor({ phrases: initialPhrases, jobId, onSave, onProcess }: TranscriptEditorProps) {
  const [phrases, setPhrases] = useState<Phrase[]>(initialPhrases);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitStatus, setSubmitStatus] = useState('');

  // Sync phrases when parent updates them
  React.useEffect(() => {
    setPhrases(initialPhrases);
  }, [initialPhrases]);

  const handleTextChange = (index: number, text: string) => {
    const updated = [...phrases];
    updated[index] = { ...updated[index], text };
    setPhrases(updated);
  };

  const handleTimeChange = (index: number, field: 'start' | 'end', value: number) => {
    const updated = [...phrases];
    updated[index] = { ...updated[index], [field]: value };
    setPhrases(updated);
  };

  const handleDelete = (index: number) => {
    const updated = phrases.filter((_, i) => i !== index);
    setPhrases(updated);
    setSelectedIndex(null);
  };

  const handleAdd = () => {
    const lastPhrase = phrases[phrases.length - 1];
    const newPhrase: Phrase = {
      text: '',
      start: lastPhrase ? lastPhrase.end : 0,
      end: lastPhrase ? lastPhrase.end + 5 : 5,
    };
    setPhrases([...phrases, newPhrase]);
  };

  const handleContinueProcess = async () => {
    if (!jobId || isSubmitting) return;
    setIsSubmitting(true);
    setSubmitStatus('Submitting edited transcript...');

    try {
      const res = await fetch(`${API_URL}/process_with_transcript`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          job_id: jobId,
          phrase_timings: phrases,
          clips_data: [],
        }),
      });

      if (res.ok) {
        setSubmitStatus('Processing resumed! Switching to progress view...');
        setTimeout(() => onProcess(), 1000);
      } else {
        const err = await res.text();
        setSubmitStatus(`Error: ${err}`);
      }
    } catch (e) {
      setSubmitStatus(`Error: ${e instanceof Error ? e.message : 'Unknown'}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    const ms = Math.floor((seconds % 1) * 100);
    return `${mins}:${secs.toString().padStart(2, '0')}.${ms.toString().padStart(2, '0')}`;
  };

  if (phrases.length === 0) {
    return (
      <div className="text-center py-16 space-y-4">
        <div className="text-gray-400 text-4xl">{"</>"}</div>
        <h2 className="text-lg font-semibold text-gray-700">No Transcript</h2>
        <p className="text-sm text-gray-500 max-w-md mx-auto">
          Enable <strong>"Review transcript before cutting"</strong> in the Process tab
          to edit the AI-generated transcript before video cutting.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-lg font-semibold">Transcript Editor</h2>
          {jobId && <p className="text-xs text-gray-400 font-mono">Job: {jobId}</p>}
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleAdd}
            className="px-3 py-1 bg-green-600 text-white rounded text-sm"
          >
            Add Phrase
          </button>
          <button
            onClick={() => onSave(phrases)}
            className="px-3 py-1 bg-blue-600 text-white rounded text-sm"
          >
            Save Changes
          </button>
          {jobId && (
            <button
              onClick={handleContinueProcess}
              disabled={isSubmitting}
              className="px-4 py-1 bg-purple-600 text-white rounded text-sm disabled:opacity-50"
            >
              {isSubmitting ? 'Submitting...' : 'Continue Processing'}
            </button>
          )}
        </div>
      </div>

      {/* Status */}
      {submitStatus && (
        <div className={`p-2 rounded text-sm ${
          submitStatus.startsWith('Error') ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'
        }`}>
          {submitStatus}
        </div>
      )}

      {/* Search */}
      <input
        type="text"
        placeholder="Search phrases..."
        className="block w-full border rounded px-3 py-2 text-sm"
        onChange={(e) => {
          // Simple filter - not implemented yet, placeholder
        }}
      />

      {/* Phrase List */}
      <div className="max-h-[500px] overflow-y-auto space-y-1">
        {phrases.map((phrase, index) => (
          <div
            key={index}
            className={`p-3 border rounded cursor-pointer transition-colors ${
              selectedIndex === index ? 'border-blue-500 bg-blue-50' : 'hover:bg-gray-50'
            }`}
            onClick={() => setSelectedIndex(index)}
          >
            {/* Time Range */}
            <div className="flex gap-2 text-xs text-gray-500 mb-1">
              <span className="font-mono">{formatTime(phrase.start)}</span>
              <span>-</span>
              <span className="font-mono">{formatTime(phrase.end)}</span>
              <span className="ml-auto text-gray-400">
                {(phrase.end - phrase.start).toFixed(1)}s
              </span>
            </div>

            {/* Text */}
            {isEditing && selectedIndex === index ? (
              <textarea
                value={phrase.text}
                onChange={(e) => handleTextChange(index, e.target.value)}
                className="w-full border rounded px-2 py-1 text-sm"
                rows={2}
                autoFocus
              />
            ) : (
              <p className="text-sm">{phrase.text || '(empty)'}</p>
            )}

            {/* Actions */}
            {selectedIndex === index && (
              <div className="flex gap-2 mt-2">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setIsEditing(!isEditing);
                  }}
                  className="px-2 py-1 text-xs border rounded"
                >
                  {isEditing ? 'Done' : 'Edit'}
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(index);
                  }}
                  className="px-2 py-1 text-xs border rounded text-red-600"
                >
                  Delete
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Stats */}
      <div className="text-sm text-gray-500 border-t pt-3">
        {phrases.length} phrases &bull;{' '}
        {phrases.reduce((acc, p) => acc + (p.end - p.start), 0).toFixed(1)}s total
      </div>
    </div>
  );
}
