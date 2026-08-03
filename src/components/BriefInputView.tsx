import React, { useState } from 'react';
import { CampaignBrief, ToneMood, ColorPreference } from '../types';
import { 
  Sparkles, 
  Palette, 
  Tag, 
  ArrowRight, 
  Zap, 
  BookOpen, 
  Check, 
  Layers,
  Sliders,
  HelpCircle
} from 'lucide-react';

interface BriefInputViewProps {
  onSubmitBrief: (brief: CampaignBrief) => void;
}

const TONE_OPTIONS: ToneMood[] = [
  'Earthy & Organic',
  'Cozy & Warm',
  'High-Tech Futuristic',
  'Minimalist Luxury',
  'Playful & Bold',
  'Energetic Athletic',
  'Professional & Authoritative'
];

const PALETTE_PRESETS: { name: string; colors: ColorPreference }[] = [
  {
    name: 'Forest Oak & Gold',
    colors: { primary: '#1E3A2B', secondary: '#F4F1EA', accent: '#D97706' }
  },
  {
    name: 'Midnight Cyber Slate',
    colors: { primary: '#0F172A', secondary: '#F8FAFC', accent: '#38BDF8' }
  },
  {
    name: 'Warm Sunset Amber',
    colors: { primary: '#451A03', secondary: '#FEF3C7', accent: '#B45309' }
  },
  {
    name: 'Botanical Sage',
    colors: { primary: '#2D4A3E', secondary: '#F0F4F1', accent: '#A3E635' }
  },
  {
    name: 'Minimal Obsidian',
    colors: { primary: '#18181B', secondary: '#FAFAFA', accent: '#E4E4E7' }
  }
];

const PRESET_TEMPLATES = [
  {
    title: 'Earthy Leather Goods',
    brandName: 'Oak & Grain Co.',
    productService: 'Handcrafted Heritage Leather Travel Bags & Travel Wallets',
    targetAudience: 'Eco-conscious weekend travelers & design enthusiasts',
    briefText: 'Highlight sustainable vegetable-tanned leather, warm forest oak textures, and heirloom lifetime durability. Tone should feel warm, grounded, and rustic yet modern.',
    tones: ['Earthy & Organic', 'Cozy & Warm'],
    paletteIdx: 0
  },
  {
    title: 'Futuristic Cyber Audio',
    brandName: 'Vortex Spatial',
    productService: '3D Spatial Noise-Canceling Wireless Earbuds with Titanium Drivers',
    targetAudience: 'Audiophiles, remote coders, commuters, spatial audio gamers',
    briefText: 'Ultra-sleek cyber-acoustic campaign highlighting zero latency, active spatial isolation, and matte titanium build.',
    tones: ['High-Tech Futuristic', 'Minimalist Luxury'],
    paletteIdx: 1
  },
  {
    title: 'Morning Artisanal Coffee',
    brandName: 'Solstice Roast',
    productService: 'Single-Origin Ethiopian Dark Roast Coffee Beans',
    targetAudience: 'Morning ritual seekers & specialty coffee connoisseurs',
    briefText: 'Warm, cozy morning ritual campaign celebrating slow pour-over coffee, notes of toasted hazelnut and dark chocolate, bathed in golden sunlight.',
    tones: ['Cozy & Warm', 'Earthy & Organic'],
    paletteIdx: 2
  }
];

// Mirrors FERNWOOD_AD_SHOTS x FERNWOOD_VIDEO_DURATION on the backend, plus the
// ~2.5s end card. Shown so the opt-in states the real runtime rather than the
// per-shot length.
const AD_SHOTS = 3;
const SHOT_SECONDS = 6;
const AD_SECONDS = AD_SHOTS * SHOT_SECONDS + 3;

export const BriefInputView: React.FC<BriefInputViewProps> = ({ onSubmitBrief }) => {
  const [brandName, setBrandName] = useState('Fernwood Goods');
  const [productService, setProductService] = useState('Handcrafted Heritage Leather Bags & Sustainable Canvas Goods');
  const [targetAudience, setTargetAudience] = useState('Eco-conscious weekend travelers, design enthusiasts, urban professionals');
  const [briefText, setBriefText] = useState('Highlight sustainable craftsmanship, warmth of forest oak leather, and lifetime durability. Tone should feel warm, grounded, and rustic yet refined.');
  const [selectedTones, setSelectedTones] = useState<string[]>(['Earthy & Organic', 'Cozy & Warm']);
  const [selectedPalette, setSelectedPalette] = useState<ColorPreference>(PALETTE_PRESETS[0].colors);
  const [includeVideo, setIncludeVideo] = useState(false);

  const toggleTone = (tone: string) => {
    if (selectedTones.includes(tone)) {
      if (selectedTones.length > 1) {
        setSelectedTones(selectedTones.filter((t) => t !== tone));
      }
    } else {
      setSelectedTones([...selectedTones, tone]);
    }
  };

  const applyPreset = (preset: typeof PRESET_TEMPLATES[0]) => {
    setBrandName(preset.brandName);
    setProductService(preset.productService);
    setTargetAudience(preset.targetAudience);
    setBriefText(preset.briefText);
    setSelectedTones(preset.tones);
    setSelectedPalette(PALETTE_PRESETS[preset.paletteIdx].colors);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!brandName.trim() || !productService.trim()) return;

    onSubmitBrief({
      brandName,
      productService,
      targetAudience,
      briefText,
      toneTags: selectedTones,
      colors: selectedPalette,
      includeVideo
    });
  };

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      {/* Hero Intro Header */}
      <div className="mb-8 text-center space-y-3">
        <div className="inline-flex items-center gap-2 rounded-full bg-emerald-100/80 px-3 py-1 text-xs font-semibold text-emerald-900 border border-emerald-200 shadow-2xs">
          <Sparkles className="h-3.5 w-3.5 text-emerald-700" />
          Self-Critique & Auto-Retry Campaign Pipeline
        </div>
        <h1 className="font-serif text-3xl sm:text-4xl font-bold tracking-tight text-stone-900">
          Create Your Brand Campaign Kit
        </h1>
        <p className="mx-auto max-w-2xl text-sm text-stone-600 leading-relaxed font-sans">
          Enter your campaign brief below. Fernwood's agentic AI pipeline will generate visual imagery, audio voiceover, and marketing copy, automatically evaluating each asset against your brief and retrying until it passes critique.
        </p>
      </div>

      {/* Quick Template Presets */}
      <div className="mb-8 rounded-2xl border border-stone-200 bg-white p-4 sm:p-5 shadow-xs">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 text-xs font-semibold text-stone-900 font-sans">
            <Zap className="h-4 w-4 text-amber-500" />
            <span>Quick Start Campaign Brief Templates</span>
          </div>
          <span className="text-[11px] text-stone-500 font-mono">1-click auto-fill</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {PRESET_TEMPLATES.map((tmpl, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => applyPreset(tmpl)}
              className="text-left p-3 rounded-xl border border-stone-200 bg-stone-50/70 hover:bg-white hover:border-emerald-600 hover:shadow-xs transition-all group"
            >
              <h4 className="text-xs font-bold text-stone-900 group-hover:text-emerald-800 transition-colors">
                {tmpl.title}
              </h4>
              <p className="text-[11px] text-stone-500 line-clamp-1 mt-0.5">
                {tmpl.brandName} • {tmpl.tones.join(', ')}
              </p>
            </button>
          ))}
        </div>
      </div>

      {/* Main Form */}
      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="rounded-2xl border border-stone-200 bg-white p-6 sm:p-8 shadow-xs space-y-6">
          {/* Section 1: Core Brand Info */}
          <div className="space-y-4">
            <h3 className="text-sm font-bold text-stone-900 uppercase tracking-wider font-mono flex items-center gap-2 border-b border-stone-100 pb-2">
              <BookOpen className="h-4 w-4 text-[#1E3A2B]" />
              1. Brand Identity & Product Details
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-stone-700 mb-1.5">
                  Brand Name <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={brandName}
                  onChange={(e) => setBrandName(e.target.value)}
                  placeholder="e.g. Fernwood Goods"
                  className="w-full rounded-xl border border-stone-200 bg-stone-50/50 px-3.5 py-2.5 text-sm text-stone-900 focus:border-[#1E3A2B] focus:bg-white focus:outline-none transition-all"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-stone-700 mb-1.5">
                  Target Audience
                </label>
                <input
                  type="text"
                  value={targetAudience}
                  onChange={(e) => setTargetAudience(e.target.value)}
                  placeholder="e.g. Eco-conscious weekend travelers"
                  className="w-full rounded-xl border border-stone-200 bg-stone-50/50 px-3.5 py-2.5 text-sm text-stone-900 focus:border-[#1E3A2B] focus:bg-white focus:outline-none transition-all"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-stone-700 mb-1.5">
                Product or Service Description <span className="text-rose-500">*</span>
              </label>
              <input
                type="text"
                required
                value={productService}
                onChange={(e) => setProductService(e.target.value)}
                placeholder="e.g. Handcrafted Heritage Leather Bags & Sustainable Canvas Goods"
                className="w-full rounded-xl border border-stone-200 bg-stone-50/50 px-3.5 py-2.5 text-sm text-stone-900 focus:border-[#1E3A2B] focus:bg-white focus:outline-none transition-all"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-stone-700 mb-1.5">
                Campaign Brief & Story Guidelines
              </label>
              <textarea
                rows={3}
                value={briefText}
                onChange={(e) => setBriefText(e.target.value)}
                placeholder="Describe key selling points, mood notes, texture preferences, and emotional hooks..."
                className="w-full rounded-xl border border-stone-200 bg-stone-50/50 px-3.5 py-2.5 text-sm text-stone-900 focus:border-[#1E3A2B] focus:bg-white focus:outline-none transition-all leading-relaxed resize-none"
              />
            </div>
          </div>

          {/* Section 2: Tone & Mood Selection */}
          <div className="space-y-3 pt-2 border-t border-stone-100">
            <h3 className="text-sm font-bold text-stone-900 uppercase tracking-wider font-mono flex items-center gap-2">
              <Tag className="h-4 w-4 text-[#D97706]" />
              2. Desired Brand Tone & Mood
            </h3>
            <p className="text-xs text-stone-500">
              The AI self-critique pass will explicitly evaluate generated assets against these mood tags.
            </p>

            <div className="flex flex-wrap gap-2 pt-1">
              {TONE_OPTIONS.map((tone) => {
                const isSelected = selectedTones.includes(tone);
                return (
                  <button
                    key={tone}
                    type="button"
                    onClick={() => toggleTone(tone)}
                    className={`flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-medium transition-all ${
                      isSelected
                        ? 'bg-[#1E3A2B] text-white shadow-xs'
                        : 'bg-stone-100 text-stone-700 hover:bg-stone-200'
                    }`}
                  >
                    {isSelected && <Check className="h-3.5 w-3.5 text-[#D97706]" />}
                    <span>{tone}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Section 3: Color Palette Preferences */}
          <div className="space-y-3 pt-2 border-t border-stone-100">
            <h3 className="text-sm font-bold text-stone-900 uppercase tracking-wider font-mono flex items-center gap-2">
              <Palette className="h-4 w-4 text-emerald-700" />
              3. Visual Color Palette
            </h3>

            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5">
              {PALETTE_PRESETS.map((p, idx) => {
                const isSelected =
                  selectedPalette.primary === p.colors.primary &&
                  selectedPalette.accent === p.colors.accent;
                return (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => setSelectedPalette(p.colors)}
                    className={`p-2.5 rounded-xl border text-left transition-all ${
                      isSelected
                        ? 'border-[#1E3A2B] bg-emerald-50/40 ring-2 ring-[#1E3A2B]/20'
                        : 'border-stone-200 bg-stone-50/50 hover:bg-white'
                    }`}
                  >
                    <div className="flex h-5 w-full rounded-md overflow-hidden mb-1.5 shadow-2xs">
                      <div className="w-1/2 h-full" style={{ backgroundColor: p.colors.primary }} />
                      <div className="w-1/4 h-full" style={{ backgroundColor: p.colors.secondary }} />
                      <div className="w-1/4 h-full" style={{ backgroundColor: p.colors.accent }} />
                    </div>
                    <span className="text-[11px] font-semibold text-stone-800 line-clamp-1">
                      {p.name}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Advertisement opt-in — off by default: it costs a generated frame
            AND a generated clip per shot, plus real provider quota. */}
        <label className="flex items-start gap-3 rounded-2xl border border-stone-200 bg-white p-5 cursor-pointer hover:border-stone-300 transition-colors">
          <input
            type="checkbox"
            checked={includeVideo}
            onChange={(e) => setIncludeVideo(e.target.checked)}
            className="mt-0.5 h-4 w-4 accent-[#D97706] cursor-pointer"
          />
          <span>
            <span className="block text-sm font-bold text-stone-900 font-sans">
              Also produce a full advertisement
            </span>
            <span className="block text-xs text-stone-600 font-sans mt-0.5">
              Writes a storyboard, then generates {AD_SHOTS} <em>distinct scenes</em> —
              hook, product, benefit — each with its own first frame and camera
              move. Cuts them together into a ~{AD_SECONDS}s commercial with the
              approved voiceover laid over it and a branded end card. Shots render
              in parallel; adds roughly three minutes to the run.
            </span>
          </span>
        </label>

        {/* Submit CTA */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 rounded-2xl bg-[#1E3A2B] p-6 text-white shadow-md">
          <div>
            <h3 className="text-base font-bold font-serif flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-[#D97706]" />
              Ready to Run AI Critique Pipeline?
            </h3>
            <p className="text-xs text-stone-300 font-sans mt-0.5">
              Generates Image, Audio{includeVideo ? `, a ${AD_SHOTS}-shot Advertisement` : ''}, and Copy with
              self-critique scoring and automatic retries.
            </p>
          </div>

          <button
            type="submit"
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2.5 rounded-xl bg-[#D97706] px-6 py-3 text-sm font-bold text-white shadow-sm hover:bg-[#b46203] active:scale-95 transition-all font-sans cursor-pointer"
          >
            <span>Launch Pipeline</span>
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </form>
    </div>
  );
};
