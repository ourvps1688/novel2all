import {
  NOVEL_PROMPT_BUDGETS,
  resolveVolumeStrategyOutputTokenBudget,
} from "../../../../prompting/prompts/novel/promptBudgetProfiles";
import type {
  AutopilotBookBudgetSummary,
  AutopilotStageBudget,
} from "@ai-novel/shared/types/autopilotBookBudget";

export interface ComputeAutopilotBookBudgetInput {
  modelId?: string;
  expectedVolumes?: number;
  expectedChaptersPerVolume?: number;
  concurrency?: number;
  assumedPerCallSeconds?: number;
}

interface ModelPrice {
  inputPerMillion: number;
  outputPerMillion: number;
  currency: "CNY" | "USD";
}

/**
 * 纯估算单价表。价格为明显标注为“估算”的参考值，实际以各供应商账单为准。
 * 仅用于在全本自动驾驶建书时给出一个量级参考，绝不影响运行决策。
 */
export const MODEL_PRICE_TABLE: Record<string, ModelPrice> = {
  "deepseek-chat": { inputPerMillion: 1, outputPerMillion: 2, currency: "CNY" },
  "qwen-max": { inputPerMillion: 1.2, outputPerMillion: 4.8, currency: "CNY" },
  "gpt-4o-mini": { inputPerMillion: 0.15, outputPerMillion: 0.6, currency: "USD" },
  "gpt-4o": { inputPerMillion: 2.5, outputPerMillion: 10, currency: "USD" },
  "claude-3-5-sonnet": { inputPerMillion: 3, outputPerMillion: 15, currency: "USD" },
};

const FX_TO_CNY = { CNY: 1, USD: 7.2 } as const;

/**
 * 计算一次全本自动驾驶建书的 token / 费用 / 时长估算摘要。
 * 纯函数、确定性：除时间戳外不含随机性，相同输入必产生相同输出。
 */
export function computeAutopilotBookBudget(input: ComputeAutopilotBookBudgetInput = {}): AutopilotBookBudgetSummary {
  const V = Math.max(0, input.expectedVolumes ?? 3);
  const C = Math.max(0, input.expectedChaptersPerVolume ?? 15);
  const concurrency = Math.max(1, input.concurrency ?? 1);
  const perCall = Math.max(1, input.assumedPerCallSeconds ?? 20);

  // 退化的边界情况：预期卷数为 0 意味着没有任何可规划/生成的内容，整体预算归零。
  const zeroBook = V === 0;

  const stages: AutopilotStageBudget[] = [];
  const add = (
    stage: string,
    label: string,
    calls: number,
    inputPerCall: number,
    outputPerCall: number,
  ) => {
    const effectiveCalls = zeroBook ? 0 : calls;
    stages.push({
      stage,
      label,
      calls: effectiveCalls,
      inputTokens: effectiveCalls * inputPerCall,
      outputTokens: effectiveCalls * outputPerCall,
      estimatedSeconds: Math.ceil((effectiveCalls * perCall) / concurrency),
    });
  };

  add("candidate_selection", "确认书级方向", 1, 1200, 600);
  add("story_macro", "故事宏观拆解", 2, NOVEL_PROMPT_BUDGETS.storyMacroDecomposition, 1200);
  add("book_contract", "书级契约", 1, NOVEL_PROMPT_BUDGETS.directorBookContract, 1400);
  add("world_setup", "世界观搭建", 2, 2000, 2000);
  add("character_setup", "角色设定", 2, 2200, 1800);

  const vsCalls = 2 * V;
  const vsOutPerCall = Math.round(resolveVolumeStrategyOutputTokenBudget(V) / Math.max(1, vsCalls));
  add("volume_strategy", "分卷策略", vsCalls, NOVEL_PROMPT_BUDGETS.volumeStrategy, vsOutPerCall);

  const soCalls = V * (2 + C);
  add("structured_outline", "结构化大纲", soCalls, NOVEL_PROMPT_BUDGETS.volumeBeatSheet, 1600);

  const ceCalls = 3 * V * C;
  add("chapter_execution", "逐章执行", ceCalls, NOVEL_PROMPT_BUDGETS.chapterWriter, 3750);

  const totals = {
    calls: 0,
    inputTokens: 0,
    outputTokens: 0,
    estimatedSeconds: 0,
  };
  for (const stage of stages) {
    totals.calls += stage.calls;
    totals.inputTokens += stage.inputTokens;
    totals.outputTokens += stage.outputTokens;
    totals.estimatedSeconds += stage.estimatedSeconds;
  }

  const costByModel: Record<string, number> = {};
  for (const [modelId, price] of Object.entries(MODEL_PRICE_TABLE)) {
    const fx = FX_TO_CNY[price.currency];
    const costCny =
      (totals.inputTokens * price.inputPerMillion) / 1e6 +
      (totals.outputTokens * price.outputPerMillion) / 1e6;
    costByModel[modelId] = Math.round(costCny * fx * 100) / 100;
  }

  const primaryModelId =
    input.modelId && MODEL_PRICE_TABLE[input.modelId]
      ? input.modelId
      : Object.keys(MODEL_PRICE_TABLE)[0];

  return {
    generatedAt: new Date().toISOString(),
    currency: "CNY",
    expectedVolumes: V,
    expectedChapters: V * C,
    stages,
    totals,
    costByModel,
    primaryModelId,
    note: "本摘要为基于默认规模与模型单价的估算值，实际消耗以运行为准；可忽略，不影响全自动流程。",
  };
}
