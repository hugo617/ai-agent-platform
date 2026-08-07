// knowledge API 集成测试(msw seam,knowledge-tiered reader-ui slice 01)。
//
// 这是项目首个 msw 集成测试层(plan §4.6 显式声明偏离 mock-hook 范式)。目的:
// 锁「前端类型层 ↔ 后端 API 契约」的连接点 —— 既有 mock-hook 范式(stub useXxx
// hook)不覆盖这层,所以 fetchDocuments 的 query string 构造 + DocumentRead 新字段
// 解析 + KnowledgeCategoryRead 响应一旦偏离后端 schema,这里会变红。
//
// 模式:
//   - ``server`` 单例来自 ``@/test/msw-server``,``beforeAll`` listen +
//     ``afterAll`` close + ``afterEach`` resetHandlers(隔离每个用例的 handler)。
//   - ``onUnhandledRequest: "error"`` 强制每个请求显式 mock,避免漏 mock 假装通过。
//   - 直接调 fetchDocuments / fetchKnowledgeCharacters(绕过 hook),断言「endpoint
//     层发出的请求 + 解析的响应」,不测 React Query 缓存(那层由组件测试覆盖)。
//
// baseURL = /api/v1(见 src/api/client.ts),msw handler 路径要带 /api/v1 前缀。
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import {
  fetchDocuments,
  fetchKnowledgeCategories,
} from "@/api/endpoints";
import type {
  DocumentRead,
  KnowledgeCategoryRead,
} from "@/api/types";
import { http, server } from "@/test/msw-server";

const API = "/api/v1";

// 后端 schema fixture(对齐 app/schemas/document.py)。scope/group_id/category_id
// 是 reader-ui slice 01 新加的字段 —— 后端 DocumentRead.scope 有 server_default
// 'store',所以 fixture 默认 store;group_id/category_id 可 null。
function makeDocument(
  overrides: Partial<DocumentRead> = {},
): DocumentRead {
  return {
    id: "doc_1",
    tenant_id: "tn_1",
    name: "颈椎理疗话术",
    source_type: "text",
    content: "## 开场\n欢迎光临...",
    chunk_count: 3,
    status: "indexed",
    scope: "store",
    group_id: null,
    category_id: null,
    created_at: "2026-08-07T09:00:00Z",
    updated_at: "2026-08-07T09:00:00Z",
    ...overrides,
  };
}

function makeCategory(
  overrides: Partial<KnowledgeCategoryRead> = {},
): KnowledgeCategoryRead {
  return {
    id: "cat_1",
    name: "产品手册",
    scope: "store",
    group_id: null,
    tenant_id: "tn_1",
    sort_order: 0,
    is_deleted: false,
    created_at: "2026-08-07T09:00:00Z",
    updated_at: "2026-08-07T09:00:00Z",
    ...overrides,
  };
}

// msw 生命周期:listen(接管请求)→ 每用例 resetHandlers(隔离)→ close(归还控制)。
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("knowledge API — fetchDocuments 请求构造 + 类型契约(msw)", () => {
  it("无 filter:发裸 GET /knowledge/documents(无 query string)", async () => {
    let capturedUrl = "";
    server.use(
      http.get(`${API}/knowledge/documents`, ({ request }) => {
        capturedUrl = request.url;
        return Response.json([makeDocument()]);
      }),
    );

    const docs = await fetchDocuments();

    // 请求构造:无 filter → 不带 scope/category_id query string。msw 把
    // request.url 完整化(带 host),用 URL 对象只验 pathname + search。
    const u = new URL(capturedUrl);
    expect(u.pathname).toBe(`${API}/knowledge/documents`);
    expect(u.search).toBe("");
    // 响应解析:返回 DocumentRead[],长度对得上。
    expect(docs).toHaveLength(1);
    expect(docs[0].id).toBe("doc_1");
  });

  it("带 {scope:'group', category_id:'cat_1'}:query string 透传两个参数", async () => {
    let capturedUrl = "";
    server.use(
      http.get(`${API}/knowledge/documents`, ({ request }) => {
        capturedUrl = request.url;
        return Response.json([makeDocument({ scope: "group", category_id: "cat_1" })]);
      }),
    );

    const docs = await fetchDocuments({
      scope: "group",
      category_id: "cat_1",
    });

    // 请求构造:scope + category_id 都进 query string(透传,后端按 role 过滤,
    // 但前端必须把 filter 构造出来 —— 这是 slice 02 category-tree 点击 → list
    // 过滤的契约基础)。
    const u = new URL(capturedUrl);
    expect(u.searchParams.get("scope")).toBe("group");
    expect(u.searchParams.get("category_id")).toBe("cat_1");
    // 响应解析:新字段 scope/category_id 从响应里正确读出。
    expect(docs[0].scope).toBe("group");
    expect(docs[0].category_id).toBe("cat_1");
  });

  it("只带 scope:仅 scope 进 query string,无 category_id", async () => {
    let capturedUrl = "";
    server.use(
      http.get(`${API}/knowledge/documents`, ({ request }) => {
        capturedUrl = request.url;
        return Response.json([]);
      }),
    );

    await fetchDocuments({ scope: "platform" });

    // axios drop undefined → category_id 不进 query string。
    const u = new URL(capturedUrl);
    expect(u.searchParams.get("scope")).toBe("platform");
    expect(u.searchParams.has("category_id")).toBe(false);
  });

  it("DocumentRead 新字段(scope/group_id/category_id)类型契约对齐后端", async () => {
    // 后端 DocumentRead.scope 有 server_default 'store'(非 null);group_id 仅
    // scope=group 时设;category_id 未分类时 null。这用例锁这个契约。
    server.use(
      http.get(`${API}/knowledge/documents`, () =>
        Response.json([
          makeDocument({
            id: "doc_platform",
            scope: "platform",
            group_id: null,
            category_id: "cat_global",
          }),
          makeDocument({
            id: "doc_group",
            scope: "group",
            group_id: "grp_1",
            category_id: null,
          }),
          makeDocument({
            id: "doc_store",
            scope: "store",
            group_id: null,
            category_id: null,
          }),
        ]),
      ),
    );

    const docs = await fetchDocuments();
    expect(docs).toHaveLength(3);
    // scope 三态都对得上 union "platform"|"group"|"store"。
    expect(docs[0].scope).toBe("platform");
    expect(docs[1].scope).toBe("group");
    expect(docs[2].scope).toBe("store");
    // group_id 仅 scope=group 设。
    expect(docs[1].group_id).toBe("grp_1");
    expect(docs[0].group_id).toBeNull();
    expect(docs[2].group_id).toBeNull();
  });
});

describe("knowledge API — fetchKnowledgeCategories 响应解析(msw)", () => {
  it("GET /knowledge/categories 返回 KnowledgeCategoryRead[]", async () => {
    server.use(
      http.get(`${API}/knowledge/categories`, () =>
        Response.json([
          makeCategory({ id: "cat_p", scope: "platform", tenant_id: null }),
          makeCategory({ id: "cat_g", scope: "group", group_id: "grp_1", tenant_id: null }),
          makeCategory({ id: "cat_s", scope: "store", tenant_id: "tn_1" }),
        ]),
      ),
    );

    const cats = await fetchKnowledgeCategories();

    expect(cats).toHaveLength(3);
    // scope↔ownership 绑定:platform → 两 null;group → group_id;store → tenant_id。
    expect(cats[0].scope).toBe("platform");
    expect(cats[0].group_id).toBeNull();
    expect(cats[0].tenant_id).toBeNull();
    expect(cats[1].scope).toBe("group");
    expect(cats[1].group_id).toBe("grp_1");
    expect(cats[2].scope).toBe("store");
    expect(cats[2].tenant_id).toBe("tn_1");
    // is_deleted 字段在后端 schema 里(knowledge tiered foundation 软删除),
    // 前端 type 必须收下 —— 不收会丢契约。
    expect(cats[0].is_deleted).toBe(false);
  });

  it("空 categories:返回 [](门店可能没有任何可见 category 的空态)", async () => {
    server.use(
      http.get(`${API}/knowledge/categories`, () => Response.json([])),
    );

    const cats = await fetchKnowledgeCategories();
    expect(cats).toEqual([]);
  });
});
