import React from 'react';

interface HookPreviewProps {
  preset: string;
  topText: string;
  headline: string;
  subheading: string;
  preset2Text: string;
  headingColor: string;
  highlightColor: string;
  strokeColor: string;
  position: string;
  fullDuration: boolean;
}

function parsePreset2Content(text: string): { word: string; highlight: boolean; italic: boolean }[][] {
  const lines: { word: string; highlight: boolean; italic: boolean }[][] = [];
  let currentLine: { word: string; highlight: boolean; italic: boolean }[] = [];
  let wordCount = 0;

  // Split by spaces, track markdown markers
  const raw = text.replace(/\+\+/g, '');
  const tokens = raw.split(/\s+/);

  for (const token of tokens) {
    if (!token) continue;
    let highlight = false;
    let italic = false;
    let clean = token;

    if (clean.startsWith('**') && clean.endsWith('**')) {
      highlight = true;
      clean = clean.slice(2, -2);
    } else if (clean.startsWith('*') && clean.endsWith('*')) {
      italic = true;
      clean = clean.slice(1, -1);
    }

    currentLine.push({ word: clean, highlight, italic });
    wordCount++;

    if (wordCount >= 3) {
      lines.push(currentLine);
      currentLine = [];
      wordCount = 0;
    }
  }

  if (currentLine.length > 0) {
    lines.push(currentLine);
  }

  return lines;
}

export function HookPreview({
  preset,
  topText,
  headline,
  subheading,
  preset2Text,
  headingColor,
  highlightColor,
  strokeColor,
  position,
}: HookPreviewProps) {
  const top = topText || 'WATCH THIS';
  const head = headline || 'VIRAL MOMENT';
  const sub = subheading || 'You need to see this';
  const p2Text = preset2Text || 'This is **amazing** and will *blow* your **mind** today';

  const positionStyle: React.CSSProperties = position === 'bottom'
    ? { justifyContent: 'flex-end', paddingBottom: '12%' }
    : position === 'center'
    ? { justifyContent: 'center' }
    : { justifyContent: 'flex-start', paddingTop: '8%' };

  return (
    <div className="flex flex-col items-center">
      <p className="text-xs text-gray-500 mb-2">Preview</p>
      <div
        className="relative bg-gray-900 rounded-lg overflow-hidden shadow-lg border border-gray-700"
        style={{ width: 180, aspectRatio: '9/16' }}
      >
        {/* Fake video background */}
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="w-12 h-12 rounded-full bg-white/10 flex items-center justify-center">
            <div className="w-0 h-0 border-l-[10px] border-l-white/30 border-y-[6px] border-y-transparent ml-1" />
          </div>
        </div>

        {/* Hook overlay */}
        <div className="absolute inset-0 flex flex-col" style={positionStyle}>
          {preset === 'preset-1' && (
            <div className="relative mx-2">
              {/* Semi-transparent background */}
              <div className="rounded-lg p-2" style={{ backgroundColor: 'rgba(0,0,0,0.7)' }}>
                <p className="text-center text-[7px] text-white/80 mb-0.5" style={{ textShadow: `0.5px 0.5px 0 ${strokeColor}` }}>
                  {top.toUpperCase()}
                </p>
                <p
                  className="text-center font-bold text-[13px] leading-tight"
                  style={{ color: headingColor, textShadow: `1px 1px 0 ${strokeColor}` }}
                >
                  {head.toUpperCase()}
                </p>
                <p className="text-center text-[8px] text-white/90 mt-0.5">
                  {sub}
                </p>
              </div>
            </div>
          )}

          {preset === 'preset-2' && (
            <div className="mx-3 flex flex-col items-center gap-0.5" style={{ marginTop: '55%' }}>
              {parsePreset2Content(p2Text).map((line, li) => (
                <p key={li} className="text-center leading-tight" style={{ fontSize: li === 1 ? '10px' : '7px' }}>
                  {line.map((w, wi) => (
                    <span
                      key={wi}
                      style={{
                        color: w.highlight ? highlightColor : '#FFFFFF',
                        fontStyle: w.italic ? 'italic' : 'normal',
                        fontWeight: w.highlight ? 800 : 400,
                        textShadow: w.highlight ? `0 0 6px ${highlightColor}` : 'none',
                      }}
                    >
                      {w.word}{' '}
                    </span>
                  ))}
                </p>
              ))}
            </div>
          )}

          {preset === 'preset-3' && (
            <div className="mx-3 flex flex-col items-center gap-1" style={{ marginTop: '50%' }}>
              <p className="text-[11px] font-black tracking-wider" style={{ color: headingColor }}>
                {head.split(' ')[0]?.toUpperCase() || 'VIRAL'}
              </p>
              <p className="text-[10px] font-bold text-white tracking-wide">
                {head.split(' ').slice(1).join(' ').toUpperCase() || 'MOMENT'}
              </p>
              <span
                className="px-2 py-0.5 text-[6px] font-bold text-white rounded-sm"
                style={{ backgroundColor: headingColor }}
              >
                {sub.toUpperCase()}
              </span>
            </div>
          )}

          {preset === 'preset-4' && (
            <div className="mx-3 flex flex-col items-center" style={{ marginTop: '50%' }}>
              <div
                className="rounded-lg p-2 w-full text-center"
                style={{ backgroundColor: headingColor + 'E6', boxShadow: `2px 2px 0 rgba(0,0,0,0.3)` }}
              >
                {top && (
                  <p className="text-[6px] text-white/80 mb-0.5">{top.toUpperCase()}</p>
                )}
                <p className="text-[10px] font-bold text-white leading-tight">
                  {head.toUpperCase()}
                </p>
                {sub && (
                  <p className="text-[6px] text-white/90 mt-0.5">{sub}</p>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
      <p className="text-[10px] text-gray-400 mt-1">9:16 preview</p>
    </div>
  );
}
