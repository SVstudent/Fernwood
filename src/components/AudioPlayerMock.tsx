import React, { useState, useEffect } from 'react';
import { Play, Pause, Volume2, VolumeX, RotateCcw, Mic, Sparkles } from 'lucide-react';

interface AudioPlayerMockProps {
  scriptText: string;
  voiceName?: string;
  durationSeconds?: number;
  waveformData?: number[];
  providerName?: string;
  modelName?: string;
}

export const AudioPlayerMock: React.FC<AudioPlayerMockProps> = ({
  scriptText,
  voiceName = 'Genblaze Warm Resonant Baritone',
  durationSeconds = 8.5,
  waveformData = [20, 35, 60, 85, 40, 70, 95, 30, 50, 75, 45, 80, 60, 35, 20],
  providerName = 'Genblaze Voice Synthesis',
  modelName = 'genblaze-tts-pro'
}) => {
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [isMuted, setIsMuted] = useState(false);

  useEffect(() => {
    let timer: any;
    if (isPlaying) {
      timer = setInterval(() => {
        setCurrentTime((prev) => {
          if (prev >= durationSeconds) {
            setIsPlaying(false);
            return 0;
          }
          return prev + 0.1;
        });
      }, 100);
    } else {
      clearInterval(timer);
    }
    return () => clearInterval(timer);
  }, [isPlaying, durationSeconds]);

  const togglePlay = () => {
    if (currentTime >= durationSeconds) {
      setCurrentTime(0);
    }
    setIsPlaying(!isPlaying);
  };

  const progressPercent = Math.min(100, (currentTime / durationSeconds) * 100);

  return (
    <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-xs transition-all hover:border-stone-300">
      {/* Header Info */}
      <div className="flex items-center justify-between pb-3 border-b border-stone-100">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-50 text-emerald-800 border border-emerald-200">
            <Mic className="h-4 w-4" />
          </div>
          <div>
            <h4 className="text-xs font-semibold text-stone-900 font-sans">
              Voiceover & Acoustic Tagline
            </h4>
            <p className="text-[11px] text-stone-500 font-mono">
              Voice: {voiceName}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-md bg-stone-100 px-2 py-0.5 text-[10px] text-stone-600 font-mono border border-stone-200">
            {modelName}
          </span>
        </div>
      </div>

      {/* Script Display */}
      <div className="my-4 rounded-lg bg-stone-50/80 p-3.5 border border-stone-200/60">
        <p className="text-xs text-stone-700 italic leading-relaxed">
          "{scriptText}"
        </p>
      </div>

      {/* Waveform Visualization */}
      <div className="mb-3 flex items-end gap-1.5 h-12 px-2 py-1 bg-stone-900 rounded-lg overflow-hidden">
        {waveformData.map((val, idx) => {
          const isActive = (idx / waveformData.length) * 100 <= progressPercent;
          return (
            <div
              key={idx}
              className={`flex-1 rounded-full transition-all duration-150 ${
                isActive
                  ? 'bg-emerald-400 opacity-100 shadow-xs'
                  : 'bg-stone-700 opacity-40 hover:opacity-60'
              }`}
              style={{
                height: isPlaying
                  ? `${Math.max(15, (val * (0.6 + Math.random() * 0.4)))}%`
                  : `${val}%`
              }}
            />
          );
        })}
      </div>

      {/* Playback Controls & Progress Slider */}
      <div className="flex items-center justify-between gap-3 pt-1">
        <div className="flex items-center gap-2">
          <button
            onClick={togglePlay}
            className="flex h-9 w-9 items-center justify-center rounded-full bg-[#1E3A2B] text-white hover:bg-[#152a1f] transition-transform active:scale-95 shadow-xs"
          >
            {isPlaying ? (
              <Pause className="h-4 w-4" />
            ) : (
              <Play className="h-4 w-4 ml-0.5" />
            )}
          </button>

          <button
            onClick={() => setCurrentTime(0)}
            className="flex h-8 w-8 items-center justify-center rounded-full text-stone-500 hover:bg-stone-100 transition-colors"
            title="Restart"
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Time Progress */}
        <div className="flex-1 mx-2">
          <div className="relative h-1.5 w-full bg-stone-200 rounded-full overflow-hidden">
            <div
              className="h-full bg-emerald-600 transition-all duration-100"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <div className="flex justify-between text-[10px] text-stone-600 font-mono mt-1">
            <span>{currentTime.toFixed(1)}s</span>
            <span>{durationSeconds.toFixed(1)}s</span>
          </div>
        </div>

        <button
          onClick={() => setIsMuted(!isMuted)}
          className="text-stone-500 hover:text-stone-800 transition-colors p-1"
        >
          {isMuted ? <VolumeX className="h-4 w-4 text-rose-500" /> : <Volume2 className="h-4 w-4" />}
        </button>
      </div>

      {/* Code Comment Placeholder for Handoff */}
      <div className="mt-3 pt-2 border-t border-dashed border-stone-200 text-[10px] text-stone-600 font-mono flex items-center gap-1.5">
        <Sparkles className="h-3 w-3 text-amber-500" />
        <span>backend-handoff: Replace mock waveform with HTML5 Audio element or Web Audio API stream</span>
      </div>
    </div>
  );
};
