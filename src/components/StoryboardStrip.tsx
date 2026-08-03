import React from 'react';
import { Film, Clock, Volume2, Layers, AlertTriangle } from 'lucide-react';
import { AdShot, AttemptContent } from '../types';

/**
 * The shot breakdown of the assembled advertisement.
 *
 * This panel exists to answer one question a viewer will otherwise have to take
 * on trust: is this a real cut, or one still drifting for twenty seconds? So it
 * shows each shot's own generated first frame side by side, in order, with the
 * camera move and the line of narration that plays over it — the evidence that
 * the shots are genuinely different scenes.
 *
 * Failed shots are rendered as gaps rather than hidden. An ad cut from two of
 * three planned shots is still a usable ad, but the viewer should be able to
 * see that it happened.
 */

const ROLE_STYLE: Record<string, { label: string; chip: string }> = {
  hook: { label: 'Hook', chip: 'bg-amber-100 text-amber-900 border-amber-200' },
  product: { label: 'Product', chip: 'bg-emerald-100 text-emerald-900 border-emerald-200' },
  benefit: { label: 'Benefit', chip: 'bg-sky-100 text-sky-900 border-sky-200' },
  cta: { label: 'Close', chip: 'bg-violet-100 text-violet-900 border-violet-200' },
};

interface StoryboardStripProps {
  content: AttemptContent;
}

export const StoryboardStrip: React.FC<StoryboardStripProps> = ({ content }) => {
  const shots = content.adShots ?? [];
  if (shots.length === 0) return null;

  const rendered = shots.filter((s) => s.status === 'rendered');
  const failed = shots.filter((s) => s.status === 'failed');

  return (
    <section className="rounded-2xl border border-stone-200 bg-white p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Film className="h-4 w-4 text-violet-700" />
          <h3 className="font-serif text-lg font-bold text-stone-900">Storyboard</h3>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 font-mono text-[10px]">
          <span className="rounded-full border border-stone-200 bg-stone-50 px-2 py-1 text-stone-700">
            <Layers className="mr-1 inline h-3 w-3" />
            {rendered.length} shot{rendered.length === 1 ? '' : 's'}
          </span>
          {content.videoDurationSeconds != null && (
            <span className="rounded-full border border-stone-200 bg-stone-50 px-2 py-1 text-stone-700">
              <Clock className="mr-1 inline h-3 w-3" />
              {content.videoDurationSeconds}s
            </span>
          )}
          {content.hasVoiceover && (
            <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-1 text-emerald-800">
              <Volume2 className="mr-1 inline h-3 w-3" />
              voiceover
            </span>
          )}
          {content.hasEndCard && (
            <span className="rounded-full border border-violet-200 bg-violet-50 px-2 py-1 text-violet-800">
              end card
            </span>
          )}
        </div>
      </div>

      <p className="mt-1 text-xs text-stone-600">
        Each shot is a separately generated scene with its own first frame and camera move,
        cut together into one film — not a single image in motion.
      </p>

      {/* Horizontal strip: reads like a storyboard, scrolls on narrow screens
          rather than forcing the page to scroll sideways. */}
      <div className="mt-4 flex gap-3 overflow-x-auto pb-2">
        {shots.map((shot) => (
          <ShotCard key={shot.index} shot={shot} />
        ))}
      </div>

      {failed.length > 0 && (
        <div className="mt-2 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-700" />
          <p className="text-xs text-amber-900">
            {failed.length} planned shot{failed.length === 1 ? '' : 's'} did not render. The
            advertisement was cut from the {rendered.length} that did.
          </p>
        </div>
      )}
    </section>
  );
};

const ShotCard: React.FC<{ shot: AdShot }> = ({ shot }) => {
  const role = ROLE_STYLE[shot.role] ?? {
    label: shot.role,
    chip: 'bg-stone-100 text-stone-800 border-stone-200',
  };
  const failed = shot.status === 'failed';

  return (
    <figure
      className={`w-56 shrink-0 overflow-hidden rounded-xl border ${
        failed ? 'border-dashed border-stone-300 opacity-60' : 'border-stone-200'
      } bg-[#FAF9F5]`}
    >
      <div className="relative aspect-video bg-stone-200">
        {shot.frameUrl && !failed ? (
          <img
            src={shot.frameUrl}
            alt={`Shot ${shot.index + 1}: ${shot.title}`}
            className="h-full w-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center font-mono text-[10px] text-stone-500">
            {failed ? 'not rendered' : 'no frame'}
          </div>
        )}
        <span className="absolute left-1.5 top-1.5 rounded bg-black/70 px-1.5 py-0.5 font-mono text-[9px] font-bold text-white">
          {shot.index + 1}
        </span>
        <span className="absolute bottom-1.5 right-1.5 rounded bg-black/70 px-1.5 py-0.5 font-mono text-[9px] text-white">
          {shot.durationSeconds}s
        </span>
      </div>

      <figcaption className="space-y-1.5 p-2.5">
        <div className="flex items-center gap-1.5">
          <span
            className={`rounded-full border px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase ${role.chip}`}
          >
            {role.label}
          </span>
        </div>

        <div className="text-xs font-bold leading-snug text-stone-900">{shot.title}</div>

        <p className="line-clamp-3 text-[10px] leading-snug text-stone-600">{shot.scenePrompt}</p>

        <p className="border-t border-stone-200 pt-1.5 font-mono text-[9px] leading-snug text-stone-500">
          <span className="text-stone-400">camera: </span>
          {shot.motionPrompt}
        </p>

        {shot.voiceoverLine && (
          <p className="text-[10px] italic leading-snug text-stone-700">"{shot.voiceoverLine}"</p>
        )}
      </figcaption>
    </figure>
  );
};
