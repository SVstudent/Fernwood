import React from 'react';
import { Sparkles, Library, PlusCircle, ShieldCheck, Database, Layers } from 'lucide-react';

interface HeaderProps {
  currentView: 'brief' | 'pipeline' | 'result' | 'library';
  onNavigate: (view: 'brief' | 'pipeline' | 'result' | 'library') => void;
  campaignCount: number;
  hasActiveResult: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  currentView,
  onNavigate,
  campaignCount,
  hasActiveResult
}) => {
  return (
    <header className="sticky top-0 z-40 border-b border-stone-200 bg-[#FAF9F5]/90 backdrop-blur-md">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6">
        {/* Brand Logo & Name */}
        <div 
          onClick={() => onNavigate('library')}
          className="flex cursor-pointer items-center gap-3 group"
        >
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#1E3A2B] text-[#F4F1EA] shadow-sm transition-transform duration-200 group-hover:scale-105">
            <Layers className="h-5 w-5 text-[#D97706]" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-serif text-xl font-bold tracking-tight text-stone-900">
                Fernwood
              </span>
              <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-800 border border-emerald-200">
                MVP Pipeline
              </span>
            </div>
            <p className="text-xs text-stone-500 font-sans">
              AI Brand Campaign Engine with Self-Critique & Retry
            </p>
          </div>
        </div>

        {/* View Switcher Tabs */}
        <nav className="flex items-center gap-1 rounded-xl bg-stone-100/80 p-1 border border-stone-200/80">
          <button
            onClick={() => onNavigate('library')}
            className={`flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-medium transition-all ${
              currentView === 'library'
                ? 'bg-white text-stone-900 shadow-xs border border-stone-200'
                : 'text-stone-600 hover:text-stone-900 hover:bg-stone-200/50'
            }`}
          >
            <Library className="h-3.5 w-3.5" />
            <span>Library</span>
            <span className="ml-0.5 rounded-md bg-stone-100 px-1.5 py-0.2 text-[10px] text-stone-600 font-mono">
              {campaignCount}
            </span>
          </button>

          {hasActiveResult && (
            <button
              onClick={() => onNavigate('result')}
              className={`flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-medium transition-all ${
                currentView === 'result'
                  ? 'bg-white text-stone-900 shadow-xs border border-stone-200'
                  : 'text-stone-600 hover:text-stone-900 hover:bg-stone-200/50'
              }`}
            >
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />
              <span>Current Kit</span>
            </button>
          )}

          {currentView === 'pipeline' && (
            <button
              onClick={() => onNavigate('pipeline')}
              className="flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-semibold bg-amber-500 text-white shadow-xs animate-pulse"
            >
              <Sparkles className="h-3.5 w-3.5" />
              <span>Pipeline Running...</span>
            </button>
          )}

          <button
            onClick={() => onNavigate('brief')}
            className={`flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-all ${
              currentView === 'brief'
                ? 'bg-[#1E3A2B] text-white shadow-xs'
                : 'bg-[#1E3A2B]/90 text-white hover:bg-[#1E3A2B]'
            }`}
          >
            <PlusCircle className="h-3.5 w-3.5 text-[#D97706]" />
            <span>New Brief</span>
          </button>
        </nav>

        {/* Backend Handoff Badges */}
        <div className="hidden md:flex items-center gap-2 text-[11px] text-stone-500 font-mono">
          <span className="flex items-center gap-1 rounded-md bg-stone-100 px-2 py-1 border border-stone-200">
            <Sparkles className="h-3 w-3 text-emerald-600" />
            Genblaze AI
          </span>
          <span className="flex items-center gap-1 rounded-md bg-stone-100 px-2 py-1 border border-stone-200">
            <Database className="h-3 w-3 text-amber-600" />
            B2 Storage
          </span>
        </div>
      </div>
    </header>
  );
};
