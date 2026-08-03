/**
 * Fernwood Core Data Types & Pipeline Models
 *
 * This file is the wire contract between the React app and the Python
 * (Genblaze) backend. The backend serializes these exact camelCase shapes over
 * /api and SSE — see backend/app/domain/models.py, which mirrors them field for
 * field. Changing a type here means changing that file too.
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
  /**
   * The score the critic actually returned, before FERNWOOD_FORCE_FIRST_RETRY
   * capped it to guarantee a visible retry. Present only when that cap fired.
   * The Campaign Brain's improvement metric prefers this over overallScore.
   */
  preCapScore?: number;
}

/* ------------------------------------------------------------------------ *
 * Campaign Brain
 *
 * Per-brand persistent intelligence. Mirrors backend/app/brain/models.py field
 * for field — that file is the other half of this contract.
 * ------------------------------------------------------------------------ */

export type LawCategory = 'visual' | 'voice' | 'copy' | 'audience' | 'strategy';
export type LobeId = 'recall' | 'strategy' | 'foresight' | 'audience' | 'learning';
export type LobeStatus = 'idle' | 'firing' | 'done' | 'skipped';

/** One durable rule this brand's own rejected work taught the brain. */
export interface BrandLaw {
  id: string;
  text: string;
  category: LawCategory;
  source: 'critique' | 'audience' | 'seed';
  confidence: number;
  /** The critique or objection that produced it. A law is a citation, not an opinion. */
  evidence: string;
  learnedFromCampaignId: string;
  learnedFromAttemptId?: string;
  learnedAt: string;
  /** Bumped when a later campaign independently rediscovers the same lesson. */
  reinforcedCount: number;
}

export interface Persona {
  id: string;
  name: string;
  age: number;
  occupation: string;
  location: string;
  mindset: string;
  skepticism: number;
  mediaDiet: string;
}

export interface PersonaReaction {
  personaId: string;
  personaName: string;
  sentiment: number;
  verdict: 'loves' | 'likes' | 'indifferent' | 'dislikes';
  /** What this person would actually say to a friend about the ad. */
  quote: string;
  objection: string;
  wouldAct: number;
  attentionSeconds: number;
}

export interface AudienceReport {
  personas: Persona[];
  reactions: PersonaReaction[];
  resonanceScore: number;
  consensus: string;
  topObjection: string;
  /** Population std-dev of sentiment: is the panel split, or merely lukewarm? */
  polarization: number;
  /** On-the-record statement of what the panel actually read. */
  basis: string;
}

export interface CampaignStrategy {
  bigIdea: string;
  positioning: string;
  visualDirection: string;
  voiceDirection: string;
  copyAngle: string;
  avoid: string[];
  lawsApplied: string[];
}

export interface Foresight {
  predictedScore: number;
  predictedRetries: number;
  likelyFailureMode: string;
  confidence: number;
  rationale: string;
  actualScore?: number;
  actualRetries?: number;
  calibrationError?: number;
}

export interface LearningDelta {
  lawsAdded: BrandLaw[];
  lawsReinforced: string[];
  summary: string;
  versionBefore: number;
  versionAfter: number;
}

export interface RunRecord {
  campaignId: string;
  brandName: string;
  createdAt: string;
  brainVersionAtRun: number;
  lawsAvailable: number;
  totalAttempts: number;
  retryCount: number;
  /** The headline learning signal: how good the opening shot was, pre-critique. */
  firstAttemptAvgScore: number;
  finalQualityScore: number;
  resonanceScore?: number;
  predictedScore?: number;
  calibrationError?: number;
  forcedFirstRetry: boolean;
}

export interface ImprovementDelta {
  hasBaseline: boolean;
  runs: number;
  baseline?: RunRecord;
  latest?: RunRecord;
  firstAttemptScoreDelta: number;
  /** Negative is better — fewer retries to reach shippable work. */
  retryDelta: number;
  qualityDelta: number;
  resonanceDelta?: number;
  lawsDelta: number;
  summary: string;
  /** Set when the two compared runs were not measured under equal conditions. */
  caveat: string;
}

/** The persistent brain for one brand. brains/{slug}/brain.json in B2. */
export interface BrainState {
  brandSlug: string;
  brandName: string;
  version: number;
  createdAt: string;
  updatedAt: string;
  laws: BrandLaw[];
  personas: Persona[];
  history: RunRecord[];
  lifetimeCampaigns: number;
}

/** What one campaign's brain knew, decided and learned. Embedded in campaign.json. */
export interface BrainSnapshot {
  brandSlug: string;
  brandName: string;
  coldStart: boolean;
  brainVersionBefore: number;
  brainVersionAfter: number;
  lawsApplied: BrandLaw[];
  strategy?: CampaignStrategy;
  foresight?: Foresight;
  audience?: AudienceReport;
  learning?: LearningDelta;
  improvement?: ImprovementDelta;
  lobes: Record<string, LobeStatus>;
  /** Manifest hash per lobe — the brain's own reasoning is provenance-tracked. */
  lobeManifests: Record<string, string>;
  modelUsed: string;
}

export type ShotRole = 'hook' | 'product' | 'benefit' | 'cta';

/**
 * One shot of the assembled advertisement.
 *
 * A shot is not a re-crop of the key visual: it has its own generated first
 * frame, its own camera move and its own line of narration, so the finished
 * film cuts between real scenes the way an ad does.
 */
export interface AdShot {
  index: number;
  role: ShotRole;
  title: string;
  scenePrompt: string;
  motionPrompt: string;
  durationSeconds: number;
  voiceoverLine?: string;
  frameUrl?: string;
  clipUrl?: string;
  manifestHash?: string;
  status: 'pending' | 'rendered' | 'failed';
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

  // For Video (a cut advertisement, not a single still in motion)
  videoUrl?: string;
  videoPosterUrl?: string;
  videoDurationSeconds?: number;
  /** Full shot breakdown of the assembled advertisement. */
  adShots?: AdShot[];
  shotCount?: number;
  hasVoiceover?: boolean;
  hasEndCard?: boolean;
  
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

export type AssetType = 'image' | 'audio' | 'copy' | 'video';

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
  /** Opt-in: adds a generated brand film (~2 min extra per campaign). */
  includeVideo?: boolean;
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
    video?: Asset;
  };
  /**
   * Deliverables with the SHA-256 provenance manifest embedded in the file
   * itself (asset kind -> /api/media URL). Extractable and verifiable without
   * B2 or this service.
   */
  delivery?: Record<string, string>;
  overallQualityScore: number;
  totalAttemptsCount: number;
  retryCount: number;
  /** What this brand's Campaign Brain knew, decided and learned on this run. */
  brain?: BrainSnapshot;
}

export type PipelineStageId =
  | 'brief_analysis'
  | 'image_gen'
  | 'image_critique'
  | 'audio_gen'
  | 'audio_critique'
  | 'copy_gen'
  | 'copy_critique'
  | 'video_gen'
  | 'video_critique'
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
