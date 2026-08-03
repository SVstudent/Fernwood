import React from 'react';
import { Archive, Compass, Eye, Users, Sparkles, Lock } from 'lucide-react';
import { BrainSnapshot, LobeId, LobeStatus } from '../types';

/**
 * The live lobe graph — the Campaign Brain made visible.
 *
 * Rendered in two places with the same component: inline in PipelineRunView,
 * where lobes light up as they fire during a run, and at the top of BrainView
 * as the finished record. Sharing it means the shape a judge watches animate is
 * the same shape they inspect afterwards.
 *
 * Drawn as one SVG rather than positioned divs so the connective paths, the
 * signal pulses travelling along them and the nodes all live in a single
 * coordinate space that scales cleanly with viewBox — no measuring, no resize
 * listeners, no drift between the edges and the things they connect.
 */

interface LobeSpec {
  id: LobeId;
  label: string;
  sub: string;
  /** Position in the 0-1000 x 0-420 viewBox. */
  x: number;
  y: number;
  Icon: React.ComponentType<{ className?: string }>;
}

const LOBES: LobeSpec[] = [
  { id: 'recall', label: 'Recall', sub: 'reads B2', x: 110, y: 210, Icon: Archive },
  { id: 'strategy', label: 'Strategy', sub: 'one big idea', x: 330, y: 108, Icon: Compass },
  { id: 'foresight', label: 'Foresight', sub: 'predicts score', x: 330, y: 312, Icon: Eye },
  { id: 'audience', label: 'Audience', sub: 'simulates panel', x: 610, y: 210, Icon: Users },
  { id: 'learning', label: 'Learning', sub: 'writes laws', x: 880, y: 210, Icon: Sparkles },
];

/** Signal paths. The Learning -> Recall edge is the loop that makes it a brain. */
const EDGES: Array<{ from: LobeId; to: LobeId; feedback?: boolean }> = [
  { from: 'recall', to: 'strategy' },
  { from: 'recall', to: 'foresight' },
  { from: 'strategy', to: 'foresight' },
  { from: 'strategy', to: 'audience' },
  { from: 'foresight', to: 'audience' },
  { from: 'audience', to: 'learning' },
  { from: 'learning', to: 'recall', feedback: true },
];

const NODE_R = 44;

const STATUS_STYLE: Record<LobeStatus, { ring: string; fill: string; text: string; glow: number }> = {
  idle: { ring: '#3f4a44', fill: '#141a17', text: '#6b7a72', glow: 0 },
  firing: { ring: '#fbbf24', fill: '#3b2f0b', text: '#fcd34d', glow: 1 },
  done: { ring: '#34d399', fill: '#0d2b21', text: '#6ee7b7', glow: 0.35 },
  skipped: { ring: '#57534e', fill: '#1c1917', text: '#78716c', glow: 0 },
};

function lobeById(id: LobeId): LobeSpec {
  return LOBES.find((l) => l.id === id)!;
}

/**
 * Edge geometry, stopping at the node rim rather than the node centre so the
 * pulse emerges from the edge of a lobe instead of from under it.
 */
function edgePath(from: LobeSpec, to: LobeSpec, feedback = false): string {
  if (feedback) {
    // Routed under the whole graph — a straight line back would pass through
    // three unrelated nodes and read as a mistake rather than a feedback loop.
    return `M ${to.x} ${to.y + NODE_R} C ${to.x} ${to.y + 170}, ${from.x} ${from.y + 170}, ${from.x} ${from.y + NODE_R}`;
  }
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const len = Math.hypot(dx, dy) || 1;
  const ux = dx / len;
  const uy = dy / len;
  const x1 = from.x + ux * NODE_R;
  const y1 = from.y + uy * NODE_R;
  const x2 = to.x - ux * NODE_R;
  const y2 = to.y - uy * NODE_R;
  // Gentle arc so parallel edges between the same columns stay distinguishable.
  const mx = (x1 + x2) / 2 - uy * 26;
  const my = (y1 + y2) / 2 + ux * 26;
  return `M ${x1} ${y1} Q ${mx} ${my}, ${x2} ${y2}`;
}

interface BrainCortexProps {
  snapshot?: BrainSnapshot | null;
  /** Compact variant for the pipeline sidebar. */
  compact?: boolean;
}

export const BrainCortex: React.FC<BrainCortexProps> = ({ snapshot, compact = false }) => {
  const statuses = (snapshot?.lobes ?? {}) as Record<string, LobeStatus>;
  const statusOf = (id: LobeId): LobeStatus => statuses[id] ?? 'idle';

  const anyFiring = LOBES.some((l) => statusOf(l.id) === 'firing');
  const doneCount = LOBES.filter((l) => statusOf(l.id) === 'done').length;

  return (
    <div
      className={`relative overflow-hidden rounded-2xl border border-emerald-900/40 bg-[#0B0F0D] ${
        compact ? 'p-3' : 'p-5'
      }`}
    >
      {/* Local keyframes: the cortex is the only thing in the app that animates
          this way, so it carries its own styles rather than growing the global
          stylesheet with single-use rules. */}
      <style>{`
        @keyframes fw-pulse-ring {
          0%   { r: ${NODE_R}px; opacity: 0.55; }
          100% { r: ${NODE_R + 26}px; opacity: 0; }
        }
        @keyframes fw-signal {
          0%   { offset-distance: 0%;   opacity: 0; }
          12%  { opacity: 1; }
          88%  { opacity: 1; }
          100% { offset-distance: 100%; opacity: 0; }
        }
        @keyframes fw-drift {
          0%, 100% { transform: translateY(0px); }
          50%      { transform: translateY(-4px); }
        }
        .fw-node-firing { animation: fw-drift 2.4s ease-in-out infinite; }
        .fw-signal {
          animation: fw-signal 2.1s linear infinite;
          offset-rotate: 0deg;
        }
        @media (prefers-reduced-motion: reduce) {
          .fw-node-firing, .fw-signal { animation: none; }
          .fw-signal { opacity: 0.9; }
        }
      `}</style>

      {/* Ambient wash — keeps the panel from reading as a flat black rectangle */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-70"
        style={{
          background:
            'radial-gradient(680px 300px at 22% 46%, rgba(16,185,129,0.13), transparent 62%), radial-gradient(520px 280px at 82% 54%, rgba(217,119,6,0.11), transparent 60%)',
        }}
      />

      <div className="relative flex items-center justify-between px-1 pb-1">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            {anyFiring && (
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75" />
            )}
            <span
              className={`relative inline-flex h-2 w-2 rounded-full ${
                anyFiring ? 'bg-amber-400' : doneCount > 0 ? 'bg-emerald-400' : 'bg-stone-600'
              }`}
            />
          </span>
          <h3 className="font-serif text-sm font-bold tracking-tight text-stone-100">
            Campaign Brain
          </h3>
          {snapshot?.brandName && (
            <span className="rounded-full border border-emerald-800/60 bg-emerald-950/60 px-2 py-0.5 font-mono text-[10px] text-emerald-300">
              {snapshot.brandName}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2 font-mono text-[10px] text-stone-500">
          {snapshot && (
            <span className="rounded border border-stone-700/70 px-1.5 py-0.5 text-stone-400">
              v{snapshot.brainVersionAfter || snapshot.brainVersionBefore}
            </span>
          )}
          {snapshot?.coldStart && (
            <span className="rounded border border-amber-800/60 bg-amber-950/40 px-1.5 py-0.5 text-amber-400">
              COLD START
            </span>
          )}
          {snapshot?.modelUsed && !compact && (
            <span className="hidden sm:inline text-stone-600">{snapshot.modelUsed}</span>
          )}
        </div>
      </div>

      <svg
        viewBox="0 0 1000 420"
        className={`relative w-full ${compact ? 'h-40' : 'h-64'}`}
        role="img"
        aria-label="Campaign Brain lobe activity"
      >
        <defs>
          <filter id="fw-glow" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="7" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Edges first, so nodes always sit on top of the wiring */}
        {EDGES.map((edge) => {
          const from = lobeById(edge.from);
          const to = lobeById(edge.to);
          const d = edgePath(from, to, edge.feedback);
          // An edge is live when its source has produced something and its
          // target is currently consuming it — that is what makes the animation
          // read as flow rather than decoration.
          const fromDone = statusOf(edge.from) === 'done';
          const toActive = statusOf(edge.to) === 'firing';
          const live = fromDone && toActive;
          const traversed = fromDone && statusOf(edge.to) === 'done';

          return (
            <g key={`${edge.from}-${edge.to}`}>
              <path
                d={d}
                fill="none"
                stroke={live ? '#fbbf24' : traversed ? '#10b981' : '#293330'}
                strokeWidth={live ? 2.2 : traversed ? 1.6 : 1.2}
                strokeDasharray={edge.feedback ? '7 6' : undefined}
                opacity={live ? 0.95 : traversed ? 0.55 : 0.5}
              />
              {live && (
                <circle
                  className="fw-signal"
                  r="4.5"
                  fill="#fde68a"
                  filter="url(#fw-glow)"
                  style={{ offsetPath: `path("${d}")` } as React.CSSProperties}
                />
              )}
            </g>
          );
        })}

        {/* Nodes */}
        {LOBES.map((lobe) => {
          const status = statusOf(lobe.id);
          const style = STATUS_STYLE[status];
          const firing = status === 'firing';

          return (
            <g key={lobe.id} className={firing ? 'fw-node-firing' : undefined}>
              {firing && (
                <circle
                  cx={lobe.x}
                  cy={lobe.y}
                  fill="none"
                  stroke={style.ring}
                  strokeWidth="2"
                  style={{ animation: 'fw-pulse-ring 1.9s ease-out infinite' }}
                />
              )}
              <circle
                cx={lobe.x}
                cy={lobe.y}
                r={NODE_R}
                fill={style.fill}
                stroke={style.ring}
                strokeWidth={firing ? 2.6 : 1.6}
                filter={style.glow > 0.5 ? 'url(#fw-glow)' : undefined}
                opacity={status === 'skipped' ? 0.5 : 1}
              />
              {/* Icons are HTML, so they ride in a foreignObject rather than
                  being re-authored as SVG paths. */}
              <foreignObject
                x={lobe.x - 13}
                y={lobe.y - 22}
                width="26"
                height="26"
                style={{ overflow: 'visible' }}
              >
                <div
                  className="flex h-[26px] w-[26px] items-center justify-center"
                  // lucide icons paint with currentColor, which inside an SVG
                  // defaults to black and would make every icon invisible on
                  // this panel. Set it explicitly from the lobe's status.
                  style={{ color: style.text }}
                >
                  <lobe.Icon className="h-[18px] w-[18px]" />
                </div>
              </foreignObject>
              <text
                x={lobe.x}
                y={lobe.y + 12}
                textAnchor="middle"
                className="font-sans"
                fontSize="13"
                fontWeight="700"
                fill={style.text}
              >
                {lobe.label}
              </text>
              <text
                x={lobe.x}
                y={lobe.y + 27}
                textAnchor="middle"
                fontSize="9.5"
                fill="#6b7a72"
                className="font-mono"
              >
                {lobe.sub}
              </text>
            </g>
          );
        })}

        <text
          x="500"
          y="404"
          textAnchor="middle"
          fontSize="10"
          fill="#4b5a53"
          className="font-mono"
        >
          learning writes back to recall — every run leaves the brain different
        </text>
      </svg>

      {!compact && snapshot && (
        <div className="relative mt-1 grid grid-cols-2 gap-1.5 sm:grid-cols-5">
          {LOBES.map((lobe) => {
            const status = statusOf(lobe.id);
            // Keyed by lobe id. The runner records every manifest under the
            // lobe name it passes to _set(), including the audience reaction —
            // an earlier guess at 'audience_reaction' silently showed no hash.
            const manifest = snapshot.lobeManifests?.[lobe.id];
            return (
              <div
                key={lobe.id}
                className={`rounded-lg border px-2 py-1.5 ${
                  status === 'firing'
                    ? 'border-amber-700/60 bg-amber-950/30'
                    : status === 'done'
                      ? 'border-emerald-900/60 bg-emerald-950/30'
                      : 'border-stone-800 bg-stone-950/40'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[10px] uppercase tracking-wide text-stone-400">
                    {lobe.label}
                  </span>
                  <span
                    className={`font-mono text-[9px] ${
                      status === 'done'
                        ? 'text-emerald-400'
                        : status === 'firing'
                          ? 'text-amber-400'
                          : 'text-stone-600'
                    }`}
                  >
                    {status}
                  </span>
                </div>
                {manifest && (
                  <div
                    className="mt-0.5 flex items-center gap-1 font-mono text-[9px] text-stone-600"
                    title={`Genblaze manifest ${manifest}`}
                  >
                    <Lock className="h-2.5 w-2.5" />
                    {manifest.slice(0, 10)}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
