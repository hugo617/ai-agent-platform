/**
 * customers/ customer-usage-dialog — AI service usage attribution dialog.
 *
 * Extracted from the original customers-page.tsx (plan-customers-page-split.md).
 * Shared by both StoreView (storeScoped=true) and HqView (storeScoped=false);
 * the backend returns store-scoped or global totals based on the caller's role.
 *
 * Takes the GLOBAL customer id (Customer.id), not the profile id.
 *
 * Token 费用管理系列 3/4.
 */
import { useNavigate } from "react-router-dom";
import { Activity, MessageSquare } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useCustomerUsage } from "@/hooks/queries";
import { formatDateTime as fmt, formatTokens } from "@/lib/format";

function Metric({
  label,
  value,
  icon,
}: {
  label: string;
  value: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="rounded-md border bg-background p-3">
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        {icon}
        {label}
      </div>
      <div className="mt-1 text-lg font-semibold">{value}</div>
    </div>
  );
}

export function CustomerUsageDialog({
  customerId,
  customerName,
  storeScoped,
  onClose,
}: {
  customerId: string | null;
  customerName: string;
  storeScoped: boolean;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const { data: usage, isLoading } = useCustomerUsage(customerId);

  const openNewChatForCustomer = () => {
    if (!customerId) return;
    onClose();
    navigate(`/chat?customer_id=${encodeURIComponent(customerId)}`);
  };

  return (
    <Dialog open={!!customerId} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>AI 服务 · {customerName}</DialogTitle>
          <DialogDescription>
            {storeScoped
              ? "本店为该客户提供 AI 服务的用量统计"
              : "跨全部门店为该客户提供 AI 服务的用量统计"}
          </DialogDescription>
        </DialogHeader>
        {isLoading ? (
          <div className="py-8 text-center text-sm text-muted-foreground">
            加载中…
          </div>
        ) : usage && usage.total_tokens > 0 ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Metric
                label="AI 对话次数"
                value={String(usage.conversation_count)}
                icon={<MessageSquare className="h-4 w-4" />}
              />
              <Metric
                label="Token 总消耗"
                value={formatTokens(usage.total_tokens)}
                icon={<Activity className="h-4 w-4" />}
              />
              <Metric
                label="输入 Token"
                value={formatTokens(usage.prompt_tokens)}
              />
              <Metric
                label="输出 Token"
                value={formatTokens(usage.completion_tokens)}
              />
            </div>
            {usage.total_cost !== null && (
              <div className="rounded-md border bg-muted/30 px-3 py-2 text-sm">
                累计费用：
                <span className="font-medium">
                  ¥{usage.total_cost.toFixed(4)}
                </span>
              </div>
            )}
            <div className="text-xs text-muted-foreground">
              最近 AI 咨询：{fmt(usage.last_active_at)}
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2 py-6 text-center">
            <Activity className="h-8 w-8 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              该客户暂无 AI 服务记录
            </p>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            关闭
          </Button>
          <Button onClick={openNewChatForCustomer}>
            <MessageSquare className="mr-2 h-4 w-4" /> 为客户咨询
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
