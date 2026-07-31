import React, { useState } from 'react';
import { Campaign } from '../types';
import { 
  Search, 
  Filter, 
  PlusCircle, 
  ShieldCheck, 
  Sparkles, 
  ArrowRight, 
  Trash2, 
  Layers, 
  Clock,
  RefreshCw,
  Copy
} from 'lucide-react';

interface LibraryViewProps {
  campaigns: Campaign[];
  onSelectCampaign: (campaign: Campaign) => void;
  onNewBrief: () => void;
  onDeleteCampaign: (id: string) => void;
}

export const LibraryView: React.FC<LibraryViewProps> = ({
  campaigns,
  onSelectCampaign,
  onNewBrief,
  onDeleteCampaign
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTagFilter, setSelectedTagFilter] = useState<string | null>(null);

  // Extract unique tone tags across all campaigns
  const allTags = Array.from(
    new Set(campaigns.flatMap((c) => c.toneTags))
  );

  const filteredCampaigns = campaigns.filter((c) => {
    const matchesSearch =
      c.brandName.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.productService.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.briefText.toLowerCase().includes(searchQuery.toLowerCase());

    const matchesTag = selectedTagFilter
      ? c.toneTags.includes(selectedTagFilter)
      : true;

    return matchesSearch && matchesTag;
  });

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 space-y-8">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-stone-200 pb-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="rounded-full bg-stone-200 px-2.5 py-0.5 text-[11px] font-mono text-stone-700 font-semibold">
              Campaign Kit Library ({campaigns.length})
            </span>
          </div>
          <h1 className="font-serif text-3xl font-bold text-stone-900 tracking-tight">
            Brand Campaign Kits
          </h1>
          <p className="text-xs text-stone-600 font-sans mt-0.5">
            Browse AI-generated campaign kits with full self-critique provenance & retry audit records.
          </p>
        </div>

        <button
          onClick={onNewBrief}
          className="inline-flex items-center gap-2 rounded-xl bg-[#1E3A2B] px-5 py-2.5 text-xs font-bold text-white shadow-sm hover:bg-[#152a1f] active:scale-95 transition-all self-start md:self-auto"
        >
          <PlusCircle className="h-4 w-4 text-[#D97706]" />
          <span>New Brand Campaign Brief</span>
        </button>
      </div>

      {/* Search & Filter Bar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 rounded-2xl bg-white p-4 border border-stone-200 shadow-2xs">
        {/* Search Input */}
        <div className="relative w-full sm:w-80">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-stone-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search campaigns by brand or keyword..."
            className="w-full rounded-xl border border-stone-200 bg-stone-50/50 pl-10 pr-4 py-2 text-xs text-stone-900 focus:border-[#1E3A2B] focus:bg-white focus:outline-none transition-all"
          />
        </div>

        {/* Tag Filters */}
        <div className="flex items-center gap-2 overflow-x-auto w-full sm:w-auto pb-1 sm:pb-0">
          <Filter className="h-3.5 w-3.5 text-stone-400 shrink-0" />
          <button
            onClick={() => setSelectedTagFilter(null)}
            className={`px-3 py-1 rounded-lg text-xs font-medium transition-all shrink-0 ${
              selectedTagFilter === null
                ? 'bg-stone-900 text-white shadow-2xs'
                : 'bg-stone-100 text-stone-600 hover:bg-stone-200'
            }`}
          >
            All Tones
          </button>
          {allTags.map((tag) => (
            <button
              key={tag}
              onClick={() => setSelectedTagFilter(selectedTagFilter === tag ? null : tag)}
              className={`px-3 py-1 rounded-lg text-xs font-medium transition-all shrink-0 ${
                selectedTagFilter === tag
                  ? 'bg-[#1E3A2B] text-white shadow-2xs'
                  : 'bg-stone-100 text-stone-600 hover:bg-stone-200'
              }`}
            >
              {tag}
            </button>
          ))}
        </div>
      </div>

      {/* Campaign Cards Grid */}
      {filteredCampaigns.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-stone-300 bg-white p-12 text-center space-y-3">
          <Layers className="h-10 w-10 text-stone-400 mx-auto" />
          <h3 className="font-serif text-lg font-bold text-stone-800">No Campaign Kits Found</h3>
          <p className="text-xs text-stone-500 max-w-sm mx-auto">
            Try adjusting your search filters or generate a new brand campaign brief.
          </p>
          <button
            onClick={onNewBrief}
            className="inline-flex items-center gap-2 rounded-xl bg-[#1E3A2B] px-4 py-2 text-xs font-bold text-white hover:bg-[#152a1f] transition-all"
          >
            <PlusCircle className="h-3.5 w-3.5 text-[#D97706]" />
            <span>Create Campaign Brief</span>
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredCampaigns.map((camp) => {
            const imgAsset = camp.assets.image;
            const approvedAttempt = imgAsset?.attempts.find((a) => a.id === imgAsset.finalApprovedAttemptId) || imgAsset?.attempts[imgAsset?.attempts.length - 1];

            return (
              <div
                key={camp.id}
                onClick={() => onSelectCampaign(camp)}
                className="group relative rounded-2xl border border-stone-200 bg-white overflow-hidden shadow-xs hover:shadow-md hover:border-stone-300 transition-all cursor-pointer flex flex-col justify-between"
              >
                {/* Thumbnail Header */}
                <div className="relative aspect-video bg-stone-900 overflow-hidden">
                  {approvedAttempt?.content.imageUrl ? (
                    <img
                      src={approvedAttempt.content.imageUrl}
                      alt={camp.brandName}
                      className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-103"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-stone-500 font-mono text-xs">
                      No Poster Generated
                    </div>
                  )}

                  {/* Quality Score Badge */}
                  <div className="absolute top-3 right-3 bg-stone-900/85 backdrop-blur-md px-2.5 py-1 rounded-full text-xs font-bold text-emerald-400 border border-stone-700 shadow-sm flex items-center gap-1 font-mono">
                    <span>{camp.overallQualityScore}</span>
                    <span className="text-[10px] text-stone-400">/100</span>
                  </div>

                  {camp.retryCount > 0 && (
                    <div className="absolute bottom-3 left-3 bg-amber-500 text-white px-2 py-0.5 rounded-md text-[10px] font-bold font-mono shadow-xs flex items-center gap-1">
                      <RefreshCw className="h-3 w-3" />
                      <span>{camp.retryCount} Retries Passed</span>
                    </div>
                  )}
                </div>

                {/* Card Body */}
                <div className="p-5 space-y-3 flex-1 flex flex-col justify-between">
                  <div className="space-y-2">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      {camp.toneTags.map((t, idx) => (
                        <span
                          key={idx}
                          className="rounded bg-stone-100 px-2 py-0.5 text-[10px] font-semibold text-stone-600 border border-stone-200"
                        >
                          {t}
                        </span>
                      ))}
                    </div>

                    <h3 className="font-serif text-xl font-bold text-stone-900 group-hover:text-emerald-800 transition-colors">
                      {camp.brandName}
                    </h3>

                    <p className="text-xs text-stone-600 line-clamp-2 leading-relaxed">
                      {camp.productService}
                    </p>
                  </div>

                  {/* Card Footer */}
                  <div className="pt-3 border-t border-stone-100 flex items-center justify-between text-[11px] text-stone-500 font-mono">
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {new Date(camp.createdAt).toLocaleDateString()}
                    </span>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onDeleteCampaign(camp.id);
                        }}
                        className="p-1 text-stone-400 hover:text-rose-600 transition-colors"
                        title="Delete Kit"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>

                      <span className="font-semibold text-[#1E3A2B] group-hover:underline flex items-center gap-0.5">
                        <span>View Kit</span>
                        <ArrowRight className="h-3.5 w-3.5" />
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
