import React, { useState, useEffect, useRef } from 'react';
import { Campaign, PipelineStageLog, PipelineStageId, AssetType } from '../types';
import { 
  Sparkles, 
  CheckCircle2, 
  XCircle, 
  RefreshCw, 
  Terminal, 
  Play, 
  Pause, 
  SkipForward, 
  ShieldCheck, 
  Cpu, 
  Layers, 
  ArrowRight,
  Database,
  Image as ImageIcon,
  Mic,
  FileText
} from 'lucide-react';

interface PipelineRunViewProps {
  campaign: Campaign | null;
  logs: PipelineStageLog[];
  isPaused: boolean;
  onTogglePause: () => void;
  onSkipStage?: () => void;
  onViewResult: () => void;
}

const STAGES: { id: PipelineStageId; label: string; icon: any }[] = [
  { id: 'brief_analysis', label: 'Brief Analysis', icon: Layers },
  { id: 'image_gen', label: 'Visual Gen & Critique', icon: ImageIcon },
  { id: 'audio_gen', label: 'Audio Gen & Critique', icon: Mic },
  { id: 'copy_gen', label: 'Copy Gen & Critique', icon: FileText },
  { id: 'assembly', label: 'Assembly & B2 Store', icon: Database }
];

export const PipelineRunView: React.FC<PipelineRunViewProps> = ({
  campaign,
  logs,
  isPaused,
  onTogglePause,
  onSkipStage,
  onViewResult
}) => {
  const [activeTab, setActiveTab] = useState<'console' | 'inspector'>('console');
  const logsEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll console logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  // Calculate overall progress percent
  const latestLog = logs[logs.length - 1];
  const isFinished = campaign?.status === 'completed';

  let progressPercent = 10;
  if (latestLog) {
    if (latestLog.stage === 'brief_analysis') progressPercent = 20;
    if (latestLog.stage === 'image_gen' || latestLog.stage === 'image_critique') progressPercent = 45;
    if (latestLog.stage === 'audio_gen' || latestLog.stage === 'audio_critique') progressPercent = 70;
    if (latestLog.stage === 'copy_gen' || latestLog.stage === 'copy_critique') progressPercent = 88;
    if (latestLog.stage === 'assembly' || latestLog.stage === 'b2_upload') progressPercent = 96;
  }
  if (isFinished) progressPercent = 100;

  // Extract all retry/rejected attempts from logs to display the "Agentic Critique Pipeline in Action"
  const rejectedLogs = logs.filter((l) => l.type === 'warning' && l.attemptDetails);
  const passedLogs = logs.filter((l) => l.type === 'success' && l.attemptDetails);

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6 space-y-6">
      {/* Top Banner & Controls */}
      <div className="rounded-2xl border border-stone-200 bg-white p-6 shadow-sm space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-0.5 text-xs font-semibold ${
                isFinished
                  ? 'bg-emerald-100 text-emerald-800 border border-emerald-300'
                  : 'bg-amber-100 text-amber-900 border border-amber-300 animate-pulse'
              }`}>
                <Sparkles className="h-3.5 w-3.5" />
                {isFinished ? 'PIPELINE COMPLETE' : 'AGENTIC PIPELINE RUNNING'}
              </span>
              <span className="text-xs text-stone-500 font-mono">
                {campaign?.brandName || 'Brand Brief'}
              </span>
            </div>
            <h2 className="font-serif text-2xl font-bold text-stone-900">
              {isFinished ? 'Campaign Kit Ready!' : 'Running Self-Critique & Retry Loop...'}
            </h2>
          </div>

          <div className="flex items-center gap-2">
            {!isFinished && (
              <>
                <button
                  onClick={onTogglePause}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-stone-200 bg-stone-50 px-3.5 py-2 text-xs font-medium text-stone-700 hover:bg-stone-100 transition-colors"
                >
                  {isPaused ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
                  <span>{isPaused ? 'Resume' : 'Pause'}</span>
                </button>
              </>
            )}

            {isFinished && (
              <button
                onClick={onViewResult}
                className="inline-flex items-center gap-2 rounded-xl bg-[#1E3A2B] px-5 py-2.5 text-xs font-bold text-white shadow-sm hover:bg-[#152a1f] transition-all"
              >
                <span>View Final Campaign Kit</span>
                <ArrowRight className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>

        {/* Progress Bar */}
        <div className="space-y-1.5">
          <div className="flex justify-between text-xs font-mono text-stone-600">
            <span>Progress: {progressPercent}%</span>
            <span>
              {rejectedLogs.length > 0 ? `${rejectedLogs.length} Auto-Retry Triggered` : 'Evaluating...'}
            </span>
          </div>
          <div className="h-2.5 w-full bg-stone-100 rounded-full overflow-hidden border border-stone-200">
            <div
              className={`h-full transition-all duration-300 ${
                isFinished ? 'bg-emerald-600' : 'bg-[#D97706]'
              }`}
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>

        {/* Stage Breadcrumb Steps */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 pt-2 border-t border-stone-100">
          {STAGES.map((s, idx) => {
            const Icon = s.icon;
            const isCurrent = latestLog?.stage.includes(s.id.split('_')[0]);
            const isCompleted = isFinished || (progressPercent > (idx + 1) * 20);

            return (
              <div
                key={s.id}
                className={`flex items-center gap-2 p-2 rounded-xl border text-xs font-sans transition-all ${
                  isCompleted
                    ? 'border-emerald-200 bg-emerald-50/50 text-emerald-900'
                    : isCurrent
                    ? 'border-amber-300 bg-amber-50 text-amber-900 font-semibold ring-1 ring-amber-300/50'
                    : 'border-stone-200 bg-stone-50/50 text-stone-400'
                }`}
              >
                <div className={`flex h-6 w-6 items-center justify-center rounded-lg ${
                  isCompleted ? 'bg-emerald-600 text-white' : isCurrent ? 'bg-amber-500 text-white animate-spin' : 'bg-stone-200 text-stone-500'
                }`}>
                  {isCompleted ? <CheckCircle2 className="h-3.5 w-3.5" /> : <Icon className="h-3.5 w-3.5" />}
                </div>
                <span className="truncate text-[11px] font-medium">{s.label}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Main Agentic Activity View */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Streaming Console Log (2 cols) */}
        <div className="lg:col-span-2 rounded-2xl border border-stone-800 bg-stone-950 text-stone-200 p-5 shadow-lg space-y-4">
          <div className="flex items-center justify-between border-b border-stone-800 pb-3">
            <div className="flex items-center gap-2">
              <Terminal className="h-4 w-4 text-emerald-400" />
              <h3 className="text-xs font-bold font-mono text-stone-100 uppercase tracking-wider">
                Genblaze Agent Execution Stream
              </h3>
            </div>
            <span className="text-[10px] text-stone-500 font-mono">
              {logs.length} events logged
            </span>
          </div>

          {/* Console Log Feed */}
          <div className="h-96 overflow-y-auto space-y-2.5 font-mono text-xs pr-2 scrollbar-thin">
            {logs.map((log) => {
              const isWarning = log.type === 'warning';
              const isSuccess = log.type === 'success';

              return (
                <div
                  key={log.id}
                  className={`p-3 rounded-lg border transition-all ${
                    isWarning
                      ? 'bg-amber-950/40 border-amber-800/80 text-amber-200'
                      : isSuccess
                      ? 'bg-emerald-950/40 border-emerald-800/80 text-emerald-200'
                      : 'bg-stone-900/80 border-stone-800 text-stone-300'
                  }`}
                >
                  <div className="flex items-center justify-between text-[10px] text-stone-400 border-b border-stone-800/60 pb-1 mb-1.5">
                    <span className="font-semibold text-stone-300 uppercase tracking-wider">
                      [{log.stage}] {log.title}
                    </span>
                    <span>{new Date(log.timestamp).toLocaleTimeString()}</span>
                  </div>

                  <p className="text-[11px] leading-relaxed whitespace-pre-wrap">
                    {log.message}
                  </p>

                  {/* Show Critique Reason if Attempt Log */}
                  {log.attemptDetails && (
                    <div className="mt-2 pt-2 border-t border-stone-800/80 text-[10px] space-y-1">
                      <div className="flex justify-between">
                        <span className="text-stone-400">Model: {log.attemptDetails.modelName}</span>
                        <span className="font-bold">Score: {log.attemptDetails.critique.overallScore}/100</span>
                      </div>
                      {log.attemptDetails.critiqueVerdict === 'FAIL' && (
                        <div className="text-amber-300 italic">
                          ↳ Retry Trigger: {log.attemptDetails.critique.suggestedFixes}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
            <div ref={logsEndRef} />
          </div>
        </div>

        {/* Right Column: Live Critique & Retry Inspector (1 col) */}
        <div className="space-y-4">
          {/* Active Retry Highlights Card */}
          <div className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm space-y-3">
            <h3 className="text-xs font-bold text-stone-900 uppercase tracking-wider font-mono flex items-center gap-2 border-b border-stone-100 pb-2">
              <RefreshCw className="h-4 w-4 text-amber-600" />
              Self-Critique & Retry Feed
            </h3>

            {rejectedLogs.length === 0 ? (
              <div className="p-4 rounded-xl bg-stone-50 border border-stone-200 text-center space-y-1 text-stone-500">
                <ShieldCheck className="h-6 w-6 text-emerald-600 mx-auto" />
                <p className="text-xs font-semibold text-stone-800">Evaluating Quality</p>
                <p className="text-[11px]">Any asset failing mood critique will automatically trigger an adjusted prompt retry here.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {rejectedLogs.map((log) => {
                  const att = log.attemptDetails!;
                  return (
                    <div key={log.id} className="p-3.5 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-900 space-y-2">
                      <div className="flex items-center justify-between font-bold border-b border-amber-200/80 pb-1">
                        <span className="flex items-center gap-1 text-amber-800">
                          <XCircle className="h-3.5 w-3.5 text-rose-500" />
                          Attempt #{att.attemptNumber} Rejected
                        </span>
                        <span className="text-[10px] font-mono bg-amber-200/60 px-1.5 py-0.5 rounded">
                          {att.critique.overallScore}/100
                        </span>
                      </div>
                      <p className="text-[11px] leading-relaxed text-amber-900 italic">
                        "{att.critique.reasoning}"
                      </p>
                      <div className="text-[10px] bg-white/80 p-2 rounded border border-amber-200 font-mono text-stone-800">
                        <strong className="text-amber-800 block mb-0.5">Adjusted Prompt for Attempt #{att.attemptNumber + 1}:</strong>
                        <span>{att.critique.suggestedFixes}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Approved Highlights Card */}
          <div className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm space-y-3">
            <h3 className="text-xs font-bold text-stone-900 uppercase tracking-wider font-mono flex items-center gap-2 border-b border-stone-100 pb-2">
              <ShieldCheck className="h-4 w-4 text-emerald-600" />
              Passing Assets Summary
            </h3>

            {passedLogs.length === 0 ? (
              <p className="text-xs text-stone-500 italic">No assets passed yet...</p>
            ) : (
              <div className="space-y-2">
                {passedLogs.map((log) => (
                  <div key={log.id} className="flex items-center justify-between p-2.5 rounded-xl bg-emerald-50 border border-emerald-200 text-xs">
                    <span className="font-semibold text-emerald-900 capitalize">
                      {log.assetType} Approved
                    </span>
                    <span className="font-mono text-emerald-700 font-bold">
                      {log.attemptDetails?.critique.overallScore}/100 ✓
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
