import { Router } from "express";
import type { ApiResponse } from "@ai-novel/shared/types/api";
import { z } from "zod";
import {
  AUTO_DIRECTOR_ATTENTION_REASONS,
} from "@ai-novel/shared/types/autoDirectorAttention";
import { authMiddleware } from "../middleware/auth";
import { validate } from "../middleware/validate";
import { AutoDirectorAttentionActionExecutor } from "../services/task/autoDirectorAttentions/AutoDirectorAttentionActionExecutor";
import { AutoDirectorAttentionService } from "../services/task/autoDirectorAttentions/AutoDirectorAttentionService";

const router = Router();
const attentionService = new AutoDirectorAttentionService();
const actionExecutor = new AutoDirectorAttentionActionExecutor();

const reasonSchema = z.enum(AUTO_DIRECTOR_ATTENTION_REASONS);

const statusSchema = z.enum(["queued", "running", "waiting_approval", "succeeded", "failed", "cancelled"]);

const sectionSchema = z.enum(["pending", "auto_progress", "exception", "replaced", "needs_validation"]);

const listQuerySchema = z.object({
  section: sectionSchema.optional(),
  reason: reasonSchema.optional(),
  status: statusSchema.optional(),
  novelId: z.string().trim().optional(),
  supportsBatch: z.coerce.boolean().optional(),
  page: z.coerce.number().int().min(1).optional(),
  pageSize: z.coerce.number().int().min(1).max(100).optional(),
});

const taskParamsSchema = z.object({
  taskId: z.string().trim().min(1),
});

const singleActionBodySchema = z.object({
  actionCode: z.enum([
    "continue_auto_execution",
    "continue_generic",
    "retry_with_task_model",
    "retry_with_route_model",
    "safe_fix_validation",
  ]),
  idempotencyKey: z.string().trim().min(1),
});

function resolveOperatorId(): string {
  return "anonymous";
}

router.use(authMiddleware);

router.get("/", validate({ query: listQuerySchema }), async (req, res, next) => {
  try {
    const query = listQuerySchema.parse(req.query);
    const data = await attentionService.list(query);
    res.status(200).json({
      success: true,
      data,
      message: "Follow-ups loaded.",
    } satisfies ApiResponse<typeof data>);
  } catch (error) {
    next(error);
  }
});

router.get("/:taskId", validate({ params: taskParamsSchema }), async (req, res, next) => {
  try {
    const { taskId } = req.params as z.infer<typeof taskParamsSchema>;
    const data = await attentionService.getDetail(taskId);
    if (!data) {
      res.status(404).json({
        success: false,
        error: "Follow-up not found.",
      } satisfies ApiResponse<null>);
      return;
    }
    res.status(200).json({
      success: true,
      data,
      message: "Follow-up detail loaded.",
    } satisfies ApiResponse<typeof data>);
  } catch (error) {
    next(error);
  }
});

router.post("/:taskId/actions", validate({ params: taskParamsSchema, body: singleActionBodySchema }), async (req, res, next) => {
  try {
    const { taskId } = req.params as z.infer<typeof taskParamsSchema>;
    const body = req.body as z.infer<typeof singleActionBodySchema>;
    const data = await actionExecutor.execute({
      directorTaskId: taskId,
      taskId,
      actionCode: body.actionCode,
      source: "web",
      operatorId: resolveOperatorId(),
      idempotencyKey: body.idempotencyKey,
    });
    res.status(200).json({
      success: true,
      data,
      message: data.message,
    } satisfies ApiResponse<typeof data>);
  } catch (error) {
    next(error);
  }
});

export default router;
