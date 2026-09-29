import type { WorldLayerKey, WorldStructureSectionKey } from "@ai-novel/shared/types/world";

export interface WorldVisualizationPromptInput {
  worldPromptSource: string;
}

export interface WorldStructureBackfillPromptInput {
  promptSource: string;
}

export interface NovelThemeWorldGenerationPromptInput {
  novelTitle: string;
  description: string;
  targetAudience: string;
  bookSellingPoint: string;
  first30ChapterPromise: string;
  commercialTags: string[];
  genreName: string;
  primaryStoryModeName: string;
  secondaryStoryModeName: string;
  storyMacroContext?: string;
  bookContractContext?: string;
  openingOnly?: boolean;
}

export interface WorldStructureSectionPromptInput {
  section: WorldStructureSectionKey;
  promptSource: string;
  currentStructure: unknown;
  currentBindingSupport: unknown;
}

export interface WorldAxiomSuggestionPromptInput {
  worldName: string;
  worldType: string;
  templateName: string;
  templateDescription: string;
  description: string;
  blueprintPromptBlock: string;
}

export interface WorldDeepeningQuestionsPromptInput {
  worldName: string;
  description: string;
  dataJson: string;
  ragContext: string;
}

export interface WorldConsistencyPromptInput {
  worldName: string;
  axioms: string;
  coreSettingsJson: string;
  ragContext: string;
}

export interface WorldLayerGenerationPromptInput {
  layerKey: WorldLayerKey;
  targetFields: string[];
  worldName: string;
  worldType: string;
  templateName: string;
  templateDescription: string;
  classicElements: string[];
  pitfalls: string[];
  axioms: string;
  summary: string;
  blueprintPromptBlock: string;
  existingJson: string;
  ragContext: string;
}

export interface WorldLayerLocalizationPromptInput {
  layerKey: WorldLayerKey;
  layerFields: string[];
  sourcePayloadJson: string;
}

export interface WorldImportExtractionPromptInput {
  content: string;
}
