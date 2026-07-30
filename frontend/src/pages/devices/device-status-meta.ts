/**
 * devices/ device-status-meta.ts — device 状态领域模型(状态原语,无 React)。
 *
 * 从原 1083 行 devices-page.tsx 抽出(plan-devices-page-split.md)。镜像
 * ``bookings/status-meta.ts`` 的范式:纯数据叶子节点,供 shared.tsx 的
 * StatusBadge / StatusSelect 及未来 view 按需 deep import。
 *
 * Why a dedicated module: 状态映射是 devices 子域的词汇表,集中一处意味着
 * 加新状态(如 ``decommissioned``)只改一个文件,不必遍历所有 view。
 */
import type { DeviceStatus } from "@/api/types";

// active → 运行中 / maintenance → 维护中 / retired → 已退役. Mirrors the
// backend DeviceStatus Literal. Drives the status Badge colour (dot-* variants)
// and the Select options in create/edit dialogs.
export const STATUS_OPTIONS: DeviceStatus[] = ["active", "maintenance", "retired"];
export const STATUS_META: Record<
  DeviceStatus,
  { label: string; badge: "success" | "warning" | "destructive" }
> = {
  active: { label: "运行中", badge: "success" },
  maintenance: { label: "维护中", badge: "warning" },
  retired: { label: "已退役", badge: "destructive" },
};

// SelectValue can't render an empty string; "_none" is the sentinel for the
// "no customer bound" option in the bind dialog (mirrors chat-page.tsx:685-707).
export const NONE = "_none";
