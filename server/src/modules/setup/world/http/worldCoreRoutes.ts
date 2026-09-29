import type { Router } from "express";
import type { ApiResponse } from "@ai-novel/shared/types/api";
import { z } from "zod";
import { validate } from "../../../../middleware/validate";
import {
  knowledgeBindingsSchema,
  knowledgeService,
  snapshotCreateSchema,
  snapshotDiffQuerySchema,
  snapshotRestoreParamsSchema,
  worldExportQuerySchema,
  worldIdSchema,
  worldImportSchema,
  worldService,
} from "./worldHttpContext";

export function registerCoreWorldRoutes(router: Router): void {
  router.post("/import", validate({ body: worldImportSchema }), async (req, res, next) => {
    try {
      const data = await worldService.importWorld(req.body as z.infer<typeof worldImportSchema>);
      res.status(201).json({
        success: true,
        data,
        message: "World imported.",
      } satisfies ApiResponse<typeof data>);
    } catch (error) {
      next(error);
    }
  });

  router.get("/", async (_req, res, next) => {
    try {
      const data = await worldService.listWorlds();
      res.status(200).json({
        success: true,
        data,
        message: "World list loaded.",
      } satisfies ApiResponse<typeof data>);
    } catch (error) {
      next(error);
    }
  });

  router.get("/:id", validate({ params: worldIdSchema }), async (req, res, next) => {
    try {
      const { id } = req.params as z.infer<typeof worldIdSchema>;
      const data = await worldService.getWorldById(id);
      if (!data) {
        res.status(404).json({
          success: false,
          error: "World not found.",
        } satisfies ApiResponse<null>);
        return;
      }
      res.status(200).json({
        success: true,
        data,
        message: "World loaded.",
      } satisfies ApiResponse<typeof data>);
    } catch (error) {
      next(error);
    }
  });

  router.get("/:id/knowledge-documents", validate({ params: worldIdSchema }), async (req, res, next) => {
    try {
      const { id } = req.params as z.infer<typeof worldIdSchema>;
      const data = await knowledgeService.listBindings("world", id);
      res.status(200).json({
        success: true,
        data,
        message: "World knowledge documents loaded.",
      } satisfies ApiResponse<typeof data>);
    } catch (error) {
      next(error);
    }
  });

  router.put(
    "/:id/knowledge-documents",
    validate({ params: worldIdSchema, body: knowledgeBindingsSchema }),
    async (req, res, next) => {
      try {
        const { id } = req.params as z.infer<typeof worldIdSchema>;
        const body = req.body as z.infer<typeof knowledgeBindingsSchema>;
        const data = await knowledgeService.replaceBindings("world", id, body.documentIds);
        res.status(200).json({
          success: true,
          data,
          message: "World knowledge documents updated.",
        } satisfies ApiResponse<typeof data>);
      } catch (error) {
        next(error);
      }
    },
  );

  router.delete("/:id", validate({ params: worldIdSchema }), async (req, res, next) => {
    try {
      const { id } = req.params as z.infer<typeof worldIdSchema>;
      await worldService.deleteWorld(id);
      res.status(200).json({
        success: true,
        message: "World deleted.",
      } satisfies ApiResponse<null>);
    } catch (error) {
      next(error);
    }
  });

  router.get("/:id/snapshots", validate({ params: worldIdSchema }), async (req, res, next) => {
    try {
      const { id } = req.params as z.infer<typeof worldIdSchema>;
      const data = await worldService.listSnapshots(id);
      res.status(200).json({
        success: true,
        data,
        message: "Snapshots loaded.",
      } satisfies ApiResponse<typeof data>);
    } catch (error) {
      next(error);
    }
  });

  router.post(
    "/:id/snapshots",
    validate({ params: worldIdSchema, body: snapshotCreateSchema }),
    async (req, res, next) => {
      try {
        const { id } = req.params as z.infer<typeof worldIdSchema>;
        const { label } = req.body as z.infer<typeof snapshotCreateSchema>;
        const data = await worldService.createSnapshot(id, label);
        res.status(201).json({
          success: true,
          data,
          message: "Snapshot created.",
        } satisfies ApiResponse<typeof data>);
      } catch (error) {
        next(error);
      }
    },
  );

  router.post(
    "/:id/snapshots/:snapshotId/restore",
    validate({ params: snapshotRestoreParamsSchema }),
    async (req, res, next) => {
      try {
        const { id, snapshotId } = req.params as z.infer<typeof snapshotRestoreParamsSchema>;
        const data = await worldService.restoreSnapshot(id, snapshotId);
        res.status(200).json({
          success: true,
          data,
          message: "Snapshot restored.",
        } satisfies ApiResponse<typeof data>);
      } catch (error) {
        next(error);
      }
    },
  );

  router.get(
    "/:id/snapshots/diff",
    validate({ params: worldIdSchema, query: snapshotDiffQuerySchema }),
    async (req, res, next) => {
      try {
        const { id } = req.params as z.infer<typeof worldIdSchema>;
        const { from, to } = snapshotDiffQuerySchema.parse(req.query);
        const data = await worldService.diffSnapshots(id, from, to);
        res.status(200).json({
          success: true,
          data,
          message: "Snapshot diff generated.",
        } satisfies ApiResponse<typeof data>);
      } catch (error) {
        next(error);
      }
    },
  );

  router.get(
    "/:id/export",
    validate({ params: worldIdSchema, query: worldExportQuerySchema }),
    async (req, res, next) => {
      try {
        const { id } = req.params as z.infer<typeof worldIdSchema>;
        const { format } = worldExportQuerySchema.parse(req.query);
        const data = await worldService.exportWorld(id, format);
        res.status(200).json({
          success: true,
          data,
          message: "Export payload prepared.",
        } satisfies ApiResponse<typeof data>);
      } catch (error) {
        next(error);
      }
    },
  );
}
