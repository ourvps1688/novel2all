import { useQuery } from "@tanstack/react-query";
import { getDirectorAttention, getDirectorAttentions } from "@/api/directorAttention";
import { queryKeys } from "@/api/queryKeys";

export interface UseDirectorAttentionsOptions {
  enabled?: boolean;
}

/** Aggregate: every non-idle novel the director needs attention for (T5 badge). */
export function useDirectorAttentions(options: UseDirectorAttentionsOptions = {}) {
  return useQuery({
    queryKey: queryKeys.directorAttentions.all,
    queryFn: () => getDirectorAttentions(),
    enabled: options.enabled ?? true,
    staleTime: 10_000,
    refetchInterval: (query) => (query.state.data && query.state.data.length > 0 ? 8000 : false),
  });
}

/** Single novel attention state (T6 banner). */
export function useDirectorAttention(
  novelId: string | null | undefined,
  options: UseDirectorAttentionsOptions = {},
) {
  const enabled = Boolean(novelId) && (options.enabled ?? true);
  return useQuery({
    queryKey: queryKeys.directorAttentions.detail(novelId ?? "none"),
    queryFn: () => getDirectorAttention(novelId as string),
    enabled,
    retry: false,
    staleTime: 10_000,
    refetchInterval: (query) => {
      const level = query.state.data?.level;
      return level === "running" || level === "auto_recovering" || level === "waiting_approval"
        ? 4000
        : false;
    },
  });
}
