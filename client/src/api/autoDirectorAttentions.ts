import type { ApiResponse } from "@ai-novel/shared/types/api";
import type {
  AutoDirectorActionExecutionResult,
  AutoDirectorAttentionDetail,
  AutoDirectorAttentionListInput,
  AutoDirectorAttentionListResponse,
  AutoDirectorMutationActionCode,
} from "@ai-novel/shared/types/autoDirectorAttention";
import type { ApiHttpError } from "./client";
import { apiClient } from "./client";

export async function listAutoDirectorAttentions(params?: AutoDirectorAttentionListInput) {
  const { data } = await apiClient.get<ApiResponse<AutoDirectorAttentionListResponse>>("/auto-director/attentions", {
    params,
  });
  return data;
}

export async function getAutoDirectorAttentionDetail(directorTaskId: string) {
  try {
    const { data } = await apiClient.get<ApiResponse<AutoDirectorAttentionDetail | null>>(
      `/auto-director/attentions/${directorTaskId}`,
      {
        silentErrorStatuses: [404],
      },
    );
    return data;
  } catch (error) {
    const httpError = error as ApiHttpError;
    if (httpError.status === 404) {
      return {
        success: true,
        data: null,
        message: "Follow-up not found.",
      } satisfies ApiResponse<AutoDirectorAttentionDetail | null>;
    }
    throw error;
  }
}

export async function executeAutoDirectorAttentionAction(
  directorTaskId: string,
  input: {
    actionCode: AutoDirectorMutationActionCode;
    idempotencyKey: string;
  },
) {
  const { data } = await apiClient.post<ApiResponse<AutoDirectorActionExecutionResult>>(
    `/auto-director/attentions/${directorTaskId}/actions`,
    input,
  );
  return data;
}
