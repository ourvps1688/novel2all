import type { ApiResponse } from "@ai-novel/shared/types/api";
import type { DirectorAttentionState } from "@ai-novel/shared/types/directorAttention";
import { apiClient } from "./client";

/**
 * Phase 5-B (T4): client access to the server's normalized director-attention
 * projection. These two endpoints replace the client's need to read
 * `DirectorRuntimeInstance.status` or branch on `checkpointType`.
 */

export async function getDirectorAttentions(): Promise<DirectorAttentionState[]> {
  const { data } = await apiClient.get<ApiResponse<{ attentions: DirectorAttentionState[] }>>(
    "/director-attentions",
  );
  return data.data?.attentions ?? [];
}

export async function getDirectorAttention(novelId: string): Promise<DirectorAttentionState | null> {
  try {
    const { data } = await apiClient.get<ApiResponse<{ attention: DirectorAttentionState }>>(
      `/director-attentions/${encodeURIComponent(novelId)}`,
      // A missing novel is an expected, non-error result — suppress the toast.
      { silentErrorStatuses: [404] },
    );
    return data.data?.attention ?? null;
  } catch (error) {
    if (error instanceof Error && (error as { status?: number }).status === 404) {
      return null;
    }
    throw error;
  }
}
