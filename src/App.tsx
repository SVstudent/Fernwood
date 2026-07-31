import React, { useState } from 'react';
import { Campaign, CampaignBrief, PipelineStageLog } from './types';
import { PRESEEDED_CAMPAIGNS } from './data/preseededCampaigns';
import { Header } from './components/Header';
import { BriefInputView } from './components/BriefInputView';
import { PipelineRunView } from './components/PipelineRunView';
import { CampaignResultView } from './components/CampaignResultView';
import { LibraryView } from './components/LibraryView';
import { executeFullCampaignPipeline } from './services/pipelineService';

export default function App() {
  const [campaigns, setCampaigns] = useState<Campaign[]>(PRESEEDED_CAMPAIGNS);
  const [currentView, setCurrentView] = useState<'library' | 'brief' | 'pipeline' | 'result'>('library');
  const [activeCampaign, setActiveCampaign] = useState<Campaign | null>(PRESEEDED_CAMPAIGNS[0]);
  const [pipelineLogs, setPipelineLogs] = useState<PipelineStageLog[]>([]);
  const [isPipelinePaused, setIsPipelinePaused] = useState(false);

  // Trigger campaign pipeline execution
  const handleLaunchPipeline = async (brief: CampaignBrief) => {
    setCurrentView('pipeline');
    setPipelineLogs([]);
    setIsPipelinePaused(false);

    let currentCampaignDraft: Campaign | null = null;

    try {
      const finalCampaign = await executeFullCampaignPipeline(
        brief,
        (newLog) => {
          setPipelineLogs((prev) => [...prev, newLog]);
        },
        (updatedCampaign) => {
          currentCampaignDraft = updatedCampaign;
          setActiveCampaign(updatedCampaign);
        }
      );

      // Add newly completed campaign to state list
      setCampaigns((prev) => [finalCampaign, ...prev.filter((c) => c.id !== finalCampaign.id)]);
      setActiveCampaign(finalCampaign);
    } catch (err) {
      console.error('Pipeline error:', err);
    }
  };

  const handleSelectCampaign = (campaign: Campaign) => {
    setActiveCampaign(campaign);
    setCurrentView('result');
  };

  const handleDeleteCampaign = (campaignId: string) => {
    setCampaigns((prev) => prev.filter((c) => c.id !== campaignId));
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
