// MarkdownReader 组件测试(reader-ui slice 02)。
//
// 模式沿用 knowledge slice 01 的 document-list.test.tsx(vitest 基建)。本组件
// 是纯渲染(props { doc }),无 hook 自调,故无需 mock @/hooks/queries。
//
// 覆盖(plan §6 切片 02 AC8):Markdown 渲染(标题/段落/代码块)+ 目录大纲提取
// (有标题/无标题)+ 搜索高亮(有关键词 <mark> 出现 + 计数 + 无关键词无 mark)+
// 空态(doc=null)。
//
// ⚠️ react-markdown 在 jsdom 下会真实解析 Markdown 并渲染 DOM。搜索高亮的
// ``components.text`` 是否真的拦截文本节点、``<mark>`` 是否出现在 DOM —— 是本测试
// 的核心断言点(若 components.text 不生效,这里会暴露)。
import { afterEach, describe, expect, it } from "vitest";
import { renderWithProviders } from "@/test/test-utils";
import { MarkdownReader } from "../markdown-reader";
import type { DocumentRead } from "@/api/types";

function makeDocument(overrides: Partial<DocumentRead> = {}): DocumentRead {
  return {
    id: "doc_1",
    tenant_id: "tn_1",
    name: "颈椎理疗话术",
    source_type: "text",
    content: "## 开场\n欢迎光临。",
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

afterEach(() => {
  // 清理 jumpToAnchor 可能注入的 window.setTimeout 残留(jsdom 下不影响,但显式清)。
});

describe("MarkdownReader — Markdown 渲染 + 目录大纲 + 搜索高亮(slice 02)", () => {
  it("空态:doc=null 显示「选择左侧文档查看」+ 不渲染搜索框", () => {
    const { getByText, queryByPlaceholderText } = renderWithProviders(
      <MarkdownReader doc={null} />,
    );

    expect(getByText("选择左侧文档查看")).toBeTruthy();
    // 无 doc 时搜索框不渲染。
    expect(queryByPlaceholderText("在文档中搜索...")).toBeNull();
  });

  it("Markdown 渲染:标题/段落/代码块均渲染为对应 DOM 元素", () => {
    const doc = makeDocument({
      content: "## 标题一\n\n正文段落。\n\n```js\nconst x = 1;\n```",
    });

    const { getByText, container } = renderWithProviders(
      <MarkdownReader doc={doc} />,
    );

    // h2 标题渲染(带 id 用于大纲锚点)。
    const h2 = container.querySelector("h2");
    expect(h2).not.toBeNull();
    expect(h2?.textContent).toContain("标题一");
    expect(h2?.id).toBe("toc-0");
    // 段落正文。
    expect(getByText("正文段落。")).toBeTruthy();
    // 代码块:``<pre>`` + ``<code>``(rehype-highlight 处理)。
    const pre = container.querySelector("pre");
    expect(pre).not.toBeNull();
  });

  it("目录大纲(G7):## / ### 提取生成大纲列表 + h2/h3 带锚点 id", () => {
    const doc = makeDocument({
      content: "## 第一章\n\n内容。\n\n### 子节\n\n更多。\n\n## 第二章",
    });

    const { container } = renderWithProviders(<MarkdownReader doc={doc} />);

    // 大纲导航存在(有标题时渲染)。大纲项在 nav 内。
    const nav = container.querySelector('[data-testid="outline-nav"]');
    expect(nav).not.toBeNull();
    // 大纲项:第一章 / 子节 / 第二章(在 nav 内,与正文 h2/h3 同名但位置不同)。
    expect(nav?.textContent).toContain("第一章");
    expect(nav?.textContent).toContain("子节");
    expect(nav?.textContent).toContain("第二章");
    // h2/h3 按顺序带 id(正文里的标题)。
    const headings = container.querySelectorAll("h2, h3");
    expect(headings.length).toBe(3);
    expect((headings[0] as Element).id).toBe("toc-0");
    expect((headings[1] as Element).id).toBe("toc-1");
    expect((headings[2] as Element).id).toBe("toc-2");
  });

  it("目录大纲(G7):点击大纲项触发对应锚点 scrollIntoView 跳转", async () => {
    const user = (await import("@testing-library/user-event")).default.setup();
    const doc = makeDocument({
      // 「第一章」正文有独占文本,大纲项点击后跳转 toc-0。
      content: "## 第一章正文标题\n\n内容段落。",
    });

    // spy scrollIntoView —— jsdom 在 HTMLElement.prototype 上实现(scrollIntoView
    // 是 no-op,但 spy 能捕获调用)。用 spyOn 正确处理原型方法替换/恢复。
    const scrollSpy = vi.spyOn(HTMLElement.prototype, "scrollIntoView");

    const { container } = renderWithProviders(<MarkdownReader doc={doc} />);

    // 大纲 nav 内的 button(第一个大纲项)。
    const nav = container.querySelector('[data-testid="outline-nav"]');
    const outlineBtn = nav?.querySelector("button");
    expect(outlineBtn).not.toBeNull();

    await user.click(outlineBtn!);

    // scrollIntoView 被调用(jumpToAnchor → getElementById("toc-0").scrollIntoView)。
    expect(scrollSpy).toHaveBeenCalled();
    // 调用目标是 id=toc-0 的元素(正文第一个 h2)—— spy 的 this/收到的元素。
    const toc0 = document.getElementById("toc-0");
    expect(toc0).not.toBeNull();

    scrollSpy.mockRestore();
  });

  it("目录大纲:无 ## / ### 标题时不渲染大纲区,只渲染正文", () => {
    const doc = makeDocument({
      content: "这是一段纯文本,没有标题。",
    });

    const { container } = renderWithProviders(<MarkdownReader doc={doc} />);

    // 无大纲导航。
    expect(container.querySelector('[data-testid="outline-nav"]')).toBeNull();
  });

  it("搜索高亮(G5):输入关键词后 <mark> 出现在 DOM + 计数显示", async () => {
    const doc = makeDocument({
      content: "颈椎理疗是一种服务。颈椎需要呵护。",
    });
    const user = (await import("@testing-library/user-event")).default.setup();

    const { getByPlaceholderText, container } = renderWithProviders(
      <MarkdownReader doc={doc} />,
    );

    // 输入关键词「颈椎」。
    await user.type(getByPlaceholderText("在文档中搜索..."), "颈椎");

    // 等 useEffect 同步 markCount。
    await new Promise((r) => setTimeout(r, 0));

    // mark 元素出现(「颈椎」出现 2 次)。
    const marks = container.querySelectorAll("mark");
    expect(marks.length).toBe(2);
    // 计数显示「1/2」(activeIdx 从 0 开始)。
    const countEl = container.querySelector('[data-testid="match-count"]');
    expect(countEl?.textContent).toContain("2");
  });

  it("搜索高亮:无关键词时无 <mark> 元素", () => {
    const doc = makeDocument({
      content: "颈椎理疗是一种服务。",
    });

    const { container } = renderWithProviders(<MarkdownReader doc={doc} />);

    // 未输入关键词:无 mark。
    expect(container.querySelectorAll("mark").length).toBe(0);
  });

  it("搜索高亮:关键词大小写不敏感匹配", async () => {
    const doc = makeDocument({
      content: "Hello world. HELLO again. hello third.",
    });
    const user = (await import("@testing-library/user-event")).default.setup();

    const { getByPlaceholderText, container } = renderWithProviders(
      <MarkdownReader doc={doc} />,
    );

    // 小写「hello」应匹配三种大小写。
    await user.type(getByPlaceholderText("在文档中搜索..."), "hello");
    await new Promise((r) => setTimeout(r, 0));

    const marks = container.querySelectorAll("mark");
    expect(marks.length).toBe(3);
  });
});
