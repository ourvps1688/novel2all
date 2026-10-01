-- DropForeignKey
ALTER TABLE "DirectorRuntimeCommand" DROP CONSTRAINT "DirectorRuntimeCommand_runtimeId_fkey";

-- DropForeignKey
ALTER TABLE "DirectorRuntimeExecution" DROP CONSTRAINT "DirectorRuntimeExecution_runtimeId_fkey";

-- DropForeignKey
ALTER TABLE "DirectorRuntimeExecution" DROP CONSTRAINT "DirectorRuntimeExecution_commandId_fkey";

-- DropForeignKey
ALTER TABLE "DirectorRuntimeCheckpoint" DROP CONSTRAINT "DirectorRuntimeCheckpoint_runtimeId_fkey";

-- DropForeignKey
ALTER TABLE "DirectorRuntimeCheckpoint" DROP CONSTRAINT "DirectorRuntimeCheckpoint_commandId_fkey";

-- DropForeignKey
ALTER TABLE "DirectorRuntimeCheckpoint" DROP CONSTRAINT "DirectorRuntimeCheckpoint_executionId_fkey";

-- DropForeignKey
ALTER TABLE "DirectorRuntimeEvent" DROP CONSTRAINT "DirectorRuntimeEvent_runtimeId_fkey";

-- DropForeignKey
ALTER TABLE "DirectorRuntimeEvent" DROP CONSTRAINT "DirectorRuntimeEvent_commandId_fkey";

-- DropForeignKey
ALTER TABLE "DirectorRuntimeEvent" DROP CONSTRAINT "DirectorRuntimeEvent_executionId_fkey";

-- DropForeignKey
ALTER TABLE "DramaSourceBundle" DROP CONSTRAINT "DramaSourceBundle_projectId_fkey";

-- DropForeignKey
ALTER TABLE "DramaEpisode" DROP CONSTRAINT "DramaEpisode_projectId_fkey";

-- DropForeignKey
ALTER TABLE "DramaFact" DROP CONSTRAINT "DramaFact_projectId_fkey";

-- DropForeignKey
ALTER TABLE "DramaCharacterLibrary" DROP CONSTRAINT "DramaCharacterLibrary_projectId_fkey";

-- DropForeignKey
ALTER TABLE "DramaStoryboard" DROP CONSTRAINT "DramaStoryboard_projectId_fkey";

-- DropForeignKey
ALTER TABLE "DramaStoryboard" DROP CONSTRAINT "DramaStoryboard_episodeId_fkey";

-- DropForeignKey
ALTER TABLE "DramaShot" DROP CONSTRAINT "DramaShot_storyboardId_fkey";

-- DropForeignKey
ALTER TABLE "DramaVideoPrompt" DROP CONSTRAINT "DramaVideoPrompt_projectId_fkey";

-- DropForeignKey
ALTER TABLE "DramaVideoPrompt" DROP CONSTRAINT "DramaVideoPrompt_episodeId_fkey";

-- DropForeignKey
ALTER TABLE "DramaBatchJob" DROP CONSTRAINT "DramaBatchJob_projectId_fkey";

-- DropForeignKey
ALTER TABLE "DramaBatchJob" DROP CONSTRAINT "DramaBatchJob_episodeId_fkey";

-- DropForeignKey
ALTER TABLE "ComicSourceBundle" DROP CONSTRAINT "ComicSourceBundle_projectId_fkey";

-- DropForeignKey
ALTER TABLE "ComicEpisode" DROP CONSTRAINT "ComicEpisode_projectId_fkey";

-- DropForeignKey
ALTER TABLE "ComicPanel" DROP CONSTRAINT "ComicPanel_episodeId_fkey";

-- DropForeignKey
ALTER TABLE "ComicFact" DROP CONSTRAINT "ComicFact_projectId_fkey";

-- DropForeignKey
ALTER TABLE "ComicUploadAsset" DROP CONSTRAINT "ComicUploadAsset_projectId_fkey";

-- DropForeignKey
ALTER TABLE "ComicExportJob" DROP CONSTRAINT "ComicExportJob_projectId_fkey";

-- DropForeignKey
ALTER TABLE "ComicBatchJob" DROP CONSTRAINT "ComicBatchJob_projectId_fkey";

-- DropForeignKey
ALTER TABLE "ComicBatchJob" DROP CONSTRAINT "ComicBatchJob_episodeId_fkey";

-- DropIndex
DROP INDEX "DramaShot_storyboardId_idx";

-- DropIndex
DROP INDEX "DramaShot_storyboardId_order_key";

-- DropIndex
DROP INDEX "ComicPanel_episodeId_idx";

-- DropIndex
DROP INDEX "ComicPanel_episodeId_order_key";

-- AlterTable
ALTER TABLE "DramaShot" DROP COLUMN "storyboardId",
ADD COLUMN     "episodeOrder" INTEGER NOT NULL,
ADD COLUMN     "projectId" TEXT NOT NULL;

-- AlterTable
ALTER TABLE "ComicPanel" DROP COLUMN "episodeId",
ADD COLUMN     "episodeOrder" INTEGER NOT NULL,
ADD COLUMN     "projectId" TEXT NOT NULL;

-- DropTable
DROP TABLE "DirectorRuntimeCommand";

-- DropTable
DROP TABLE "DirectorRuntimeExecution";

-- DropTable
DROP TABLE "DirectorRuntimeCheckpoint";

-- DropTable
DROP TABLE "DirectorRuntimeEvent";

-- DropTable
DROP TABLE "AutoDirectorFollowUpNotificationLog";

-- DropTable
DROP TABLE "DramaSourceBundle";

-- DropTable
DROP TABLE "DramaEpisode";

-- DropTable
DROP TABLE "DramaFact";

-- DropTable
DROP TABLE "DramaCharacterLibrary";

-- DropTable
DROP TABLE "DramaStoryboard";

-- DropTable
DROP TABLE "DramaVideoPrompt";

-- DropTable
DROP TABLE "DramaBatchJob";

-- DropTable
DROP TABLE "ComicSourceBundle";

-- DropTable
DROP TABLE "ComicEpisode";

-- DropTable
DROP TABLE "ComicFact";

-- DropTable
DROP TABLE "ComicUploadAsset";

-- DropTable
DROP TABLE "ComicExportJob";

-- DropTable
DROP TABLE "ComicBatchJob";

-- CreateIndex
CREATE INDEX "DramaShot_projectId_idx" ON "DramaShot"("projectId");

-- CreateIndex
CREATE INDEX "ComicPanel_projectId_idx" ON "ComicPanel"("projectId");

