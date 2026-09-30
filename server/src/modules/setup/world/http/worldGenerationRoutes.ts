import type { Router } from "express";
import type { ApiResponse } from "@ai-novel/shared/types/api";
import { z } from "zod";
import { streamToSSE } from "../../../../llm/streaming";
import { validate } from "../../../../middleware/validate";
import {
  libraryCreateSchema,
  libraryListQuerySchema,
  libraryUseParamsSchema,
  libraryUseSchema,
  worldIdSchema,
  worldRefineSchema,
  worldService,
} from "./worldHttpContext";

export function registerGenerationWorldRoutes(router: Router): void {
  router.get("/library", validate({ query: libraryListQuerySchema }), async (req, res, next) => {
    try {
      const query = libraryListQuerySchema.parse(req.query);
      const data = await worldService.listLibrary(query);
      res.status(200).json({
        success: true,
        data,
        message: "Library loaded.",
      } satisfies ApiResponse<typeof data>);
    } catch (error) {
      next(error);
    }
  });

  router.post("/library", validate({ body: libraryCreateSchema }), async (req, res, next) => {
    try {
      const data = await worldService.createLibraryItem(req.body as z.infer<typeof libraryCreateSchema>);
      res.status(201).json({
        success: true,
        data,
        message: "Library item created.",
      } satisfies ApiResponse<typeof data>);
    } catch (error) {
      next(error);
    }
  });

  router.post(
    "/library/:libraryId/use",
    validate({ params: libraryUseParamsSchema, body: libraryUseSchema }),
    async (req, res, next) => {
      try {
        const { libraryId } = req.params as z.infer<typeof libraryUseParamsSchema>;
        const data = await worldService.useLibraryItem(libraryId, req.body as z.infer<typeof libraryUseSchema>);
        res.status(200).json({
          success: true,
          data,
          message: "Library item used.",
        } satisfies ApiResponse<typeof data>);
      } catch (error) {
        next(error);
      }
    },
  );

  router.post("/:id/refine", validate({ params: worldIdSchema, body: worldRefineSchema }), async (req, res, next) => {
    try {
      const { id } = req.params as z.infer<typeof worldIdSchema>;
      const { stream, onDone } = await worldService.createRefineStream(
        id,
        req.body as z.infer<typeof worldRefineSchema>,
      );
      await streamToSSE(res, stream, onDone);
    } catch (error) {
      next(error);
    }
  });
}
