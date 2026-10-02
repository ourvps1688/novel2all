import { Dialog, DialogContent } from "@/components/ui/dialog";
import AssetHubPage from "@/pages/assets/AssetHubPage";

export interface NovelAssetsDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * 把既有的「创作资产」枢纽（AssetHubPage，全局可复用素材库）以右侧抽屉形式挂进
 * 小说工作区，而非独立顶层页面。抽屉直接复用 AssetHubPage，因此 9 个分类（含
 * knowledge / style-engine 的 link 模式）全部免费可用。点击 link 模式分类会跳出到
 * 对应独立路由，抽屉随之关闭。
 */
export default function NovelAssetsDrawer({ open, onOpenChange }: NovelAssetsDrawerProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="left-auto right-0 top-0 flex h-dvh max-h-dvh w-full max-w-[860px] translate-x-0 translate-y-0 flex-col gap-0 rounded-none border-y-0 border-r-0 border-l bg-background p-0 pr-10 overflow-y-auto">
        <AssetHubPage />
      </DialogContent>
    </Dialog>
  );
}
