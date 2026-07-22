import {
  Bot,
  BookOpen,
  Building2,
  Contact,
  Coins,
  LayoutDashboard,
  MessageSquare,
  Monitor,
  ScrollText,
  Settings,
  Shield,
  ShieldCheck,
  Store,
  Users,
  UserCog,
  Wallet,
} from "lucide-react";
import type { MeResponse } from "@/api/types";
import { canViewMenu, hasPermission, isSuperAdmin } from "@/lib/permission";

/**
 * Navigation model — the single source for sidebar items, the ⌘K command menu,
 * and any "jump to" UI.
 *
 * Items carry their own visibility predicate so the sidebar and the command
 * menu render the exact same set without duplicating the permission logic. The
 * predicate reuses the existing helpers (``canViewMenu`` / ``hasPermission`` /
 * ``isSuperAdmin``) — no new permission mechanism, just a shared data table.
 *
 * Grouped into three sections (工作台 / 管理 / 平台) per the UI revamp plan
 * (§1.1): the sidebar renders one ``<NavGroup>`` per group, and the command
 * menu renders one ``<CommandGroup>`` per group. ``platformOnly`` items land in
 * the 平台 group and are gated purely on ``platform_role === "super_admin"``.
 */

export interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  /** Menu permission code (e.g. "menu:agents"). Gates visibility via canViewMenu. */
  menuCode?: string;
  /** Platform-level items: no tenant menu perm, gated on super_admin. */
  platformOnly?: boolean;
  /** Gate on an api permission code instead of a menu code. super_admin bypasses. */
  permission?: { obj: string; act: string };
}

export interface NavSubgroup {
  /** Collapsible sub-heading inside a group (e.g. "业务管理" under 管理). */
  label: string;
  items: NavItem[];
}

export interface NavGroup {
  /** Section heading (null = no heading, e.g. the primary 工作台 group). */
  label: string;
  /**
   * Direct flat items rendered as a one-level list (used by 工作台 / 平台).
   * Ignored by the sidebar when ``subgroups`` is present.
   */
  items: NavItem[];
  /**
   * Optional collapsible sub-groups (used by 管理). When present, the sidebar
   * renders an accordion of these instead of the flat ``items``. The command
   * palette flattens both ``items`` and ``subgroups[].items`` into one list.
   */
  subgroups?: NavSubgroup[];
}

// Flat item list (single source). Grouping is applied by GROUPS below. Order
// within a group is preserved as written here.
const ITEMS: NavItem[] = [
  // --- 工作台 (primary tools a member uses day-to-day) ---
  { to: "/", label: "概览", icon: LayoutDashboard, menuCode: "menu:dashboard" },
  { to: "/agents", label: "智能体", icon: Bot, menuCode: "menu:agents" },
  { to: "/chat", label: "对话", icon: MessageSquare, menuCode: "menu:chat" },
  {
    to: "/knowledge",
    label: "知识库",
    icon: BookOpen,
    menuCode: "menu:knowledge",
  },

  // --- 管理 (tenant administration) ---
  {
    to: "/groups",
    label: "组织",
    icon: Building2,
    menuCode: "menu:groups",
  },
  {
    to: "/customers",
    label: "客户",
    icon: Contact,
    menuCode: "menu:customers",
  },
  // devices (devices-crud-ui slice 02): menu:devices seeded to owner/admin/
  // member, so the whole store-side roles see the nav entry. hq_staff /
  // super_admin bypass menu checks (platform role), so they see it too even
  // though they have no tenant role — the HQ panorama view branches in-page.
  {
    to: "/devices",
    label: "设备",
    icon: Monitor,
    menuCode: "menu:devices",
  },
  {
    to: "/billing",
    label: "费用管理",
    icon: Wallet,
    permission: { obj: "wallet", act: "read" },
  },
  { to: "/members", label: "成员", icon: UserCog, menuCode: "menu:members" },
  { to: "/users", label: "用户", icon: Users, menuCode: "menu:users" },
  { to: "/roles", label: "角色", icon: Shield, menuCode: "menu:roles" },
  {
    to: "/permissions",
    label: "权限矩阵",
    icon: ShieldCheck,
    menuCode: "menu:permissions",
  },
  { to: "/settings", label: "设置", icon: Settings, menuCode: "menu:settings" },
  {
    to: "/logs",
    label: "审计日志",
    icon: ScrollText,
    permission: { obj: "logs", act: "read" },
  },

  // --- 平台 (super_admin only) ---
  { to: "/tenants", label: "门店", icon: Store, platformOnly: true },
  { to: "/billing/admin", label: "计费管理", icon: Coins, platformOnly: true },
];

/** Pick a single item from the flat source by its `to`. */
const pick = (to: string): NavItem => {
  const found = ITEMS.find((i) => i.to === to);
  if (!found) throw new Error(`nav-items: unknown route ${to}`);
  return found;
};

const GROUPS: NavGroup[] = [
  {
    label: "工作台",
    items: ITEMS.filter((i) =>
      ["/", "/agents", "/chat", "/knowledge"].includes(i.to),
    ),
  },
  {
    label: "管理",
    // 9 项拆成 3 个可折叠二级组,缓解侧边栏过长(§sidebar-collapsible)。
    // items 留空,侧边栏只渲染 subgroups;命令面板拍平后与历史一致。
    items: [],
    subgroups: [
      {
        label: "业务管理",
        items: ["/groups", "/customers", "/devices", "/billing"].map(pick),
      },
      {
        label: "人员与权限",
        items: ["/members", "/users", "/roles", "/permissions"].map(pick),
      },
      {
        label: "系统设置",
        items: ["/settings", "/logs"].map(pick),
      },
    ],
  },
  {
    label: "平台",
    items: ITEMS.filter((i) => i.platformOnly),
  },
];

/** Does the given user have permission to see this nav item? */
export function canSeeItem(me: MeResponse | null | undefined, item: NavItem): boolean {
  if (item.platformOnly) return isSuperAdmin(me);
  if (item.permission)
    return hasPermission(me, item.permission.obj, item.permission.act);
  return canViewMenu(me, item.menuCode ?? "");
}

/** All groups with their items pre-filtered to what `me` may see. */
export function visibleGroups(
  me: MeResponse | null | undefined,
): NavGroup[] {
  return GROUPS.map((g) => {
    const items = g.items.filter((item) => canSeeItem(me, item));
    const subgroups = g.subgroups
      ?.map((sg) => ({
        ...sg,
        items: sg.items.filter((item) => canSeeItem(me, item)),
      }))
      .filter((sg) => sg.items.length > 0);
    return { ...g, items, subgroups };
  }).filter(
    // 丢弃直接项与子组全空的 group(管理区某用户一项都看不到就整区不渲染)。
    (g) => g.items.length > 0 || (g.subgroups?.length ?? 0) > 0,
  );
}
