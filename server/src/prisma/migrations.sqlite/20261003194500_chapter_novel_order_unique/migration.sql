-- AlterTable: enforce one Chapter row per (novelId, order)
-- Prevents the auto-director chapter-materialization race from creating
-- duplicate chapter numbers (see VolumeChapterSyncService idempotent create).

-- DropIndex
DROP INDEX "Chapter_novelId_order_idx";

-- CreateIndex
CREATE UNIQUE INDEX "Chapter_novelId_order_key" ON "Chapter"("novelId", "order");
