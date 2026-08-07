/**
 * knowledge/ knowledge-page.tsx — barrel re-export.
 *
 * 镜像 devices/devices-page.tsx + bookings/bookings-page.tsx 范式(reader-ui
 * slice 01):旧 ``pages/knowledge-page.tsx`` 单文件重构成 ``knowledge/`` 文件夹,
 * 本文件只是 barrel re-export,让 App.tsx 的 lazy import
 * ``import("@/pages/knowledge-page")`` 路径零改动(保持「page file name = route
 * name」约定,不触碰 router)。
 *
 * ⚠️ App.tsx 的 lazy import 路径是 ``@/pages/knowledge-page``(指向旧文件位置)。
 * 旧 ``pages/knowledge-page.tsx`` 已改为 re-export 本文件夹的 KnowledgePage(见该
 * 文件),所以路由入口是「旧文件 → 旧文件 barrel → 本文件夹 barrel → index.tsx」
 * 两段 re-export。切片 03 可选把 App.tsx 的 import 路径直接指向
 * ``@/pages/knowledge/knowledge-page``,但 slice 01 严守「App.tsx 零改动」。
 */
export { KnowledgePage } from "./index";
