-- RenameTable
ALTER TABLE "AutoDirectorFollowUpActionLog" RENAME TO "AutoDirectorAttentionActionLog";

-- RenameIndex
DROP INDEX "AutoDirectorFollowUpActionLog_idempotencyKey_key";
CREATE UNIQUE INDEX "AutoDirectorAttentionActionLog_idempotencyKey_key" ON "AutoDirectorAttentionActionLog"("idempotencyKey");

-- RenameIndex
DROP INDEX "AutoDirectorFollowUpActionLog_taskId_executedAt_idx";
CREATE INDEX "AutoDirectorAttentionActionLog_taskId_executedAt_idx" ON "AutoDirectorAttentionActionLog"("taskId","executedAt");

-- RenameIndex
DROP INDEX "AutoDirectorFollowUpActionLog_taskId_actionCode_executedAt_idx";
CREATE INDEX "AutoDirectorAttentionActionLog_taskId_actionCode_executedAt_idx" ON "AutoDirectorAttentionActionLog"("taskId","actionCode","executedAt");
