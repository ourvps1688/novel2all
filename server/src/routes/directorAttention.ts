import { Router } from "express";
import type { ApiResponse } from "@ai-novel/shared/types/api";
import { authMiddleware } from "../middleware/auth";
import { directorAttentionService } from "../services/novel/director/attention/DirectorAttentionService";

const router = Router();
router.use(authMiddleware);

router.get("/", async (_req, res, next) => {
  try {
    const attentions = await directorAttentionService.listAttentions();
    res.status(200).json({
      success: true,
      data: { attentions },
      message: "Director attentions loaded.",
    } satisfies ApiResponse<{ attentions: typeof attentions }>);
  } catch (error) {
    next(error);
  }
});

router.get("/:novelId", async (req, res, next) => {
  try {
    const novelId = String(req.params.novelId ?? "").trim();
    if (!novelId) {
      res.status(400).json({ success: false, error: "novelId is required." } satisfies ApiResponse<null>);
      return;
    }
    const attention = await directorAttentionService.getAttention(novelId);
    if (!attention) {
      res.status(404).json({ success: false, error: "Novel not found." } satisfies ApiResponse<null>);
      return;
    }
    res.status(200).json({
      success: true,
      data: { attention },
      message: "Director attention loaded.",
    } satisfies ApiResponse<{ attention: typeof attention }>);
  } catch (error) {
    next(error);
  }
});

export default router;
