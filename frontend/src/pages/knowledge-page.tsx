/**
 * knowledge-page.tsx — barrel re-export(reader-ui slice 01)。
 *
 * 旧的单文件 KnowledgePage(458 行:列表 Table + 录入/删除 Dialog +
 * RetrievalDebugCard)已重构进 ``pages/knowledge/`` 文件夹。本文件改为 barrel,
 * 让 App.tsx 的 lazy import ``import("@/pages/knowledge-page")`` 路径**零改动**
 * (plan AC5:App.tsx import 零改动)。
 *
 * 实际入口是 ``pages/knowledge/index.tsx``(三栏编排 + LegacyKnowledgePage 过渡)。
 * 旧的全部行为(列表 Table + CRUD + 检索调试)在切片 01 期间整体保留在
 * ``pages/knowledge/legacy-page.tsx``,由 index.tsx 在三栏空壳下方渲染 ——
 * plan G2 行为零回归。切片 03 拆掉 legacy-page,届时本 barrel 仍是
 * ``knowledge/knowledge-page.tsx`` → ``knowledge/index.tsx`` 的 re-export 链。
 *
 * 镜像 devices/devices-page.tsx 的 barrel 范式(「page file name = route name」
 * 约定保留,不触碰 router)。
 */
export { KnowledgePage } from "./knowledge/knowledge-page";
