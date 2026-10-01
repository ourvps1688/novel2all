import { useState } from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Bell, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useDirectorAttentions } from "@/hooks/useDirectorAttention";
import { useDirectorAttentionActionExecutor } from "@/lib/directorAttentionActions";
import { DirectorAttentionCenter } from "@/components/autoDirector/DirectorAttentionCenter";

/**
 * T5: persistent, cross-page "needs attention" bell + drawer.
 *
 * The count reflects every non-idle novel returned by the aggregate endpoint.
 * Because this is driven by its own `useDirectorAttentions` query, it stays
 * visible even after an in-page banner is dismissed — it is never tied to
 * sessionStorage.
 */
export default function DirectorAttentionBadge() {
  const { data: attentions = [] } = useDirectorAttentions();
  const executor = useDirectorAttentionActionExecutor();
  const [open, setOpen] = useState(false);

  const actionable = attentions.filter((attention) => attention.level !== "idle");
  const count = actionable.length;

  return (
    <>
      <Button
        type="button"
        size="sm"
        variant="outline"
        className={cn(
          "relative transition-[border-color,background-color,box-shadow] duration-300",
          count > 0 &&
            "border-primary/60 bg-primary/[0.06] shadow-[0_0_0_3px_hsl(var(--primary)/0.12)]",
        )}
        onClick={() => setOpen(true)}
        title={count > 0 ? `有 ${count} 本小说需要你处理` : "没有待处理的小说"}
        aria-label="待处理提醒"
      >
        <Bell className={count > 0 ? "h-4 w-4 text-primary" : "h-4 w-4"} />
        {count > 0 ? (
          <Badge className="ml-1.5 h-5 min-w-5 px-1.5 text-[10px]" aria-label={`${count} 项待处理`}>
            {count}
          </Badge>
        ) : null}
      </Button>

      <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
        <DialogPrimitive.Portal>
          <DialogPrimitive.Overlay className="fixed inset-0 z-[60] bg-black/50 backdrop-blur-sm" />
          <DialogPrimitive.Content
            className="fixed right-0 top-0 z-[70] flex h-[100dvh] w-[min(28rem,calc(100vw-1.5rem))] flex-col border-l bg-background shadow-2xl outline-none"
            aria-describedby="director-attention-drawer-description"
          >
            <header className="flex shrink-0 items-center justify-between border-b px-4 py-3">
              <DialogPrimitive.Title className="text-sm font-semibold">
                待处理小说{count > 0 ? `（${count}）` : ""}
              </DialogPrimitive.Title>
              <DialogPrimitive.Close asChild>
                <Button type="button" variant="ghost" size="icon" aria-label="关闭">
                  <X className="h-4 w-4" />
                </Button>
              </DialogPrimitive.Close>
            </header>
            <DialogPrimitive.Description
              id="director-attention-drawer-description"
              className="sr-only"
            >
              列出所有自动导演需要你介入的小说，点按主操作即可继续或恢复。
            </DialogPrimitive.Description>
            <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
              {actionable.length === 0 ? (
                <p className="text-sm text-muted-foreground">当前没有需要你处理的小说。</p>
              ) : (
                actionable.map((attention) => (
                  <DirectorAttentionCenter
                    key={attention.novelId}
                    state={attention}
                    variant="card"
                    onAction={async (action) => {
                      await executor(action);
                      setOpen(false);
                    }}
                  />
                ))
              )}
            </div>
          </DialogPrimitive.Content>
        </DialogPrimitive.Portal>
      </DialogPrimitive.Root>
    </>
  );
}
