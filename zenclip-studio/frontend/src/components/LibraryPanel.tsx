import React, { useState, useCallback } from 'react';

interface Video {
  path: string;
  filename: string;
  size?: number;
  created?: number;
  duration?: number;
}

interface LibraryPanelProps {
  onUpload: (file: File) => Promise<void>;
  onSelect: (video: Video) => void;
  onDelete: (paths: string[]) => Promise<void>;
}

export function LibraryPanel({ onUpload, onSelect, onDelete }: LibraryPanelProps) {
  const [videos, setVideos] = useState<Video[]>([]);
  const [selectedVideos, setSelectedVideos] = useState<Set<string>>(new Set());
  const [isUploading, setIsUploading] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    try {
      await onUpload(file);
      // Refresh video list after upload
      loadVideos();
    } catch (error) {
      console.error('Upload failed:', error);
    } finally {
      setIsUploading(false);
      e.target.value = '';
    }
  };

  const loadVideos = useCallback(async () => {
    try {
      const res = await fetch('/api/videos');
      const data = await res.json();
      // Flatten clips, uploads, downloads
      const allVideos: Video[] = [
        ...(data.clips || []),
        ...(data.uploads || []),
        ...(data.downloads || []),
      ];
      setVideos(allVideos);
    } catch (error) {
      console.error('Failed to load videos:', error);
    }
  }, []);

  const toggleSelect = (path: string) => {
    const updated = new Set(selectedVideos);
    if (updated.has(path)) {
      updated.delete(path);
    } else {
      updated.add(path);
    }
    setSelectedVideos(updated);
  };

  const handleSelectAll = () => {
    if (selectedVideos.size === videos.length) {
      setSelectedVideos(new Set());
    } else {
      setSelectedVideos(new Set(videos.map(v => v.path)));
    }
  };

  const handleDeleteSelected = async () => {
    if (selectedVideos.size === 0) return;

    setIsDeleting(true);
    try {
      await onDelete(Array.from(selectedVideos));
      setSelectedVideos(new Set());
      loadVideos();
    } catch (error) {
      console.error('Delete failed:', error);
    } finally {
      setIsDeleting(false);
    }
  };

  const formatSize = (bytes?: number): string => {
    if (!bytes) return '--';
    const mb = bytes / (1024 * 1024);
    return `${mb.toFixed(1)} MB`;
  };

  const formatDate = (timestamp?: number): string => {
    if (!timestamp) return '--';
    const value = timestamp > 10_000_000_000 ? timestamp : timestamp * 1000;
    return new Date(value).toLocaleDateString();
  };

  const filteredVideos = videos.filter(v =>
    v.filename.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-semibold">Library</h2>
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Search videos..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="border rounded px-3 py-1 text-sm"
          />
          <button
            onClick={loadVideos}
            className="px-3 py-1 border rounded text-sm"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Upload Section */}
      <div className="border-2 border-dashed rounded p-4 text-center">
        <input
          type="file"
          accept="video/*"
          onChange={handleFileChange}
          className="hidden"
          id="library-upload"
        />
        <label
          htmlFor="library-upload"
          className="cursor-pointer text-blue-600 hover:text-blue-800"
        >
          {isUploading ? 'Uploading...' : '+ Upload Video'}
        </label>
        <p className="text-xs text-gray-500 mt-1">
          Drop video files here or click to browse
        </p>
      </div>

      {/* Selection Actions */}
      {selectedVideos.size > 0 && (
        <div className="flex gap-2 items-center">
          <span className="text-sm text-gray-600">
            {selectedVideos.size} selected
          </span>
          <button
            onClick={handleSelectAll}
            className="px-3 py-1 border rounded text-sm"
          >
            {selectedVideos.size === videos.length ? 'Deselect All' : 'Select All'}
          </button>
          <button
            onClick={handleDeleteSelected}
            disabled={isDeleting}
            className="px-3 py-1 bg-red-600 text-white rounded text-sm disabled:opacity-50"
          >
            {isDeleting ? 'Deleting...' : 'Delete Selected'}
          </button>
        </div>
      )}

      {/* Video List */}
      {filteredVideos.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          {searchQuery ? 'No videos match your search' : 'No videos in library'}
        </div>
      ) : (
        <div className="space-y-2">
          {filteredVideos.map((video) => (
            <div
              key={video.path}
              className={`flex items-center gap-4 p-3 border rounded hover:bg-gray-50 cursor-pointer ${
                selectedVideos.has(video.path) ? 'ring-2 ring-blue-500' : ''
              }`}
              onClick={() => onSelect(video)}
            >
              {/* Checkbox */}
              <input
                type="checkbox"
                checked={selectedVideos.has(video.path)}
                onChange={() => toggleSelect(video.path)}
                onClick={(e) => e.stopPropagation()}
                className="w-4 h-4"
              />

              {/* Video Info */}
              <div className="flex-1 min-w-0">
                <p className="font-medium truncate" title={video.filename}>
                  {video.filename}
                </p>
                <p className="text-sm text-gray-500">
                  {formatSize(video.size)} • {formatDate(video.created)}
                </p>
              </div>

              {/* Actions */}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onSelect(video);
                }}
                className="px-3 py-1 bg-blue-600 text-white rounded text-sm"
              >
                Use
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Stats */}
      <div className="text-sm text-gray-500">
        {filteredVideos.length} videos • {formatSize(videos.reduce((acc, v) => acc + (v.size || 0), 0))} total
      </div>
    </div>
  );
}
