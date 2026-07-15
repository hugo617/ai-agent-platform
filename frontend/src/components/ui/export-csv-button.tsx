import { Download, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { apiErrorMessage } from "@/api/client";
import { useExportCsv } from "@/hooks/queries";
import type { ExportEntity, ExportParams } from "@/api/endpoints";

/**
 * Export-to-CSV button with built-in mutation, spinner, and toasts.
 *
 * Replaces the byte-identical export handler + button duplicated across the
 * customers / logs / billing pages (each had its own ``handleExport`` building
 * ``${entity}_${YYYY-MM-DD}.csv`` and the same Loader2/Download toggle). The
 * component owns the filename (derived from ``entity`` + today) and the
 * success/error toasts, so call sites just declare what to export.
 *
 * Pass ``label`` to override the button text (e.g. "导出用量").
 */
export function ExportCsvButton({
  entity,
  params,
  label = "导出 CSV",
  successMessage,
  size,
  variant = "outline",
}: {
  entity: ExportEntity;
  params?: ExportParams;
  label?: string;
  /** Override the default "已导出" toast title. */
  successMessage?: string;
  size?: "default" | "sm" | "lg" | "icon";
  variant?: "default" | "outline" | "ghost" | "secondary" | "destructive";
}) {
  const toast = useToast();
  const exportMut = useExportCsv();

  const handleExport = async () => {
    const filename = `${entity}_${new Date().toISOString().slice(0, 10)}.csv`;
    try {
      await exportMut.mutateAsync({ entity, params, filename });
      toast.success(successMessage ?? "已导出");
    } catch (err) {
      toast.error("导出失败", apiErrorMessage(err));
    }
  };

  return (
    <Button
      variant={variant}
      size={size}
      onClick={handleExport}
      disabled={exportMut.isPending}
    >
      {exportMut.isPending ? (
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
      ) : (
        <Download className="mr-2 h-4 w-4" />
      )}
      {label}
    </Button>
  );
}
