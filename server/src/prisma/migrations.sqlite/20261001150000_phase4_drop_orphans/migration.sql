-- DropIndex
DROP INDEX "DirectorRuntimeCommand_legacyCommandId_key";

-- DropIndex
DROP INDEX "DirectorRuntimeCommand_runtimeId_status_updatedAt_idx";

-- DropIndex
DROP INDEX "DirectorRuntimeCommand_status_priority_runAfter_createdAt_idx";

-- DropIndex
DROP INDEX "DirectorRuntimeCommand_workflowTaskId_status_updatedAt_idx";

-- DropIndex
DROP INDEX "DirectorRuntimeCommand_novelId_status_updatedAt_idx";

-- DropIndex
DROP INDEX "DirectorRuntimeCommand_leaseOwner_leaseExpiresAt_idx";

-- DropIndex
DROP INDEX "DirectorRuntimeCommand_runtimeId_commandType_idempotencyKey_key";

-- DropIndex
DROP INDEX "DirectorRuntimeExecution_activeLockKey_key";

-- DropIndex
DROP INDEX "DirectorRuntimeExecution_runtimeId_status_updatedAt_idx";

-- DropIndex
DROP INDEX "DirectorRuntimeExecution_status_leaseExpiresAt_idx";

-- DropIndex
DROP INDEX "DirectorRuntimeExecution_workflowTaskId_status_updatedAt_idx";

-- DropIndex
DROP INDEX "DirectorRuntimeExecution_novelId_status_updatedAt_idx";

-- DropIndex
DROP INDEX "DirectorRuntimeExecution_workerId_status_updatedAt_idx";

-- DropIndex
DROP INDEX "DirectorRuntimeCheckpoint_runtimeId_createdAt_idx";

-- DropIndex
DROP INDEX "DirectorRuntimeCheckpoint_commandId_idx";

-- DropIndex
DROP INDEX "DirectorRuntimeCheckpoint_executionId_idx";

-- DropIndex
DROP INDEX "DirectorRuntimeCheckpoint_runtimeId_version_key";

-- DropIndex
DROP INDEX "DirectorRuntimeEvent_runtimeId_occurredAt_idx";

-- DropIndex
DROP INDEX "DirectorRuntimeEvent_commandId_occurredAt_idx";

-- DropIndex
DROP INDEX "DirectorRuntimeEvent_executionId_occurredAt_idx";

-- DropIndex
DROP INDEX "DirectorRuntimeEvent_workflowTaskId_occurredAt_idx";

-- DropIndex
DROP INDEX "DirectorRuntimeEvent_novelId_occurredAt_idx";

-- DropIndex
DROP INDEX "DirectorRuntimeEvent_type_occurredAt_idx";

-- DropIndex
DROP INDEX "AutoDirectorFollowUpNotificationLog_taskId_createdAt_idx";

-- DropIndex
DROP INDEX "AutoDirectorFollowUpNotificationLog_eventId_channelType_createdAt_idx";

-- DropIndex
DROP INDEX "DramaSourceBundle_projectId_key";

-- DropIndex
DROP INDEX "DramaEpisode_projectId_status_idx";

-- DropIndex
DROP INDEX "DramaEpisode_projectId_order_key";

-- DropIndex
DROP INDEX "DramaFact_projectId_episodeOrder_idx";

-- DropIndex
DROP INDEX "DramaFact_projectId_category_idx";

-- DropIndex
DROP INDEX "DramaCharacterLibrary_projectId_idx";

-- DropIndex
DROP INDEX "DramaCharacterLibrary_name_idx";

-- DropIndex
DROP INDEX "DramaStoryboard_projectId_idx";

-- DropIndex
DROP INDEX "DramaStoryboard_episodeId_idx";

-- DropIndex
DROP INDEX "DramaVideoPrompt_projectId_idx";

-- DropIndex
DROP INDEX "DramaVideoPrompt_episodeId_idx";

-- DropIndex
DROP INDEX "DramaVideoPrompt_projectId_shotId_version_idx";

-- DropIndex
DROP INDEX "DramaVideoPrompt_provider_status_idx";

-- DropIndex
DROP INDEX "DramaBatchJob_projectId_createdAt_idx";

-- DropIndex
DROP INDEX "DramaBatchJob_episodeId_status_idx";

-- DropIndex
DROP INDEX "DramaBatchJob_type_status_idx";

-- DropIndex
DROP INDEX "ComicSourceBundle_projectId_key";

-- DropIndex
DROP INDEX "ComicEpisode_projectId_status_idx";

-- DropIndex
DROP INDEX "ComicEpisode_projectId_order_key";

-- DropIndex
DROP INDEX "ComicFact_projectId_idx";

-- DropIndex
DROP INDEX "ComicUploadAsset_projectId_kind_idx";

-- DropIndex
DROP INDEX "ComicExportJob_projectId_createdAt_idx";

-- DropIndex
DROP INDEX "ComicExportJob_format_status_idx";

-- DropIndex
DROP INDEX "ComicBatchJob_projectId_createdAt_idx";

-- DropIndex
DROP INDEX "ComicBatchJob_episodeId_status_idx";

-- DropIndex
DROP INDEX "ComicBatchJob_type_status_idx";

-- DropTable
PRAGMA foreign_keys=off;
DROP TABLE "DirectorRuntimeCommand";
PRAGMA foreign_keys=on;

-- DropTable
PRAGMA foreign_keys=off;
DROP TABLE "DirectorRuntimeExecution";
PRAGMA foreign_keys=on;

-- DropTable
PRAGMA foreign_keys=off;
DROP TABLE "DirectorRuntimeCheckpoint";
PRAGMA foreign_keys=on;

-- DropTable
PRAGMA foreign_keys=off;
DROP TABLE "DirectorRuntimeEvent";
PRAGMA foreign_keys=on;

-- DropTable
PRAGMA foreign_keys=off;
DROP TABLE "AutoDirectorFollowUpNotificationLog";
PRAGMA foreign_keys=on;

-- DropTable
PRAGMA foreign_keys=off;
DROP TABLE "DramaSourceBundle";
PRAGMA foreign_keys=on;

-- DropTable
PRAGMA foreign_keys=off;
DROP TABLE "DramaEpisode";
PRAGMA foreign_keys=on;

-- DropTable
PRAGMA foreign_keys=off;
DROP TABLE "DramaFact";
PRAGMA foreign_keys=on;

-- DropTable
PRAGMA foreign_keys=off;
DROP TABLE "DramaCharacterLibrary";
PRAGMA foreign_keys=on;

-- DropTable
PRAGMA foreign_keys=off;
DROP TABLE "DramaStoryboard";
PRAGMA foreign_keys=on;

-- DropTable
PRAGMA foreign_keys=off;
DROP TABLE "DramaVideoPrompt";
PRAGMA foreign_keys=on;

-- DropTable
PRAGMA foreign_keys=off;
DROP TABLE "DramaBatchJob";
PRAGMA foreign_keys=on;

-- DropTable
PRAGMA foreign_keys=off;
DROP TABLE "ComicSourceBundle";
PRAGMA foreign_keys=on;

-- DropTable
PRAGMA foreign_keys=off;
DROP TABLE "ComicEpisode";
PRAGMA foreign_keys=on;

-- DropTable
PRAGMA foreign_keys=off;
DROP TABLE "ComicFact";
PRAGMA foreign_keys=on;

-- DropTable
PRAGMA foreign_keys=off;
DROP TABLE "ComicUploadAsset";
PRAGMA foreign_keys=on;

-- DropTable
PRAGMA foreign_keys=off;
DROP TABLE "ComicExportJob";
PRAGMA foreign_keys=on;

-- DropTable
PRAGMA foreign_keys=off;
DROP TABLE "ComicBatchJob";
PRAGMA foreign_keys=on;

-- RedefineTables
PRAGMA defer_foreign_keys=ON;
PRAGMA foreign_keys=OFF;
CREATE TABLE "new_DramaShot" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "projectId" TEXT NOT NULL,
    "episodeOrder" INTEGER NOT NULL,
    "order" INTEGER NOT NULL,
    "shotSize" TEXT,
    "cameraMove" TEXT,
    "durationSec" INTEGER,
    "location" TEXT,
    "action" TEXT NOT NULL,
    "dialogue" TEXT,
    "characterRefs" TEXT,
    "visualPrompt" TEXT,
    "keyframeData" TEXT,
    "dialogueAudioData" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL
);
INSERT INTO "new_DramaShot" ("action", "cameraMove", "characterRefs", "createdAt", "dialogue", "dialogueAudioData", "durationSec", "id", "keyframeData", "location", "order", "shotSize", "updatedAt", "visualPrompt") SELECT "action", "cameraMove", "characterRefs", "createdAt", "dialogue", "dialogueAudioData", "durationSec", "id", "keyframeData", "location", "order", "shotSize", "updatedAt", "visualPrompt" FROM "DramaShot";
DROP TABLE "DramaShot";
ALTER TABLE "new_DramaShot" RENAME TO "DramaShot";
CREATE INDEX "DramaShot_projectId_idx" ON "DramaShot"("projectId");
CREATE TABLE "new_ComicPanel" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "projectId" TEXT NOT NULL,
    "episodeOrder" INTEGER NOT NULL,
    "order" INTEGER NOT NULL,
    "panelType" TEXT,
    "action" TEXT NOT NULL,
    "dialogues" TEXT,
    "characterRefs" TEXT,
    "sceneRef" TEXT,
    "visualPrompt" TEXT,
    "densityLevel" TEXT,
    "focus" TEXT,
    "layoutData" TEXT,
    "imageData" TEXT,
    "letteredData" TEXT,
    "motionData" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL
);
INSERT INTO "new_ComicPanel" ("action", "characterRefs", "createdAt", "densityLevel", "dialogues", "focus", "id", "imageData", "layoutData", "letteredData", "motionData", "order", "panelType", "sceneRef", "updatedAt", "visualPrompt") SELECT "action", "characterRefs", "createdAt", "densityLevel", "dialogues", "focus", "id", "imageData", "layoutData", "letteredData", "motionData", "order", "panelType", "sceneRef", "updatedAt", "visualPrompt" FROM "ComicPanel";
DROP TABLE "ComicPanel";
ALTER TABLE "new_ComicPanel" RENAME TO "ComicPanel";
CREATE INDEX "ComicPanel_projectId_idx" ON "ComicPanel"("projectId");
PRAGMA foreign_keys=ON;
PRAGMA defer_foreign_keys=OFF;

