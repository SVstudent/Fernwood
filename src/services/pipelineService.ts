/**
 * Fernwood AI Pipeline Service & Integrations Layer
 *
 * This module is now a thin client over the Python (Genblaze) backend. The
 * previous simulated generation/critique/storage placeholders are gone:
 *
 *  - `generateAssetViaGenblaze()` -> real Genblaze Pipeline steps using a custom
 *      TokenRouterImageProvider (image) and ElevenLabsTTSProvider (audio)
 *  - `critiqueAssetViaLLM()`      -> real vision/text critique via TokenRouter
 *  - `saveToB2()` / `fetchFromB2()` -> real ObjectStorageSink + campaign index
 *
 * All of that runs server-side, because Genblaze is a Python SDK and because
 * the TokenRouter / ElevenLabs / B2 credentials must never reach the browser.
 * Progress arrives over Server-Sent Events carrying the exact `PipelineStageLog`
 * and `Campaign` shapes declared in ../types, so no component had to change.
 */

import {
  BrainSnapshot,
  BrainState,
  Campaign,
  CampaignBrief,
  ImprovementDelta,
  PipelineStageLog,
} from '../types';

// Empty string -> same-origin, proxied to the backend by vite.config.ts.
// Set VITE_API_BASE (e.g. http://127.0.0.1:8787) to bypass the dev proxy
// entirely if SSE ever misbehaves through it.
const API_BASE: string = (import.meta as any).env?.VITE_API_BASE ?? '';

export type OnLogCallback = (log: PipelineStageLog) => void;
export type OnCampaignUpdateCallback = (campaign: Campaign) => void;
export type OnBrainUpdateCallback = (snapshot: BrainSnapshot) => void;

export class PipelineError extends Error {}

/**
 * Start a campaign run and stream its progress.
 *
 * Signature is unchanged from the mock so App.tsx did not need restructuring.
 * The run is started with a POST (which returns immediately) and consumed via a
 * separate EventSource GET — a run takes minutes, EventSource cannot issue a
 * POST, and a GET stream is re-openable if the tab reloads mid-run.
 */
export async function executeFullCampaignPipeline(
  brief: CampaignBrief,
  onLog: OnLogCallback,
  onCampaignUpdate: OnCampaignUpdateCallback,
  onBrainUpdate?: OnBrainUpdateCallback
): Promise<Campaign> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/campaigns`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(brief),
    });
  } catch {
    throw new PipelineError(
      'Could not reach the Fernwood backend. Start it with: cd backend && uv run uvicorn app.main:app --port 8787'
    );
  }

  if (!res.ok) {
    throw new PipelineError(`Failed to start pipeline (HTTP ${res.status}).`);
  }

  const { campaignId, campaign } = await res.json();
  if (campaign) onCampaignUpdate(campaign as Campaign);

  return new Promise<Campaign>((resolve, reject) => {
    let lastSeq = -1;
    let settled = false;

    const es = new EventSource(
      `${API_BASE}/api/campaigns/${campaignId}/stream?from=${lastSeq}`
    );

    const finish = (fn: () => void) => {
      settled = true;
      es.close();
      fn();
    };

    es.addEventListener('log', (e) => {
      const ev = e as MessageEvent;
      if (ev.lastEventId) lastSeq = Number(ev.lastEventId);
      onLog(JSON.parse(ev.data) as PipelineStageLog);
    });

    es.addEventListener('campaign', (e) => {
      const ev = e as MessageEvent;
      if (ev.lastEventId) lastSeq = Number(ev.lastEventId);
      onCampaignUpdate(JSON.parse(ev.data) as Campaign);
    });

    // The Campaign Brain streams its whole snapshot on its own event name, not
    // as another log frame: the lobe graph needs complete state on every tick,
    // while the log is an append-only feed. Unknown event names are ignored by
    // EventSource, so a backend without the brain simply never fires this.
    es.addEventListener('brain', (e) => {
      const ev = e as MessageEvent;
      if (ev.lastEventId) lastSeq = Number(ev.lastEventId);
      onBrainUpdate?.(JSON.parse(ev.data) as BrainSnapshot);
    });

    es.addEventListener('done', (e) => {
      const { campaign: finalCampaign } = JSON.parse((e as MessageEvent).data);
      finish(() => {
        onCampaignUpdate(finalCampaign as Campaign);
        resolve(finalCampaign as Campaign);
      });
    });

    // A *named* 'error' event carries .data and means the server reported a
    // fatal run failure. Transport errors arrive on es.onerror without .data.
    es.addEventListener('error', (e) => {
      const data = (e as MessageEvent).data;
      if (!data) return;
      const { message } = JSON.parse(data);
      finish(() => reject(new PipelineError(message ?? 'Pipeline failed.')));
    });

    es.onerror = () => {
      if (settled) return;
      // readyState CONNECTING means EventSource is auto-reconnecting and will
      // resume from Last-Event-ID — let it. Only CLOSED is terminal.
      if (es.readyState === EventSource.CLOSED) {
        finish(() =>
          reject(new PipelineError('Connection to the pipeline stream was lost.'))
        );
      }
    };
  });
}

/**
 * Load the campaign library from storage (Backblaze B2, or local disk in dev).
 * Returns null when storage is unreachable so the caller can fall back to the
 * preseeded sample campaigns rather than showing an empty gallery.
 */
export async function listCampaigns(): Promise<Campaign[] | null> {
  try {
    const res = await fetch(`${API_BASE}/api/campaigns`);
    if (!res.ok) return null;
    const { campaigns, source } = await res.json();
    if (source === 'unavailable') return null;
    return (campaigns ?? []) as Campaign[];
  } catch {
    return null;
  }
}

/** Delete a campaign from the library index. Best-effort. */
export async function deleteCampaignRemote(campaignId: string): Promise<void> {
  try {
    await fetch(`${API_BASE}/api/campaigns/${campaignId}`, { method: 'DELETE' });
  } catch {
    /* local state is updated regardless */
  }
}

export interface BrainResponse {
  brain: BrainState;
  improvement: ImprovementDelta;
  model: string;
  slug?: string;
}

/**
 * Load a brand's persistent brain.
 *
 * Keyed by brand NAME rather than slug so a caller only needs what it already
 * has from the campaign; the backend slugifies. Returns 200 with an empty brain
 * for an unknown brand — a cold start is the normal first case, not an error.
 */
export async function fetchBrainByBrand(brandName: string): Promise<BrainResponse | null> {
  try {
    const res = await fetch(`${API_BASE}/api/brain/by-brand/${encodeURIComponent(brandName)}`);
    return res.ok ? ((await res.json()) as BrainResponse) : null;
  } catch {
    return null;
  }
}

/** Every brand brain in storage, newest first. */
export async function fetchBrains(): Promise<BrainState[]> {
  try {
    const res = await fetch(`${API_BASE}/api/brains`);
    if (!res.ok) return [];
    const { brains } = await res.json();
    return (brains ?? []) as BrainState[];
  } catch {
    return [];
  }
}

/**
 * Wipe a brand's learned memory so the next run is a true cold start.
 * Exists for the cold-vs-warm demo; versioned snapshots in storage survive.
 */
export async function resetBrain(slug: string): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/brain/${encodeURIComponent(slug)}`, {
      method: 'DELETE',
    });
    return res.ok;
  } catch {
    return false;
  }
}

export interface BackendHealth {
  ok: boolean;
  storage: { mode: string; bucket: string; b2Configured: boolean };
  tokenrouter: { configured: boolean; reachable: boolean; imageModel: string };
  elevenlabs: { configured: boolean; enabled: boolean };
  warnings: string[];
}

export async function fetchHealth(): Promise<BackendHealth | null> {
  try {
    const res = await fetch(`${API_BASE}/api/health`);
    return res.ok ? ((await res.json()) as BackendHealth) : null;
  } catch {
    return null;
  }
}
