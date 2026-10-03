export interface AutopilotStageBudget {
  stage: string;
  label: string;
  calls: number;
  inputTokens: number;
  outputTokens: number;
  estimatedSeconds: number;
}

export interface AutopilotBookBudgetSummary {
  generatedAt: string;
  currency: string;
  expectedVolumes: number;
  expectedChapters: number;
  stages: AutopilotStageBudget[];
  totals: {
    calls: number;
    inputTokens: number;
    outputTokens: number;
    estimatedSeconds: number;
  };
  costByModel: Record<string, number>;
  primaryModelId: string;
  note: string;
}
