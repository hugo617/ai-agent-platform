import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export interface PaginationProps {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  className?: string;
}

/** A compact page navigator: « ‹ page x/y › ». */
export function Pagination({
  page,
  totalPages,
  onPageChange,
  className,
}: PaginationProps) {
  if (totalPages <= 1) return null;
  const canPrev = page > 1;
  const canNext = page < totalPages;

  return (
    <div className={cn("flex items-center gap-1", className)}>
      <Button
        variant="outline"
        size="icon"
        className="h-8 w-8"
        disabled={!canPrev}
        onClick={() => onPageChange(1)}
        title="第一页"
      >
        <ChevronsLeft className="h-4 w-4" />
      </Button>
      <Button
        variant="outline"
        size="icon"
        className="h-8 w-8"
        disabled={!canPrev}
        onClick={() => onPageChange(page - 1)}
        title="上一页"
      >
        <ChevronLeft className="h-4 w-4" />
      </Button>
      <span className="px-3 text-sm text-muted-foreground">
        第 <span className="font-medium text-foreground">{page}</span> / {totalPages} 页
      </span>
      <Button
        variant="outline"
        size="icon"
        className="h-8 w-8"
        disabled={!canNext}
        onClick={() => onPageChange(page + 1)}
        title="下一页"
      >
        <ChevronRight className="h-4 w-4" />
      </Button>
      <Button
        variant="outline"
        size="icon"
        className="h-8 w-8"
        disabled={!canNext}
        onClick={() => onPageChange(totalPages)}
        title="最后一页"
      >
        <ChevronsRight className="h-4 w-4" />
      </Button>
    </div>
  );
}
