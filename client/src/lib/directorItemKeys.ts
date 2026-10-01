// Shared item-key groupings used by both the director progress panel and the
// workspace navigation resolver. Kept in one place so the two views cannot drift
// apart (S3 redundant-logic convergence).

export const CHAPTER_EXECUTION_ITEM_KEYS: readonly string[] = [
  "chapter_execution",
  "chapter_execution_node",
  "chapter.draft.write",
  "chapter.write",
];

export const QUALITY_REPAIR_ITEM_KEYS: readonly string[] = [
  "reviewing",
  "repairing",
  "quality_repair",
  "chapter_quality_review_node",
  "chapter.quality.review",
  "chapter_state_commit_node",
  "chapter.state.commit",
];
