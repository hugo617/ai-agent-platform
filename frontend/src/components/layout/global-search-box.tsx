import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Bot,
  Building2,
  MessageSquare,
  Search,
  UserCircle,
  X,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { useGlobalSearch } from "@/hooks/queries";
import type { SearchResultItem } from "@/api/types";

// Render order for the dropdown sections. Declared first so the CATEGORIES
// record can key off its keys.
const SECTION_ORDER = {
  agents: 0,
  customers: 1,
  conversations: 2,
  users: 3,
  tenants: 4,
} as const;

// Category → (Chinese label, lucide icon, route builder, list-page-with-search).
// Each route takes the item id; the "查看全部" link goes to the list page with
// the current term as the search param so the user can see the full result set.
interface CategoryConfig {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  /** Build the detail-page route for one hit. */
  route: (id: string) => string;
  /** Build the "查看全部" list-page URL (with the search term). */
  listRoute: (term: string) => string;
}

const CATEGORIES: Record<keyof typeof SECTION_ORDER, CategoryConfig> = {
  agents: {
    label: "智能体",
    icon: Bot,
    route: () => `/agents`,
    listRoute: (term) => `/agents?search=${encodeURIComponent(term)}`,
  },
  customers: {
    label: "客户",
    icon: UserCircle,
    route: () => `/customers`,
    listRoute: (term) => `/customers?search=${encodeURIComponent(term)}`,
  },
  conversations: {
    label: "对话",
    icon: MessageSquare,
    route: () => `/chat`,
    listRoute: (term) => `/chat?search=${encodeURIComponent(term)}`,
  },
  users: {
    label: "用户",
    icon: UserCircle,
    route: () => `/users`,
    listRoute: (term) => `/users?search=${encodeURIComponent(term)}`,
  },
  tenants: {
    label: "门店",
    icon: Building2,
    route: () => `/tenants`,
    listRoute: () => `/tenants`,
  },
};

/**
 * Top-bar global search box.
 *
 * A magnifier input with a 300ms-debounced cross-entity search. While the
 * debounced term is >= 2 chars a dropdown shows categorized hits (智能体 / 客户 /
 * 对话 / 用户 / 门店), top 5 each. Selecting a hit navigates to that entity's
 * page; "查看全部" opens the list page with the term as the search filter.
 * Clicking outside or pressing Escape closes the dropdown.
 */
export function GlobalSearchBox() {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  // Only fire the query for terms >= 2 chars; useGlobalSearch gates the request
  // (enabled) so shorter terms produce no network traffic.
  const { data, isFetching } = useGlobalSearch(query);

  // Close on outside click.
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const term = query.trim();

  const handleSelect = (cfg: CategoryConfig, item: SearchResultItem) => {
    navigate(cfg.route(item.id));
    setOpen(false);
    setQuery("");
  };

  const handleViewAll = (cfg: CategoryConfig) => {
    navigate(cfg.listRoute(term));
    setOpen(false);
    setQuery("");
  };

  const hasAnyHit = !!data && (
    data.agents.length +
    data.customers.length +
    data.conversations.length +
    data.users.length +
    data.tenants.length
  ) > 0;
  // Show the dropdown when there's a debounced term of sufficient length AND
  // the input is focused. Empty results show a "无结果" row.
  const showDropdown = open && term.length >= 2;

  return (
    <div ref={containerRef} className="relative w-full max-w-md">
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              setOpen(false);
              setQuery("");
            }
          }}
          placeholder="搜索智能体 / 客户 / 对话…"
          className="h-9 pl-8 pr-8"
          aria-label="全局搜索"
        />
        {query && (
          <button
            type="button"
            onClick={() => {
              setQuery("");
            }}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            aria-label="清除搜索"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {showDropdown && (
        <div className="absolute left-0 right-0 top-full z-50 mt-1 max-h-[28rem] overflow-y-auto rounded-md border bg-background shadow-lg">
          {isFetching && (
            <div className="px-3 py-2 text-sm text-muted-foreground">
              搜索中…
            </div>
          )}
          {!isFetching && !hasAnyHit && (
            <div className="px-3 py-2 text-sm text-muted-foreground">
              无结果
            </div>
          )}
          {!isFetching &&
            hasAnyHit &&
            (Object.keys(SECTION_ORDER) as Array<keyof typeof SECTION_ORDER>)
              .filter((key) => (data?.[key]?.length ?? 0) > 0)
              .map((key) => {
                const cfg = CATEGORIES[key];
                const items = data?.[key] ?? [];
                return (
                  <div key={key} className="border-b last:border-b-0">
                    <div className="flex items-center justify-between bg-muted/40 px-3 py-1.5">
                      <span className="text-xs font-medium text-muted-foreground">
                        {cfg.label}
                      </span>
                      <button
                        type="button"
                        onClick={() => handleViewAll(cfg)}
                        className="text-xs text-primary hover:underline"
                      >
                        查看全部
                      </button>
                    </div>
                    {items.map((item) => (
                      <button
                        key={`${key}-${item.id}`}
                        type="button"
                        onClick={() => handleSelect(cfg, item)}
                        className={cn(
                          "flex w-full items-center gap-2 px-3 py-2 text-left text-sm",
                          "hover:bg-accent hover:text-accent-foreground",
                        )}
                      >
                        <cfg.icon className="h-4 w-4 shrink-0 text-muted-foreground" />
                        <span className="truncate">{item.label}</span>
                      </button>
                    ))}
                  </div>
                );
              })}
        </div>
      )}
    </div>
  );
}
