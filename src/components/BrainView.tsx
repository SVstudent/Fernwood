import React, { useEffect, useState } from 'react';
import {
  TrendingUp,
  TrendingDown,
  Minus,
  Quote,
  ShieldAlert,
  Target,
  Gauge,
  Users,
  BookLock,
  RotateCcw,
  AlertTriangle,
  Clock,
} from 'lucide-react';
import {
  BrainSnapshot,
  BrainState,
  BrandLaw,
  Campaign,
  ImprovementDelta,
  PersonaReaction,
  RunRecord,
} from '../types';
import { BrainCortex } from './BrainCortex';
import { fetchBrainByBrand, resetBrain } from '../services/pipelineService';

/**
 * The Campaign Brain page.
 *
 * Reads from two sources and keeps them distinct on purpose:
 *   - campaign.brain — the SNAPSHOT of what the brain did on this specific run
 *   - GET /api/brain — the LIVE persistent brain for the brand, including every
 *     law and the full run history
 *
 * The improvement panel is deliberately the first thing on the page, because it
 * is the only claim here that is falsifiable: everything else describes what the
 * brain did, and that panel measures whether it worked.
 */

interface BrainViewProps {
  campaign: Campaign | null;
  onBackToLibrary: () => void;
}

const CATEGORY_STYLE: Record<string, string> = {
  visual: 'bg-violet-100 text-violet-800 border-violet-200',
  voice: 'bg-sky-100 text-sky-800 border-sky-200',
  copy: 'bg-amber-100 text-amber-800 border-amber-200',
  audience: 'bg-rose-100 text-rose-800 border-rose-200',
  strategy: 'bg-emerald-100 text-emerald-800 border-emerald-200',
};

const VERDICT_STYLE: Record<string, { chip: string; ring: string }> = {
  loves: { chip: 'bg-emerald-100 text-emerald-800 border-emerald-200', ring: '#059669' },
  likes: { chip: 'bg-lime-100 text-lime-800 border-lime-200', ring: '#65a30d' },
  indifferent: { chip: 'bg-stone-100 text-stone-700 border-stone-200', ring: '#a8a29e' },
  dislikes: { chip: 'bg-rose-100 text-rose-800 border-rose-200', ring: '#e11d48' },
};

export const BrainView: React.FC<BrainViewProps> = ({ campaign, onBackToLibrary }) => {
  const snapshot: BrainSnapshot | undefined = campaign?.brain;
  const [brain, setBrain] = useState<BrainState | null>(null);
  const [improvement, setImprovement] = useState<ImprovementDelta | null>(
    snapshot?.improvement ?? null
  );
  const [loading, setLoading] = useState(false);
  const [resetting, setResetting] = useState(false);

  const brandName = campaign?.brandName ?? snapshot?.brandName ?? '';

  // The persistent brain is authoritative for laws and history — the run
  // snapshot only knows what was true when that run started.
  const load = React.useCallback(() => {
    if (!brandName) return;
    setLoading(true);
    fetchBrainByBrand(brandName)
      .then((res) => {
        if (!res) return;
        setBrain(res.brain);
        setImprovement(res.improvement);
      })
      .finally(() => setLoading(false));
  }, [brandName]);

  useEffect(load, [load]);

  const handleReset = async () => {
    if (!brain?.brandSlug) return;
    setResetting(true);
    await resetBrain(brain.brandSlug);
    setResetting(false);
    load();
  };

  if (!campaign && !brain) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-20 text-center sm:px-6">
        <h2 className="font-serif text-2xl font-bold text-stone-900">No brain to show yet</h2>
        <p className="mt-2 text-sm text-stone-600">
          Run a campaign and its brand's Campaign Brain will appear here.
        </p>
        <button
          onClick={onBackToLibrary}
          className="mt-6 rounded-lg bg-[#1E3A2B] px-4 py-2 text-sm font-semibold text-white"
        >
          Back to Library
        </button>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <header className="mb-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-widest text-stone-500">
              Persistent brand intelligence
            </p>
            <h1 className="mt-1 font-serif text-3xl font-bold tracking-tight text-stone-900">
              {brandName || 'Campaign'} Brain
            </h1>
            <p className="mt-1 max-w-2xl text-sm text-stone-600">
              Every rejected attempt this studio ever produced is stored with the critique
              that rejected it. The brain reads that archive back, turns it into rules with
              citations, and aims the next campaign with them.
            </p>
          </div>

          <div className="flex items-center gap-2">
            {brain && (
              <div className="rounded-xl border border-stone-200 bg-white px-3 py-2 text-center">
                <div className="font-mono text-lg font-bold text-stone-900">v{brain.version}</div>
                <div className="font-mono text-[10px] uppercase text-stone-500">brain</div>
              </div>
            )}
            {brain && (
              <div className="rounded-xl border border-stone-200 bg-white px-3 py-2 text-center">
                <div className="font-mono text-lg font-bold text-stone-900">
                  {brain.lifetimeCampaigns}
                </div>
                <div className="font-mono text-[10px] uppercase text-stone-500">campaigns</div>
              </div>
            )}
            {brain && (
              <div className="rounded-xl border border-stone-200 bg-white px-3 py-2 text-center">
                <div className="font-mono text-lg font-bold text-stone-900">
                  {brain.laws.length}
                </div>
                <div className="font-mono text-[10px] uppercase text-stone-500">laws</div>
              </div>
            )}
          </div>
        </div>
      </header>

      <div className="mb-6">
        <BrainCortex snapshot={snapshot} />
      </div>

      <ImprovementPanel improvement={improvement} history={brain?.history ?? []} />

      <div className="mt-6 grid gap-6 lg:grid-cols-5">
        <div className="lg:col-span-3 space-y-6">
          {snapshot?.audience && <AudiencePanel snapshot={snapshot} />}
          <LawsPanel
            laws={brain?.laws ?? snapshot?.lawsApplied ?? []}
            appliedIds={new Set((snapshot?.lawsApplied ?? []).map((l) => l.id))}
            addedIds={new Set((snapshot?.learning?.lawsAdded ?? []).map((l) => l.id))}
            loading={loading}
          />
        </div>

        <div className="lg:col-span-2 space-y-6">
          {snapshot?.foresight && <ForesightPanel snapshot={snapshot} />}
          {snapshot?.strategy && <StrategyPanel snapshot={snapshot} />}
          {brain && (
            <div className="rounded-xl border border-stone-200 bg-white p-4">
              <h3 className="font-serif text-sm font-bold text-stone-900">Demo control</h3>
              <p className="mt-1 text-xs text-stone-600">
                Wipe this brand's learned memory so the next run is a true cold start. The
                versioned snapshots in storage survive — a reset gives a clean baseline, it
                does not erase the evidence behind past claims.
              </p>
              <button
                onClick={handleReset}
                disabled={resetting}
                className="mt-3 flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-semibold text-rose-800 hover:bg-rose-100 disabled:opacity-50"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                {resetting ? 'Resetting…' : `Reset ${brandName} brain`}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

/* ------------------------------------------------------------------ metrics */

const Delta: React.FC<{ value: number; suffix?: string; invert?: boolean }> = ({
  value,
  suffix = '',
  invert = false,
}) => {
  // `invert` for metrics where down is good (retries). Without it a drop in
  // retries would render red, which is exactly backwards.
  const good = invert ? value < 0 : value > 0;
  const neutral = value === 0;
  const Icon = neutral ? Minus : good ? TrendingUp : TrendingDown;
  const color = neutral ? 'text-stone-500' : good ? 'text-emerald-700' : 'text-rose-700';
  return (
    <span className={`inline-flex items-center gap-1 font-mono text-sm font-bold ${color}`}>
      <Icon className="h-3.5 w-3.5" />
      {value > 0 ? '+' : ''}
      {value}
      {suffix}
    </span>
  );
};

const ImprovementPanel: React.FC<{
  improvement: ImprovementDelta | null;
  history: RunRecord[];
}> = ({ improvement, history }) => {
  if (!improvement) return null;

  const { hasBaseline, baseline, latest } = improvement;

  return (
    <section className="rounded-2xl border-2 border-emerald-800/20 bg-gradient-to-br from-emerald-50 to-[#FAF9F5] p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Target className="h-4 w-4 text-emerald-700" />
          <h2 className="font-serif text-lg font-bold text-stone-900">Measured self-improvement</h2>
        </div>
        <span className="rounded-full border border-emerald-200 bg-white px-2.5 py-1 font-mono text-[10px] uppercase tracking-wide text-emerald-800">
          {improvement.runs} run{improvement.runs === 1 ? '' : 's'} recorded
        </span>
      </div>

      <p className="mt-2 max-w-4xl text-sm leading-relaxed text-stone-700">
        {improvement.summary}
      </p>

      {improvement.caveat && (
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-700" />
          <p className="text-xs text-amber-900">{improvement.caveat}</p>
        </div>
      )}

      {hasBaseline && baseline && latest ? (
        <>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard
              label="First-attempt quality"
              hint="average critique score before any retry — the real learning signal"
              from={baseline.firstAttemptAvgScore}
              to={latest.firstAttemptAvgScore}
              delta={improvement.firstAttemptScoreDelta}
            />
            <MetricCard
              label="Retries needed"
              hint="regenerations to reach shippable work"
              from={baseline.retryCount}
              to={latest.retryCount}
              delta={improvement.retryDelta}
              invert
            />
            <MetricCard
              label="Final quality"
              hint="approved score across all assets"
              from={baseline.finalQualityScore}
              to={latest.finalQualityScore}
              delta={improvement.qualityDelta}
            />
            <MetricCard
              label="Audience resonance"
              hint="simulated panel — same personas each run"
              from={baseline.resonanceScore}
              to={latest.resonanceScore}
              delta={improvement.resonanceDelta ?? 0}
              unavailable={
                baseline.resonanceScore == null || latest.resonanceScore == null
              }
            />
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-1 font-mono text-[11px] text-stone-600">
            <span>
              baseline <span className="text-stone-900">{baseline.campaignId}</span> · brain v
              {baseline.brainVersionAtRun} · {baseline.lawsAvailable} laws
            </span>
            <span>→</span>
            <span>
              latest <span className="text-stone-900">{latest.campaignId}</span> · brain v
              {latest.brainVersionAtRun} · {latest.lawsAvailable} laws
            </span>
          </div>
        </>
      ) : (
        <div className="mt-4 rounded-xl border border-dashed border-emerald-300 bg-white/60 px-4 py-6 text-center">
          <p className="text-sm font-semibold text-stone-800">
            Baseline recorded. Run this brief again to measure the difference.
          </p>
          <p className="mt-1 text-xs text-stone-600">
            Nothing is claimed from a single run — one campaign is a baseline, not a trend.
          </p>
        </div>
      )}

      {history.length > 1 && <HistoryChart history={history} />}
    </section>
  );
};

const MetricCard: React.FC<{
  label: string;
  hint: string;
  from?: number | null;
  to?: number | null;
  delta: number;
  invert?: boolean;
  unavailable?: boolean;
}> = ({ label, hint, from, to, delta, invert = false, unavailable = false }) => (
  <div className="rounded-xl border border-stone-200 bg-white p-3">
    <div className="flex items-baseline justify-between">
      <span className="text-[11px] font-semibold uppercase tracking-wide text-stone-500">
        {label}
      </span>
      {!unavailable && <Delta value={delta} invert={invert} />}
    </div>
    {unavailable ? (
      <div className="mt-2 font-mono text-sm text-stone-400">not measured both runs</div>
    ) : (
      <div className="mt-1.5 flex items-baseline gap-2 font-mono">
        <span className="text-lg text-stone-400 line-through decoration-stone-300">{from}</span>
        <span className="text-stone-400">→</span>
        <span className="text-2xl font-bold text-stone-900">{to}</span>
      </div>
    )}
    <p className="mt-1 text-[10px] leading-snug text-stone-500">{hint}</p>
  </div>
);

/** Sparkline of first-attempt quality against the growing law count. */
const HistoryChart: React.FC<{ history: RunRecord[] }> = ({ history }) => {
  const W = 900;
  const H = 130;
  const PAD = 26;
  const points = history.map((r, i) => ({
    x: PAD + (i * (W - PAD * 2)) / Math.max(1, history.length - 1),
    y: H - PAD - ((r.firstAttemptAvgScore || 0) / 100) * (H - PAD * 2),
    record: r,
  }));
  const line = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');
  const maxLaws = Math.max(1, ...history.map((r) => r.lawsAvailable));

  return (
    <div className="mt-4 rounded-xl border border-stone-200 bg-white p-3">
      <div className="flex items-center justify-between">
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-stone-500">
          First-attempt quality per campaign
        </h3>
        <span className="font-mono text-[10px] text-stone-500">
          bars = learned laws available
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-1 w-full" role="img">
        {[0, 50, 100].map((tick) => {
          const y = H - PAD - (tick / 100) * (H - PAD * 2);
          return (
            <g key={tick}>
              <line x1={PAD} y1={y} x2={W - PAD} y2={y} stroke="#e7e5e4" strokeWidth="1" />
              <text x={4} y={y + 3} fontSize="9" fill="#a8a29e" className="font-mono">
                {tick}
              </text>
            </g>
          );
        })}

        {points.map((p) => {
          const barH = (p.record.lawsAvailable / maxLaws) * (H - PAD * 2) * 0.55;
          return (
            <rect
              key={`bar-${p.record.campaignId}`}
              x={p.x - 7}
              y={H - PAD - barH}
              width="14"
              height={barH}
              fill="#d1fae5"
              rx="2"
            />
          );
        })}

        <path d={line} fill="none" stroke="#047857" strokeWidth="2" />
        {points.map((p) => (
          <g key={p.record.campaignId}>
            <circle cx={p.x} cy={p.y} r="4" fill="#047857" />
            <title>
              {p.record.campaignId}: first attempts {p.record.firstAttemptAvgScore}/100,{' '}
              {p.record.lawsAvailable} laws, {p.record.retryCount} retries
            </title>
          </g>
        ))}
      </svg>
    </div>
  );
};

/* ----------------------------------------------------------------- audience */

const AudiencePanel: React.FC<{ snapshot: BrainSnapshot }> = ({ snapshot }) => {
  const report = snapshot.audience!;
  return (
    <section className="rounded-2xl border border-stone-200 bg-white p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Users className="h-4 w-4 text-rose-700" />
          <h2 className="font-serif text-lg font-bold text-stone-900">
            Simulated audience reaction
          </h2>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-stone-900 px-3 py-1 font-mono text-xs font-bold text-white">
            {report.resonanceScore}/100 resonance
          </span>
          <span
            className="rounded-full border border-stone-200 px-2.5 py-1 font-mono text-[10px] text-stone-600"
            title="Population standard deviation of sentiment. High means the panel is split, not lukewarm."
          >
            ±{report.polarization} spread
          </span>
        </div>
      </div>

      {report.consensus && (
        <p className="mt-2 text-sm leading-relaxed text-stone-700">{report.consensus}</p>
      )}

      {report.topObjection && (
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2">
          <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-rose-700" />
          <p className="text-xs text-rose-900">
            <span className="font-semibold">Top objection: </span>
            {report.topObjection}
          </p>
        </div>
      )}

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {report.reactions.map((reaction) => (
          <ReactionCard
            key={reaction.personaId}
            reaction={reaction}
            persona={report.personas.find((p) => p.id === reaction.personaId)}
          />
        ))}
      </div>

      <p className="mt-3 border-t border-stone-100 pt-2 text-[10px] leading-relaxed text-stone-500">
        {report.basis}
      </p>
    </section>
  );
};

const ReactionCard: React.FC<{
  reaction: PersonaReaction;
  persona?: { age: number; occupation: string; location: string; skepticism: number };
}> = ({ reaction, persona }) => {
  const style = VERDICT_STYLE[reaction.verdict] ?? VERDICT_STYLE.indifferent;
  return (
    <div className="rounded-xl border border-stone-200 bg-[#FAF9F5] p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate font-serif text-sm font-bold text-stone-900">
            {reaction.personaName}
          </div>
          {persona && (
            <div className="truncate font-mono text-[10px] text-stone-500">
              {persona.age} · {persona.occupation} · {persona.location}
            </div>
          )}
        </div>
        <span
          className={`shrink-0 rounded-full border px-2 py-0.5 font-mono text-[10px] font-semibold ${style.chip}`}
        >
          {reaction.verdict}
        </span>
      </div>

      <blockquote className="mt-2 flex gap-1.5">
        <Quote className="mt-0.5 h-3 w-3 shrink-0 text-stone-400" />
        <p className="text-sm italic leading-snug text-stone-800">{reaction.quote}</p>
      </blockquote>

      {reaction.objection && (
        <p className="mt-2 text-[11px] leading-snug text-stone-600">
          <span className="font-semibold text-stone-700">But: </span>
          {reaction.objection}
        </p>
      )}

      <div className="mt-2.5 grid grid-cols-3 gap-2 border-t border-stone-200 pt-2 font-mono text-[10px]">
        <Stat label="sentiment" value={`${reaction.sentiment}`} />
        <Stat label="would act" value={`${reaction.wouldAct}`} />
        <Stat
          label="attention"
          value={`${reaction.attentionSeconds}s`}
          icon={<Clock className="h-2.5 w-2.5" />}
        />
      </div>

      {persona && (
        <div className="mt-2">
          <div className="flex items-center justify-between font-mono text-[9px] text-stone-500">
            <span>skepticism</span>
            <span>{persona.skepticism}</span>
          </div>
          <div className="mt-0.5 h-1 w-full overflow-hidden rounded-full bg-stone-200">
            <div
              className="h-full rounded-full bg-stone-500"
              style={{ width: `${persona.skepticism}%` }}
            />
          </div>
        </div>
      )}
    </div>
  );
};

const Stat: React.FC<{ label: string; value: string; icon?: React.ReactNode }> = ({
  label,
  value,
  icon,
}) => (
  <div>
    <div className="flex items-center gap-1 text-stone-500">
      {icon}
      <span className="text-[9px] uppercase">{label}</span>
    </div>
    <div className="text-sm font-bold text-stone-900">{value}</div>
  </div>
);

/* -------------------------------------------------------------------- laws */

const LawsPanel: React.FC<{
  laws: BrandLaw[];
  appliedIds: Set<string>;
  addedIds: Set<string>;
  loading: boolean;
}> = ({ laws, appliedIds, addedIds, loading }) => (
  <section className="rounded-2xl border border-stone-200 bg-white p-5">
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <BookLock className="h-4 w-4 text-emerald-700" />
        <h2 className="font-serif text-lg font-bold text-stone-900">Learned brand laws</h2>
      </div>
      <span className="font-mono text-[10px] text-stone-500">
        {loading ? 'loading…' : `${laws.length} total`}
      </span>
    </div>

    <p className="mt-1 text-xs text-stone-600">
      Each law cites the rejected attempt or audience objection that produced it. Nothing here
      is an unsourced model opinion — laws without evidence are discarded before they are saved.
    </p>

    {laws.length === 0 ? (
      <p className="mt-4 rounded-lg border border-dashed border-stone-300 px-4 py-6 text-center text-sm text-stone-500">
        No laws yet. This brand's brain is a cold start — the first run's rejections are what
        write them.
      </p>
    ) : (
      <ul className="mt-4 space-y-2.5">
        {laws.map((law) => (
          <li
            key={law.id}
            className={`rounded-xl border p-3 ${
              addedIds.has(law.id)
                ? 'border-amber-300 bg-amber-50'
                : 'border-stone-200 bg-[#FAF9F5]'
            }`}
          >
            <div className="flex flex-wrap items-center gap-1.5">
              <span
                className={`rounded-full border px-2 py-0.5 font-mono text-[9px] font-semibold uppercase ${
                  CATEGORY_STYLE[law.category] ?? CATEGORY_STYLE.strategy
                }`}
              >
                {law.category}
              </span>
              {addedIds.has(law.id) && (
                <span className="rounded-full border border-amber-300 bg-amber-100 px-2 py-0.5 font-mono text-[9px] font-semibold uppercase text-amber-900">
                  new this run
                </span>
              )}
              {appliedIds.has(law.id) && !addedIds.has(law.id) && (
                <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 font-mono text-[9px] font-semibold uppercase text-emerald-800">
                  applied this run
                </span>
              )}
              {law.reinforcedCount > 1 && (
                <span
                  className="rounded-full border border-stone-300 bg-white px-2 py-0.5 font-mono text-[9px] text-stone-700"
                  title="Independently rediscovered by a later campaign"
                >
                  reinforced ×{law.reinforcedCount}
                </span>
              )}
            </div>

            <p className="mt-1.5 text-sm font-medium leading-snug text-stone-900">{law.text}</p>

            <p className="mt-1.5 border-l-2 border-stone-300 pl-2 text-[11px] italic leading-snug text-stone-600">
              {law.evidence}
            </p>

            <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 font-mono text-[9px] text-stone-500">
              <span>from {law.learnedFromCampaignId}</span>
              <span>confidence {law.confidence}</span>
              <span>{law.source}</span>
            </div>
          </li>
        ))}
      </ul>
    )}
  </section>
);

/* --------------------------------------------------------------- foresight */

const ForesightPanel: React.FC<{ snapshot: BrainSnapshot }> = ({ snapshot }) => {
  const f = snapshot.foresight!;
  const scored = f.calibrationError != null;
  return (
    <section className="rounded-2xl border border-stone-200 bg-white p-5">
      <div className="flex items-center gap-2">
        <Gauge className="h-4 w-4 text-sky-700" />
        <h2 className="font-serif text-lg font-bold text-stone-900">Foresight</h2>
      </div>
      <p className="mt-1 text-xs text-stone-600">
        Committed before a single generation call was made, then scored against the result —
        whether or not the answer flatters the brain.
      </p>

      <div className="mt-3 flex items-end gap-4">
        <div>
          <div className="font-mono text-[10px] uppercase text-stone-500">predicted</div>
          <div className="font-mono text-3xl font-bold text-stone-400">{f.predictedScore}</div>
        </div>
        <div className="pb-2 text-stone-400">vs</div>
        <div>
          <div className="font-mono text-[10px] uppercase text-stone-500">actual</div>
          <div className="font-mono text-3xl font-bold text-stone-900">
            {scored ? f.actualScore : '—'}
          </div>
        </div>
        {scored && (
          <div className="ml-auto pb-1 text-right">
            <div className="font-mono text-[10px] uppercase text-stone-500">off by</div>
            <div
              className={`font-mono text-xl font-bold ${
                (f.calibrationError ?? 0) <= 5
                  ? 'text-emerald-700'
                  : (f.calibrationError ?? 0) <= 12
                    ? 'text-amber-700'
                    : 'text-rose-700'
              }`}
            >
              {f.calibrationError}
            </div>
          </div>
        )}
      </div>

      <div className="mt-3 rounded-lg border border-stone-200 bg-[#FAF9F5] p-2.5">
        <div className="font-mono text-[10px] uppercase text-stone-500">
          predicted failure mode
        </div>
        <p className="mt-0.5 text-xs leading-snug text-stone-800">{f.likelyFailureMode}</p>
      </div>

      {f.rationale && (
        <p className="mt-2 text-[11px] leading-snug text-stone-600">{f.rationale}</p>
      )}

      <div className="mt-2 flex items-center justify-between font-mono text-[10px] text-stone-500">
        <span>self-reported confidence</span>
        <span className="text-stone-800">{f.confidence}%</span>
      </div>
    </section>
  );
};

/* ---------------------------------------------------------------- strategy */

const StrategyPanel: React.FC<{ snapshot: BrainSnapshot }> = ({ snapshot }) => {
  const s = snapshot.strategy!;
  return (
    <section className="rounded-2xl border border-stone-200 bg-white p-5">
      <div className="flex items-center gap-2">
        <Target className="h-4 w-4 text-emerald-700" />
        <h2 className="font-serif text-lg font-bold text-stone-900">Campaign strategy</h2>
      </div>
      <p className="mt-1 text-xs text-stone-600">
        The image, voiceover and copy generators never see each other's output. This is the only
        thing making them one campaign.
      </p>

      <blockquote className="mt-3 rounded-lg border-l-4 border-emerald-700 bg-emerald-50 px-3 py-2">
        <div className="font-mono text-[10px] uppercase text-emerald-800">big idea</div>
        <p className="mt-0.5 text-sm font-medium leading-snug text-stone-900">{s.bigIdea}</p>
      </blockquote>

      <dl className="mt-3 space-y-2">
        {[
          ['Positioning', s.positioning],
          ['Visual', s.visualDirection],
          ['Voice', s.voiceDirection],
          ['Copy', s.copyAngle],
        ]
          .filter(([, value]) => Boolean(value))
          .map(([label, value]) => (
            <div key={label}>
              <dt className="font-mono text-[10px] uppercase text-stone-500">{label}</dt>
              <dd className="text-xs leading-snug text-stone-800">{value}</dd>
            </div>
          ))}
      </dl>

      {s.avoid.length > 0 && (
        <div className="mt-3 rounded-lg border border-rose-200 bg-rose-50 p-2.5">
          <div className="font-mono text-[10px] uppercase text-rose-800">
            anti-patterns enforced
          </div>
          <ul className="mt-1 space-y-1">
            {s.avoid.map((item) => (
              <li key={item} className="flex gap-1.5 text-[11px] leading-snug text-rose-900">
                <span className="text-rose-500">✕</span>
                {item}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
};
