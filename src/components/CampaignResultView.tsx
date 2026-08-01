import React, { useState } from 'react';
import { Campaign } from '../types';
import { AudioPlayerMock } from './AudioPlayerMock';
import { ProvenanceLog } from './ProvenanceLog';
import { 
  ShieldCheck, 
  Download, 
  Share2, 
  Sparkles, 
  Copy, 
  Check, 
  ExternalLink, 
  Tag, 
  Layers, 
  Code, 
  Maximize2, 
  Database,
  ArrowLeft,
  FileText
} from 'lucide-react';

interface CampaignResultViewProps {
  campaign: Campaign;
  onBackToLibrary: () => void;
  onReRunBrief: () => void;
}

export const CampaignResultView: React.FC<CampaignResultViewProps> = ({
  campaign,
  onBackToLibrary,
  onReRunBrief
}) => {
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [showExportModal, setShowExportModal] = useState(false);
  const [isImageZoomed, setIsImageZoomed] = useState(false);

  const imageAsset = campaign.assets.image;
  const audioAsset = campaign.assets.audio;
  const copyAsset = campaign.assets.copy;

  const approvedImgAttempt = imageAsset?.attempts.find(a => a.id === imageAsset.finalApprovedAttemptId) || imageAsset?.attempts[imageAsset.attempts.length - 1];
  const approvedAudAttempt = audioAsset?.attempts.find(a => a.id === audioAsset.finalApprovedAttemptId) || audioAsset?.attempts[audioAsset.attempts.length - 1];
  const approvedCpyAttempt = copyAsset?.attempts.find(a => a.id === copyAsset.finalApprovedAttemptId) || copyAsset?.attempts[copyAsset.attempts.length - 1];

  const handleCopyText = (text: string, fieldName: string) => {
    navigator.clipboard.writeText(text);
    setCopiedField(fieldName);
    setTimeout(() => setCopiedField(null), 2000);
  };

  const downloadMarkdownSummary = () => {
    const md = `
# ${campaign.brandName} — Brand Campaign Kit
*Generated via Fernwood AI Pipeline on ${new Date(campaign.createdAt).toLocaleDateString()}*

## 1. Brand Guidelines
- **Product/Service:** ${campaign.productService}
- **Tone/Mood:** ${campaign.toneTags.join(', ')}
- **Quality Score:** ${campaign.overallQualityScore}/100

## 2. Marketing Copy Suite
### Headline
${approvedCpyAttempt?.content.headline || ''}

### Subheadline
${approvedCpyAttempt?.content.subheadline || ''}

### Primary Body Copy
${approvedCpyAttempt?.content.bodyText || ''}

### Call to Action
${approvedCpyAttempt?.content.callToAction || ''}

### Key Benefit Highlights
${approvedCpyAttempt?.content.keyBenefitBullets?.map(b => `- ${b}`).join('\n') || ''}

### Social Media Posts
${approvedCpyAttempt?.content.socialPosts?.map(p => `> ${p}`).join('\n\n') || ''}

## 3. Audio Voiceover Script
"${approvedAudAttempt?.content.audioScript || ''}"

## 4. Provenance Summary
- Total Attempts Executed: ${campaign.totalAttemptsCount}
- Auto-Retries Triggered: ${campaign.retryCount}
- Backblaze B2 Object Key: campaigns/${campaign.id}/campaign.json
- Genblaze Manifests: campaigns/${campaign.id}/runs/ (one SHA-256-verified manifest per attempt)
${[campaign.assets.image, campaign.assets.audio, campaign.assets.copy]
  .filter(Boolean)
  .flatMap((a) => a!.attempts.map((t) => `  - ${a!.type} attempt ${t.attemptNumber} [${t.critiqueVerdict}] sha256: ${t.content.manifestHash ?? 'n/a'}`))
  .join('\n')}
    `.trim();

    const blob = new Blob([md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${campaign.brandName.toLowerCase().replace(/\s+/g, '-')}-campaign-kit.md`;
    a.click();
  };

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 space-y-8">
      {/* Back Navigation Bar */}
      <div className="flex items-center justify-between">
        <button
          onClick={onBackToLibrary}
          className="inline-flex items-center gap-2 text-xs font-semibold text-stone-600 hover:text-stone-900 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          <span>Back to Library</span>
        </button>

        <div className="flex items-center gap-2">
          <button
            onClick={onReRunBrief}
            className="inline-flex items-center gap-1.5 rounded-xl border border-stone-200 bg-white px-3.5 py-2 text-xs font-semibold text-stone-700 hover:bg-stone-50 transition-colors shadow-2xs"
          >
            <Sparkles className="h-3.5 w-3.5 text-amber-600" />
            <span>Tweak Brief & Re-run</span>
          </button>

          <button
            onClick={downloadMarkdownSummary}
            className="inline-flex items-center gap-1.5 rounded-xl bg-[#1E3A2B] px-4 py-2 text-xs font-bold text-white hover:bg-[#152a1f] transition-all shadow-xs"
          >
            <Download className="h-3.5 w-3.5 text-[#D97706]" />
            <span>Export Campaign Kit</span>
          </button>
        </div>
      </div>

      {/* Hero Header Card */}
      <div className="rounded-2xl border border-stone-200 bg-white p-6 sm:p-8 shadow-xs space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-stone-100 pb-6">
          <div className="space-y-2">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-3 py-1 text-xs font-bold text-emerald-900 border border-emerald-200">
                <ShieldCheck className="h-3.5 w-3.5 text-emerald-700" />
                CRITIQUE VERDICT: PASSED
              </span>
              {campaign.toneTags.map((t, idx) => (
                <span key={idx} className="rounded-md bg-stone-100 px-2.5 py-0.5 text-xs font-medium text-stone-700 border border-stone-200">
                  {t}
                </span>
              ))}
            </div>

            <h1 className="font-serif text-3xl sm:text-4xl font-bold text-stone-900 tracking-tight">
              {campaign.brandName}
            </h1>
            <p className="text-sm text-stone-600 max-w-3xl leading-relaxed">
              {campaign.productService}
            </p>
          </div>

          {/* Quality Score Gauge */}
          <div className="flex items-center gap-3 bg-stone-50 p-4 rounded-2xl border border-stone-200/80 self-start">
            <div className="text-right">
              <span className="block text-[11px] font-mono text-stone-600 uppercase tracking-wider font-semibold">
                Quality Score
              </span>
              <span className="font-serif text-3xl font-bold text-stone-900">
                {campaign.overallQualityScore}
                <span className="text-sm text-stone-600 font-mono font-normal">/100</span>
              </span>
            </div>
            <div className="h-10 w-10 rounded-full bg-emerald-600 text-white flex items-center justify-center font-bold text-sm shadow-xs">
              ✓
            </div>
          </div>
        </div>

        {/* Quick Stats & Metadata Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-stone-600 font-mono pt-1">
          <div className="flex items-center gap-4">
            <span>Attempts Executed: <strong>{campaign.totalAttemptsCount}</strong></span>
            <span>Retries Triggered: <strong className="text-amber-700">{campaign.retryCount}</strong></span>
            <span>Created: {new Date(campaign.createdAt).toLocaleDateString()}</span>
          </div>

          <button
            onClick={() => setShowExportModal(true)}
            className="text-stone-600 hover:text-stone-900 underline flex items-center gap-1"
          >
            <Code className="h-3.5 w-3.5" />
            <span>Inspect JSON Payload</span>
          </button>
        </div>
      </div>

      {/* Main Assets Grid (2 Cols: Left Image & Audio, Right Copywriting) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Left Column: Visual & Audio Assets */}
        <div className="space-y-6">
          {/* Approved Image Poster Card */}
          <div className="rounded-2xl border border-stone-200 bg-white p-5 shadow-xs space-y-4">
            <div className="flex items-center justify-between border-b border-stone-100 pb-3">
              <div>
                <h3 className="text-xs font-bold text-stone-900 uppercase tracking-wider font-mono">
                  Approved Key Visual Poster
                </h3>
                <p className="text-[11px] text-stone-600 font-mono">
                  Model: {approvedImgAttempt?.modelName || 'genblaze-image-v3'} (Attempt #{approvedImgAttempt?.attemptNumber})
                </p>
              </div>

              <button
                onClick={() => setIsImageZoomed(true)}
                className="p-1.5 text-stone-600 hover:bg-stone-100 rounded-lg transition-colors"
                title="Zoom Image"
              >
                <Maximize2 className="h-4 w-4" />
              </button>
            </div>

            {/* Poster Image Container */}
            <div className="relative rounded-xl overflow-hidden border border-stone-200/80 bg-stone-900 aspect-video shadow-inner group">
              <img
                src={approvedImgAttempt?.content.imageUrl}
                alt={campaign.brandName}
                className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-102"
              />
              <div className="absolute bottom-3 left-3 bg-stone-900/80 backdrop-blur-md px-2.5 py-1 rounded-md text-[10px] text-stone-200 font-mono border border-stone-700">
                16:9 • SVG Vector High-Res
              </div>
            </div>

            {/* Image Prompt Used */}
            <div className="p-3 rounded-lg bg-stone-50 border border-stone-200 text-xs font-mono space-y-1">
              <span className="text-[10px] text-stone-600 font-bold uppercase block">Approved Image Prompt:</span>
              <p className="text-stone-800 text-[11px] leading-relaxed line-clamp-2">
                {approvedImgAttempt?.promptUsed}
              </p>
            </div>
          </div>

          {/* Approved Audio Player Card */}
          {approvedAudAttempt && (
            <AudioPlayerMock
              scriptText={approvedAudAttempt.content.audioScript || ''}
              voiceName={approvedAudAttempt.content.audioVoice || 'Resonant Baritone'}
              durationSeconds={approvedAudAttempt.content.durationSeconds || 8.5}
              waveformData={approvedAudAttempt.content.audioWaveformData}
              modelName={approvedAudAttempt.modelName}
              audioUrl={approvedAudAttempt.content.audioUrl}
            />
          )}
        </div>

        {/* Right Column: Approved Copywriting Suite */}
        <div className="rounded-2xl border border-stone-200 bg-white p-6 shadow-xs space-y-6">
          <div className="flex items-center justify-between border-b border-stone-100 pb-3">
            <div>
              <h3 className="text-xs font-bold text-stone-900 uppercase tracking-wider font-mono">
                Approved Marketing Copy Suite
              </h3>
              <p className="text-[11px] text-stone-600 font-mono">
                Model: {approvedCpyAttempt?.modelName || 'gemini-2.5-pro'}
              </p>
            </div>
          </div>

          {/* Headline & Subheadline */}
          <div className="space-y-3">
            <div className="group relative p-4 rounded-xl bg-stone-50 border border-stone-200">
              <span className="text-[10px] font-mono font-bold uppercase text-stone-600 block mb-1">
                Headline
              </span>
              <h2 className="font-serif text-xl font-bold text-stone-900 pr-8">
                {approvedCpyAttempt?.content.headline}
              </h2>
              <button
                onClick={() => handleCopyText(approvedCpyAttempt?.content.headline || '', 'headline')}
                className="absolute top-3 right-3 p-1.5 text-stone-600 hover:text-stone-800 rounded hover:bg-stone-200/60"
              >
                {copiedField === 'headline' ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
              </button>
            </div>

            <div className="group relative p-4 rounded-xl bg-stone-50 border border-stone-200">
              <span className="text-[10px] font-mono font-bold uppercase text-stone-600 block mb-1">
                Subheadline
              </span>
              <p className="text-sm font-semibold text-stone-800 pr-8">
                {approvedCpyAttempt?.content.subheadline}
              </p>
              <button
                onClick={() => handleCopyText(approvedCpyAttempt?.content.subheadline || '', 'subheadline')}
                className="absolute top-3 right-3 p-1.5 text-stone-600 hover:text-stone-800 rounded hover:bg-stone-200/60"
              >
                {copiedField === 'subheadline' ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
              </button>
            </div>
          </div>

          {/* Body Copy & Call To Action */}
          <div className="space-y-3">
            <div className="group relative p-4 rounded-xl bg-stone-50 border border-stone-200">
              <span className="text-[10px] font-mono font-bold uppercase text-stone-600 block mb-1">
                Primary Campaign Copy
              </span>
              <p className="text-xs text-stone-700 leading-relaxed pr-8 whitespace-pre-wrap">
                {approvedCpyAttempt?.content.bodyText}
              </p>
              <button
                onClick={() => handleCopyText(approvedCpyAttempt?.content.bodyText || '', 'bodyText')}
                className="absolute top-3 right-3 p-1.5 text-stone-600 hover:text-stone-800 rounded hover:bg-stone-200/60"
              >
                {copiedField === 'bodyText' ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
              </button>
            </div>

            <div className="p-3.5 rounded-xl bg-[#1E3A2B] text-white flex items-center justify-between">
              <div>
                <span className="text-[10px] font-mono text-stone-300 uppercase block">Call To Action</span>
                <span className="text-xs font-bold text-stone-100">{approvedCpyAttempt?.content.callToAction}</span>
              </div>
              <button
                onClick={() => handleCopyText(approvedCpyAttempt?.content.callToAction || '', 'cta')}
                className="px-2.5 py-1 rounded bg-[#D97706] text-[11px] font-bold hover:bg-[#b46203] transition-colors"
              >
                {copiedField === 'cta' ? 'Copied!' : 'Copy CTA'}
              </button>
            </div>
          </div>

          {/* Social Media Posts */}
          {approvedCpyAttempt?.content.socialPosts && approvedCpyAttempt.content.socialPosts.length > 0 && (
            <div className="space-y-2 pt-2 border-t border-stone-100">
              <span className="text-[11px] font-mono font-bold uppercase text-stone-600">
                Social Media Ad Posts
              </span>
              {approvedCpyAttempt.content.socialPosts.map((post, idx) => (
                <div key={idx} className="group relative p-3 rounded-lg bg-stone-50 border border-stone-200 text-xs text-stone-700">
                  <p className="pr-8">{post}</p>
                  <button
                    onClick={() => handleCopyText(post, `social-${idx}`)}
                    className="absolute top-2.5 right-2.5 p-1 text-stone-600 hover:text-stone-800"
                  >
                    {copiedField === `social-${idx}` ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Comprehensive Provenance Log & Critique Chain Section */}
      <div className="space-y-4 pt-4 border-t border-stone-200">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="font-serif text-2xl font-bold text-stone-900">
              Full Provenance Record & Critique Chain
            </h2>
            <p className="text-xs text-stone-600">
              Every attempt executed by the AI pipeline — including rejected attempts, critique reasoning, and prompt revisions.
            </p>
          </div>
        </div>

        <div className="space-y-4">
          {imageAsset && (
            <ProvenanceLog
              attempts={imageAsset.attempts}
              assetTypeTitle="Visual Image Asset Provenance"
              defaultExpanded={true}
            />
          )}

          {audioAsset && (
            <ProvenanceLog
              attempts={audioAsset.attempts}
              assetTypeTitle="Audio Voiceover Asset Provenance"
              defaultExpanded={false}
            />
          )}

          {copyAsset && (
            <ProvenanceLog
              attempts={copyAsset.attempts}
              assetTypeTitle="Marketing Copy Asset Provenance"
              defaultExpanded={false}
            />
          )}
        </div>
      </div>

      {/* Image Zoom Modal */}
      {isImageZoomed && (
        <div 
          onClick={() => setIsImageZoomed(false)}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 cursor-pointer"
        >
          <div className="max-w-4xl max-h-[90vh] overflow-hidden rounded-2xl bg-stone-900 p-2 shadow-2xl">
            <img
              src={approvedImgAttempt?.content.imageUrl}
              alt={campaign.brandName}
              className="w-full h-auto max-h-[85vh] object-contain rounded-xl"
            />
          </div>
        </div>
      )}

      {/* JSON Payload Inspection Modal */}
      {showExportModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
          <div className="w-full max-w-2xl max-h-[85vh] rounded-2xl bg-stone-900 text-stone-100 p-6 shadow-2xl overflow-hidden flex flex-col space-y-4 border border-stone-800">
            <div className="flex items-center justify-between border-b border-stone-800 pb-3">
              <h3 className="font-mono text-xs font-bold text-amber-400 flex items-center gap-2">
                <Database className="h-4 w-4" />
                Backblaze B2: campaigns/{campaign.id}/campaign.json
              </h3>
              <button
                onClick={() => setShowExportModal(false)}
                className="text-stone-400 hover:text-white"
              >
                ✕
              </button>
            </div>

            <pre className="flex-1 overflow-y-auto bg-stone-950 p-4 rounded-xl text-[11px] font-mono text-stone-300 leading-relaxed scrollbar-thin">
              {JSON.stringify(campaign, null, 2)}
            </pre>

            <div className="flex justify-end gap-2 pt-2 border-t border-stone-800">
              <button
                onClick={() => {
                  navigator.clipboard.writeText(JSON.stringify(campaign, null, 2));
                  setCopiedField('json');
                  setTimeout(() => setCopiedField(null), 2000);
                }}
                className="px-4 py-2 rounded-xl bg-stone-800 hover:bg-stone-700 text-xs font-mono font-semibold text-white transition-colors"
              >
                {copiedField === 'json' ? 'Copied JSON!' : 'Copy Raw JSON'}
              </button>
              <button
                onClick={() => setShowExportModal(false)}
                className="px-4 py-2 rounded-xl bg-[#1E3A2B] hover:bg-[#152a1f] text-xs font-bold text-white transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
