/**
 * knowledge-page.tsx — barrel re-export(reader-ui slice 01 + 03)。
 *
 * 旧的单文件 KnowledgePage(458 行:列表 Table + 录入/删除 Dialog +
 * RetrievalDebugCard)已重构进 ``pages/knowledge/`` 文件夹。本文件改为 barrel,
 * 让 App.tsx 的 lazy import ``import("@/pages/knowledge-page")`` 路径**零改动**
 * (plan AC5:App.tsx import 零改动)。
 *
 * 实际入口是 ``pages/knowledge/index.tsx``(三栏编排 + 底部 RetrievalDebugCard)。
 * 切片 01-02 期间旧 page 行为整体保留在 ``legacy-page.tsx`` 过渡;切片 03 已迁移
 * 完毕(CRUD 进 document-list.tsx、调试卡独立成 retrieval-debug-card.tsx)并删除
 * legacy-page。本 barrel 维持 ``knowledge/knowledge-page.tsx`` →
 * ``knowledge/index.tsx`` 的 re-export 链。
 *
 * 镜像 devices/devices-page.tsx 的 barrel 范式(「page file name = route name」
 * 约定保留,不触碰 router)。
 */
export { KnowledgePage } from "./knowledge/knowledge-page";
