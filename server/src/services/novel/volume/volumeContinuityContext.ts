import type {
  CrossVolumeContinuityPackage,
  VolumePlan,
  VolumePlanDocument,
} from "@ai-novel/shared/types/novel";
import { prisma } from "../../../db/prisma";
import { listActiveVolumeRows } from "./volumeWorkspacePersistence";
import { parseJsonStringArraySafe } from "../runtime/runtimeContextBlocks";

/**
 * Build a consolidated cross-volume continuity package for planning a new
 * volume's chapter list.
 *
 * Two data paths:
 *  - In-memory (`document` provided, no `db`): volume arcs are derived from the
 *    planning document's prior volumes. No database hit is performed, which keeps
 *    whole-book planning free of I/O. Character / payoff / world-rule / fact
 *    enrichment stays empty in this path because the in-memory document only
 *    carries VolumePlan fields.
 *  - JIT / DB (`document` omitted): prior volumes are loaded from the database
 *    via the shared volume-workspace reader, and character / payoff / bible /
 *    consistency-fact data is loaded on the fly.
 *
 * If a `db` client is explicitly supplied it is reused (never a new connection)
 * for the enrichment queries even when `document` is present.
 */
export async function buildCrossVolumeContinuityPackage(params: {
  novelId: string;
  targetVolumeSortOrder: number;
  document?: VolumePlanDocument;
  db?: any;
}): Promise<CrossVolumeContinuityPackage> {
  const { novelId, targetVolumeSortOrder, document, db } = params;

  let priorVolumes: VolumePlan[] = [];
  let useDbEnrichment = false;

  if (document) {
    priorVolumes = document.volumes.filter((volume) => volume.sortOrder < targetVolumeSortOrder);
    if (db) {
      useDbEnrichment = true;
    }
  } else {
    const dbClient = db ?? prisma;
    const allVolumes = await listActiveVolumeRows(novelId, dbClient);
    priorVolumes = allVolumes.filter((volume) => volume.sortOrder < targetVolumeSortOrder);
    useDbEnrichment = true;
  }

  const volumeArc = priorVolumes.map((volume) => ({
    sortOrder: volume.sortOrder,
    title: volume.title,
    summary: volume.summary ?? null,
    climax: volume.climax ?? null,
    protagonistChange: volume.protagonistChange ?? null,
    nextVolumeHook: volume.nextVolumeHook ?? null,
    resetPoint: volume.resetPoint ?? null,
    openPayoffs: normalizeOpenPayoffs((volume as { openPayoffs?: unknown }).openPayoffs),
  }));

  const base: CrossVolumeContinuityPackage = {
    targetVolumeSortOrder,
    priorVolumeCount: priorVolumes.length,
    volumeArc,
    characterStates: [],
    pendingPayoffs: [],
    worldRules: null,
    consistencyFacts: [],
    priorChapterSummaries: [],
  };

  if (!useDbEnrichment) {
    return base;
  }

  const dbClient = db ?? prisma;
  try {
    const [characters, snapshots, payoffs, bible, facts] = await Promise.all([
      dbClient.character.findMany({ where: { novelId } }),
      dbClient.characterMindSnapshot.findMany({ where: { novelId, isCurrent: true } }),
      dbClient.payoffLedgerItem.findMany({ where: { novelId } }),
      dbClient.novelBible.findFirst({ where: { novelId } }),
      dbClient.consistencyFact.findMany({ where: { novelId } }),
    ]);

    const snapshotByCharacter = new Map<string, any>();
    for (const snapshot of snapshots ?? []) {
      snapshotByCharacter.set(snapshot.characterId, snapshot);
    }

    base.characterStates = (characters ?? [])
      .map((character: any) => ({
        name: character.name,
        role: character.role,
        currentState: character.currentState ?? null,
        currentGoal: character.currentGoal ?? null,
        mindSnapshot: snapshotByCharacter.get(character.id)?.currentInterpretation ?? null,
      }))
      .slice(0, 8);

    base.pendingPayoffs = (payoffs ?? [])
      .filter((payoff: any) => payoff.scopeType === "book" || payoff.scopeType === "volume")
      .map((payoff: any) => ({
        ledgerKey: payoff.ledgerKey,
        title: payoff.title,
        summary: payoff.summary,
        scopeType: payoff.scopeType,
        status: payoff.currentStatus,
      }));

    base.worldRules = (bible as any)?.worldRules ?? null;

    base.consistencyFacts = (facts ?? [])
      .map((fact: any) => `[${fact.category}] ${fact.content}`)
      .slice(0, 12);

    const lastChapterIds = priorVolumes
      .map((volume) => {
        const sorted = [...volume.chapters].sort((left, right) => left.chapterOrder - right.chapterOrder);
        return sorted.length > 0 ? sorted[sorted.length - 1].id : null;
      })
      .filter((id): id is string => Boolean(id));

    if (lastChapterIds.length > 0) {
      const summaries = await dbClient.chapterSummary.findMany({
        where: { chapterId: { in: lastChapterIds } },
      });
      base.priorChapterSummaries = (summaries ?? [])
        .map((summary: any) => summary.summary)
        .filter((text: unknown) => typeof text === "string" && text.trim().length > 0);
    }
  } catch {
    // Enrichment is best-effort; fall back to the VolumePlan-derived package.
  }

  return base;
}

function normalizeOpenPayoffs(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item ?? "").trim()).filter(Boolean);
  }
  if (typeof value === "string" && value.trim().length > 0) {
    return parseJsonStringArraySafe(value);
  }
  return [];
}
