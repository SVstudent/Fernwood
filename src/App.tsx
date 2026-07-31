import React, { useEffect, useState } from 'react';
import { Campaign, CampaignBrief, PipelineStageLog } from './types';
import { PRESEEDED_CAMPAIGNS } from './data/preseededCampaigns';
import { Header } from './components/Header';
import { BriefInputView } from './components/BriefInputView';
import { PipelineRunView } from './components/PipelineRunView';
import { CampaignResultView } from './components/CampaignResultView';
import { LibraryView } from './components/LibraryView';
import {
  executeFullCampaignPipeline,
  listCampaigns,
  deleteCampaignRemote,
} from './services/pipelineService';

export default function App() {
  const [campaigns, setCampaigns] = useState<Campaign[]>(PRESEEDED_CAMPAIGNS);
  const [currentView, setCurrentView] = useState<'library' | 'brief' | 'pipeline' | 'result'>('library');
  const [activeCampaign, setActiveCampaign] = useState<Campaign | null>(PRESEEDED_CAMPAIGNS[0]);
  const [pipelineLogs, setPipelineLogs] = useState<PipelineStageLog[]>([]);
  const [isPipelinePaused, setIsPipelinePaused] = useState(false);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [isLibraryLoading, setIsLibraryLoading] = useState(true);

  // Hydrate the library from Backblaze B2 (via the backend). Falls back to the
  // preseeded sample campaigns when storage is empty or unreachable, so the
  // gallery is never blank during a demo.
  useEffect(() => {
    let cancelled = false;
    listCampaigns()
      .then((remote) => {
        if (cancelled || !remote || remote.length === 0) return;
        setCampaigns(remote);
        setActiveCampaign((current) => current ?? remote[0]);
      })
      .finally(() => {
        if (!cancelled) setIsLibraryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Trigger campaign pipeline execution
  const handleLaunchPipeline = async (brief: CampaignBrief) => {
    setCurrentView('pipeline');
    setPipelineLogs([]);
    setIsPipelinePaused(false);
    setPipelineError(null);

    try {
      const finalCampaign = await executeFullCampaignPipeline(
        brief,
        (newLog) => {
          setPipelineLogs((prev) => [...prev, newLog]);
        },
        (updatedCampaign) => {
          setActiveCampaign(updatedCampaign);
        }
      );

      // Add newly completed campaign to state list
      setCampaigns((prev) => [finalCampaign, ...prev.filter((c) => c.id !== finalCampaign.id)]);
      setActiveCampaign(finalCampaign);
    } catch (err) {
      console.error('Pipeline error:', err);
      setPipelineError(err instanceof Error ? err.message : 'The pipeline run failed.');
    }
  };

  const handleSelectCampaign = (campaign: Campaign) => {
    setActiveCampaign(campaign);
    setCurrentView('result');
  };

  const handleDeleteCampaign = (campaignId: string) => {
    setCampaigns((prev) => prev.filter((c) => c.id !== campaignId));
    void deleteCampaignRemote(campaignId);
    if (activeCampaign?.id === campaignId) {
      setActiveCampaign(null);
      setCurrentView('library');
    }
  };

  return (
    <div className="min-h-screen bg-[#FAF9F5] text-stone-900 font-sans selection:bg-emerald-200 selection:text-emerald-900 flex flex-col justify-between">
      <div>
        {/* Navigation Header */}
        <Header
          currentView={currentView}
          onNavigate={(view) => setCurrentView(view)}
          campaignCount={campaigns.length}
          hasActiveResult={!!activeCampaign}
        />

        {/* Library hydration indicator (B2 read) */}
        {isLibraryLoading && currentView === 'library' && (
          <div className="h-0.5 w-full overflow-hidden bg-stone-200">
            <div className="h-full w-1/3 animate-pulse bg-emerald-600" />
          </div>
        )}

        {/* Provider/transport failure — distinct from a critique-fail retry,
            which surfaces as a warning inside the pipeline log stream. */}
        {pipelineError && (
          <div className="mx-auto mt-4 max-w-7xl px-4 sm:px-6">
            <div className="flex items-start justify-between gap-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3">
              <div className="text-sm text-red-800">
                <p className="font-semibold">Pipeline run failed</p>
                <p className="mt-0.5 font-mono text-xs text-red-700">{pipelineError}</p>
              </div>
              <button
                onClick={() => setPipelineError(null)}
                className="shrink-0 text-xs font-medium text-red-700 underline hover:text-red-900"
              >
                Dismiss
              </button>
            </div>
          </div>
        )}

        {/* Dynamic Views */}
        <main className="pb-16">
          {currentView === 'library' && (
            <LibraryView
              campaigns={campaigns}
              onSelectCampaign={handleSelectCampaign}
              onNewBrief={() => setCurrentView('brief')}
              onDeleteCampaign={handleDeleteCampaign}
            />
          )}

          {currentView === 'brief' && (
            <BriefInputView onSubmitBrief={handleLaunchPipeline} />
          )}

          {currentView === 'pipeline' && (
            <PipelineRunView
              campaign={activeCampaign}
              logs={pipelineLogs}
              isPaused={isPipelinePaused}
              onTogglePause={() => setIsPipelinePaused(!isPipelinePaused)}
              onViewResult={() => setCurrentView('result')}
            />
          )}

          {currentView === 'result' && activeCampaign && (
            <CampaignResultView
              campaign={activeCampaign}
              onBackToLibrary={() => setCurrentView('library')}
              onReRunBrief={() => setCurrentView('brief')}
            />
          )}
        </main>
      </div>

      {/* Footer */}
      <footer className="border-t border-stone-200 bg-white py-6">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-stone-500 font-mono">
          <div className="flex items-center gap-2">
            <span className="font-bold font-serif text-stone-900">Fernwood</span>
            <span>•</span>
            <span>AI Brand Campaign Generator MVP Scaffold</span>
          </div>

          <div className="flex items-center gap-4 text-[11px]">
            <span>Genblaze Pipeline</span>
            <span>•</span>
            <span>Backblaze B2 Storage</span>
            <span>•</span>
            <span>Self-Critique & Retry Engine</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
