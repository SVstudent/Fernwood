import React, { useState } from 'react';
import { Attempt } from '../types';
import { 
  History, 
  CheckCircle2, 
  XCircle, 
  ChevronDown, 
  ChevronUp, 
  Terminal, 
  Cpu, 
  Sparkles,
  ArrowRight,
  ShieldCheck,
  Code
} from 'lucide-react';

interface ProvenanceLogProps {
  attempts: Attempt[];
  assetTypeTitle?: string;
  defaultExpanded?: boolean;
}

export const ProvenanceLog: React.FC<ProvenanceLogProps> = ({
  attempts,
  assetTypeTitle = 'Asset Provenance Chain',
  defaultExpanded = false
}) => {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const [activeAttemptTab, setActiveAttemptTab] = useState<number>(attempts.length - 1);

  if (!attempts || attempts.length === 0) return null;

  const currentAttempt = attempts[activeAttemptTab] || attempts[attempts.length - 1];

  return (
    <div className="rounded-xl border border-stone-200 bg-stone-50/80 overflow-hidden text-stone-800 transition-all">
      {/* Header Bar */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between p-4 bg-stone-100/80 hover:bg-stone-200/50 transition-colors text-left border-b border-stone-200"
      >
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-stone-900 text-stone-100">
            <History className="h-4 w-4" />
          </div>
          <div>
            <h4 className="text-xs font-semibold text-stone-900 font-sans flex items-center gap-2">
              <span>{assetTypeTitle}</span>
              <span className="rounded-full bg-stone-200 px-2 py-0.5 text-[10px] font-mono text-stone-700">
                {attempts.length} {attempts.length === 1 ? 'Attempt' : 'Attempts / Retries'}
              </span>
            </h4>
            <p className="text-[11px] text-stone-500 font-mono">
              Audit trail: prompt history, model info & self-critique verdict
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {attempts.some(a => a.critiqueVerdict === 'FAIL') && (
            <span className="hidden sm:inline-flex items-center gap-1 text-[11px] font-mono text-amber-700 bg-amber-50 px-2 py-0.5 rounded-md border border-amber-200">
              <Sparkles className="h-3 w-3" /> Auto-Retry Executed
            </span>
          )}
          {isExpanded ? <ChevronUp className="h-4 w-4 text-stone-500" /> : <ChevronDown className="h-4 w-4 text-stone-500" />}
        </div>
      </button>

      {/* Expandable Body */}
      {isExpanded && (
        <div className="p-4 sm:p-5 space-y-4 bg-white">
          {/* Attempt Selector Tabs if multiple attempts */}
          {attempts.length > 1 && (
            <div className="flex items-center gap-2 border-b border-stone-200 pb-3 overflow-x-auto">
              <span className="text-[11px] font-mono text-stone-400 uppercase tracking-wider font-semibold mr-1">
                Attempt:
              </span>
              {attempts.map((att, idx) => {
                const isPass = att.critiqueVerdict === 'PASS';
                const isSelected = activeAttemptTab === idx;
                return (
                  <button
                    key={att.id}
                    onClick={() => setActiveAttemptTab(idx)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-medium transition-all ${
                      isSelected
                        ? 'bg-stone-900 text-white shadow-xs'
                        : 'bg-stone-100 text-stone-600 hover:bg-stone-200'
                    }`}
                  >
                    <span>#{att.attemptNumber}</span>
                    {isPass ? (
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                    ) : (
                      <XCircle className="h-3.5 w-3.5 text-rose-400" />
                    )}
                    <span className="text-[10px] opacity-75">({att.critique.overallScore}/100)</span>
                  </button>
                );
              })}
            </div>
          )}

          {/* Active Attempt Details Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Left Column: Model & Prompt Metadata */}
            <div className="space-y-3">
              <div className="flex items-center justify-between text-xs font-mono text-stone-500">
                <span className="flex items-center gap-1">
                  <Cpu className="h-3.5 w-3.5 text-stone-400" />
                  Provider: <strong className="text-stone-800">{currentAttempt.providerName}</strong>
                </span>
                <span className="rounded bg-stone-100 px-2 py-0.5 border border-stone-200">
                  {currentAttempt.modelName}
                </span>
              </div>

              {/* Prompt Box */}
              <div className="rounded-lg bg-stone-900 text-stone-100 p-3.5 font-mono text-xs space-y-1.5 shadow-inner">
                <div className="flex items-center justify-between text-[10px] text-stone-400 border-b border-stone-800 pb-1">
                  <span className="flex items-center gap-1">
                    <Terminal className="h-3 w-3 text-amber-400" />
                    PROMPT USED (ATTEMPT #{currentAttempt.attemptNumber})
                  </span>
                  <span>{new Date(currentAttempt.timestamp).toLocaleTimeString()}</span>
                </div>
                <p className="leading-relaxed text-stone-200 text-[11px] whitespace-pre-wrap">
                  {currentAttempt.promptUsed}
                </p>
              </div>

              {/* If Retry: Prompt Evolution Note */}
              {currentAttempt.attemptNumber > 1 && (
                <div className="p-3 bg-amber-50 rounded-lg border border-amber-200 text-xs text-amber-900 space-y-1">
                  <div className="flex items-center gap-1.5 font-semibold text-amber-900">
                    <Sparkles className="h-3.5 w-3.5 text-amber-600" />
                    Prompt Revision Triggered by Critique
                  </div>
                  {/* The actual critique that caused this retry — not a
                      canned blurb. This is the causal link that makes the
                      self-critique loop auditable. */}
                  <p className="text-[11px] leading-relaxed text-amber-800">
                    {attempts[activeAttemptTab - 1]?.critique?.suggestedFixes ||
                      'Prompt was automatically restructured to address the previous critique.'}
                  </p>
                </div>
              )}
            </div>

            {/* Right Column: Critique Verdict & Scoring Breakdown */}
            <div className="rounded-lg border border-stone-200 p-3.5 bg-stone-50/50 space-y-3">
              <div className="flex items-center justify-between border-b border-stone-200 pb-2.5">
                <div className="flex items-center gap-2">
                  {currentAttempt.critiqueVerdict === 'PASS' ? (
                    <div className="flex items-center gap-1.5 text-emerald-700 bg-emerald-100 px-2.5 py-1 rounded-md text-xs font-semibold border border-emerald-300">
                      <ShieldCheck className="h-4 w-4 text-emerald-600" />
                      CRITIQUE VERDICT: PASSED
                    </div>
                  ) : (
                    <div className="flex items-center gap-1.5 text-rose-700 bg-rose-100 px-2.5 py-1 rounded-md text-xs font-semibold border border-rose-300">
                      <XCircle className="h-4 w-4 text-rose-600" />
                      CRITIQUE VERDICT: REJECTED
                    </div>
                  )}
                </div>
                <div className="text-right">
                  <span className="text-lg font-bold font-mono text-stone-900">
                    {currentAttempt.critique.overallScore}
                  </span>
                  <span className="text-xs text-stone-400 font-mono">/100</span>
                </div>
              </div>

              {/* Reasoning */}
              <div className="text-xs text-stone-700 space-y-1">
                <p className="font-semibold text-stone-900">Critique Reasoning:</p>
                <p className="leading-relaxed italic text-stone-600 bg-white p-2.5 rounded border border-stone-200/80">
                  "{currentAttempt.critique.reasoning}"
                </p>
              </div>

              {/* Individual Criteria Bars */}
              <div className="space-y-2 pt-1">
                <p className="text-[11px] font-mono font-semibold uppercase text-stone-400 tracking-wider">
                  Score Breakdown:
                </p>
                {currentAttempt.critique.criteria.map((c, idx) => (
                  <div key={idx} className="space-y-1">
                    <div className="flex justify-between text-[11px]">
                      <span className="font-medium text-stone-800">{c.name}</span>
                      <span className="font-mono text-stone-600">
                        {c.score}/{c.targetScore} {c.passed ? '✓' : '✗'}
                      </span>
                    </div>
                    <div className="h-1.5 w-full bg-stone-200 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${
                          c.passed ? 'bg-emerald-600' : 'bg-rose-500'
                        }`}
                        style={{ width: `${Math.min(100, (c.score / 100) * 100)}%` }}
                      />
                    </div>
                    <p className="text-[10px] text-stone-500 italic">{c.feedback}</p>
                  </div>
                ))}
              </div>

              {/* Suggested Fixes if Failed */}
              {!currentAttempt.critique.passed && currentAttempt.critique.suggestedFixes && (
                <div className="pt-2 border-t border-dashed border-stone-200 text-xs text-rose-800">
                  <strong className="block mb-0.5">Automated Fix Instructions:</strong>
                  <span className="text-[11px]">{currentAttempt.critique.suggestedFixes}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
