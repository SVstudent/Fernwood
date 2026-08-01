/**
 * Fernwood Core Data Types & Pipeline Models
 * MVP Scaffold with placeholder types for Backblaze B2 & Genblaze pipeline integrations.
 */

export type ToneMood =
  | 'Cozy & Warm'
  | 'Playful & Bold'
  | 'Minimalist Luxury'
  | 'High-Tech Futuristic'
  | 'Earthy & Organic'
  | 'Energetic Athletic'
  | 'Professional & Authoritative';

export interface ColorPreference {
  primary: string;
  secondary: string;
  accent: string;
}

export interface CritiqueCriterion {
  name: string;
  score: number; // 0 to 100
  targetScore: number;
  passed: boolean;
  feedback: string;
}

export interface CritiqueResult {
  passed: boolean;
  overallScore: number;
  criteria: CritiqueCriterion[];
  reasoning: string;
  suggestedFixes: string;
}

export interface AttemptContent {
  // For Image
  imageUrl?: string;
  svgData?: string;
  aspectRatio?: string;
  
  // For Audio
  audioScript?: string;
  audioVoice?: string;
  durationSeconds?: number;
  audioWaveformData?: number[];
  audioUrl?: string; // real ElevenLabs mp3, served from B2 via /api/media
  
  // For Marketing Copy
  headline?: string;
  subheadline?: string;
  bodyText?: string;
  callToAction?: string;
  socialPosts?: string[];
  keyBenefitBullets?: string[];
  
  // Style / Palette metadata
  primaryColor?: string;
  secondaryColor?: string;
  accentColor?: string;

  // Genblaze provenance for this attempt (SHA-256 canonical manifest hash and
  // the manifest's location in B2). Present for real generations only.
  manifestHash?: string;
  manifestUri?: string;
}

export interface Attempt {
  id: string;
  attemptNumber: number;
  providerName: string; // e.g. "Genblaze Visual Engine", "Genblaze Voice Synthesis", "Genblaze LLM"
  modelName: string;    // e.g. "genblaze-image-v3", "genblaze-tts-pro", "gemini-2.5-flash"
  promptUsed: string;
  timestamp: string;
  critiqueVerdict: 'PASS' | 'FAIL';
  critique: CritiqueResult;
  content: AttemptContent;
}

export type AssetType = 'image' | 'audio' | 'copy';

export interface Asset {
  id: string;
  campaignId: string;
  type: AssetType;
  attempts: Attempt[];
  finalApprovedAttemptId: string | null;
  status: 'pending' | 'in_progress' | 'passed' | 'failed';
}

export interface CampaignBrief {
  brandName: string;
  productService: string;
  targetAudience: string;
  briefText: string;
  toneTags: string[];
  colors: ColorPreference;
}

export interface Campaign {
  id: string;
  brandName: string;
  productService: string;
  targetAudience: string;
  briefText: string;
  toneTags: string[];
  colors: ColorPreference;
  createdAt: string;
  updatedAt: string;
  status: 'draft' | 'running' | 'completed' | 'failed';
  assets: {
    image?: Asset;
    audio?: Asset;
    copy?: Asset;
  };
  overallQualityScore: number;
  totalAttemptsCount: number;
  retryCount: number;
}

export type PipelineStageId =
  | 'brief_analysis'
  | 'image_gen'
  | 'image_critique'
  | 'audio_gen'
  | 'audio_critique'
  | 'copy_gen'
  | 'copy_critique'
  | 'assembly'
  | 'b2_upload';

export interface PipelineStageLog {
  id: string;
  stage: PipelineStageId;
  type: 'info' | 'success' | 'warning' | 'error' | 'attempt';
  title: string;
  message: string;
  timestamp: string;
  attemptDetails?: Attempt;
  assetType?: AssetType;
}

export interface PipelineState {
  campaignId: string | null;
  currentStage: PipelineStageId | null;
  progressPercent: number;
  isRunning: boolean;
  isPaused: boolean;
  logs: PipelineStageLog[];
  activeAttempts: {
    image?: Attempt;
    audio?: Attempt;
    copy?: Attempt;
  };
  currentAttemptCounts: {
    image: number;
    audio: number;
    copy: number;
  };
}
