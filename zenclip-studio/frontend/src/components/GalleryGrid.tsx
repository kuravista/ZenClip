import React, { useState } from 'react';

interface Video {
  path: string;
  filename: string;
  thumbnail?: string;
  duration?: number;
  size?: number;
  created?: number;
}

interface GalleryGridProps {
  videos: Video[];
  onPlay: (video: Video) => void;
  onDelete: (videos: string[]) => void;
  onRefresh: () => void;
  isLoading: boolean;
}

export function GalleryGrid({ videos, onPlay, onDelete, onRefresh, isLoading }: GalleryGridProps) {
  const [selectedVideos, setSelectedVideos] = useState<Set<string>>(new Set());
  const [playingVideo, setPlayingVideo] = useState<Video | null>(null);

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

  const handleDeleteSelected = () => {
    if (selectedVideos.size > 0) {
      onDelete(Array.from(selectedVideos));
      setSelectedVideos(new Set());
    }
  };

  const formatDuration = (seconds?: number): string => {
    if (!seconds) return '--:--';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const formatSize = (bytes?: number): string => {
    if (!bytes) return '--';
    const mb = bytes / (1024 * 1024);
    return `${mb.toFixed(1)} MB`;
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-semibold">Gallery</h2>
        <div className="flex gap-2">
          <button
            onClick={onRefresh}
            className="px-3 py-1 border rounded text-sm"
            disabled={isLoading}
          >
            {isLoading ? 'Loading...' : 'Refresh'}
          </button>
          <button
            onClick={handleSelectAll}
            className="px-3 py-1 border rounded text-sm"
          >
            {selectedVideos.size === videos.length ? 'Deselect All' : 'Select All'}
          </button>
          {selectedVideos.size > 0 && (
            <button
              onClick={handleDeleteSelected}
              className="px-3 py-1 bg-red-600 text-white rounded text-sm"
            >
              Delete ({selectedVideos.size})
            </button>
          )}
        </div>
      </div>

      {/* Video Grid */}
      {videos.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          No videos in gallery
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {videos.map((video) => (
            <div
              key={video.path}
              className={`border rounded overflow-hidden cursor-pointer transition-shadow hover:shadow-lg ${
                selectedVideos.has(video.path) ? 'ring-2 ring-blue-500' : ''
              }`}
            >
              {/* Thumbnail */}
              <div
                className="aspect-video bg-gray-200 relative"
                onClick={() => setPlayingVideo(video)}
              >
                {video.thumbnail ? (
                  <img
                    src={video.thumbnail}
                    alt={video.filename}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-gray-400">
                    No Preview
                  </div>
                )}

                {/* Duration Badge */}
                <div className="absolute bottom-2 right-2 bg-black/70 text-white text-xs px-1 rounded">
                  {formatDuration(video.duration)}
                </div>

                {/* Checkbox */}
                <div
                  className="absolute top-2 left-2"
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleSelect(video.path);
                  }}
                >
                  <input
                    type="checkbox"
                    checked={selectedVideos.has(video.path)}
                    onChange={() => toggleSelect(video.path)}
                    className="w-4 h-4"
                  />
                </div>
              </div>

              {/* Info */}
              <div className="p-2">
                <p className="text-sm truncate" title={video.filename}>
                  {video.filename}
                </p>
                <p className="text-xs text-gray-500">
                  {formatSize(video.size)}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Video Player Modal */}
      {playingVideo && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg max-w-3xl w-full max-h-[90vh] overflow-hidden">
            <div className="p-4 border-b flex justify-between items-center">
              <h3 className="font-medium">{playingVideo.filename}</h3>
              <button
                onClick={() => setPlayingVideo(null)}
                className="text-gray-500 hover:text-gray-700"
              >
                ✕
              </button>
            </div>
            <div className="p-4">
              <video
                src={`/api/video/${encodeURIComponent(playingVideo.path)}`}
                controls
                className="w-full max-h-[60vh]"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
