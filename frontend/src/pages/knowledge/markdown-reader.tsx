/**
 * knowledge/ markdown-reader — 右栏 Markdown 阅读器(reader-ui slice 02)。
 *
 * 纯渲染组件(plan G1 右栏例外):接收 ``doc: DocumentRead | null`` prop,不自调
 * hook(内容已在 doc.content 里,由 DocumentList 选中下传,避免重复请求)。
 *
 * 三大能力(承接 plan §4.5 G5/G7 + 切片 02 AC3-5):
 *   1. Markdown 渲染:react-markdown + remark-gfm + rehype-highlight(对齐
 *      ``components/chat/markdown-view.tsx`` 范式,但不复用该组件 —— 阅读器需要
 *      目录大纲 + 搜索高亮的自定义 components,与 chat 的 copy-button 范式不同)。
 *   2. 目录大纲(G7):渲染前正则 ``/^(#{2,3})\s+(.+)$/gm`` 提取 ## / ### 标题,
 *      生成大纲列表;react-markdown ``components.h2/h3`` render 时给标题加
 *      ``id={anchor}``;点大纲项 → ``getElementById(anchor).scrollIntoView``。
 *   3. 搜索高亮(G5):顶部搜索框 + 关键词 state;在文本容器元素(p/li/strong/em/
 *      td/h2-h6 等)的 components 自定义 render 里把直接字符串片段拆「前 +
 *      ``<mark>`` + 后」;高亮计数(「N/M」)+ 上一个/下一个按钮 → 用 container ref
 *      ``querySelectorAll('mark')`` 收集所有命中 + ``scrollIntoView`` 跳转。关键词空
 *      时正常渲染无 ``<mark>``。**不引新依赖**(用现有 react-markdown components,
 *      不加 rehype/remark 插件)。
 *
 * 空态(doc=null):显示「选择左侧文档查看」占位(切片 02 AC3)。
 *
 * ⚠️ G5 实现细节:react-markdown v10 的 ``components.text`` 不拦截 hast text 节点
 * (实测无效),故改在文本容器元素的 render 里对 children 的直接字符串片段做拆分
 * (见 buildComponents 注释)。仍用 react-markdown components 自定义 render + ``<mark>``,
 * 不引新依赖;偏离仅是实现层「text key → 文本容器 key」,行为等价。
 */
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { ChevronDown, ChevronUp, FileText, Search } from "lucide-react";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { DocumentRead } from "@/api/types";
import { cn } from "@/lib/utils";

// highlight.js github-dark 主题(对齐 components/chat/markdown-view.tsx,代码块
// 固定深色背景,light/dark 模式一致)。在此 import 一次,与渲染器同置。
import "highlight.js/styles/github-dark.css";

// 代码块 copy 按钮(从 chat/markdown-view.tsx 镜像,逻辑零变化)。不直接 import
// chat 版本 —— 那是 chat 模块内部组件(未 export);两份是纯 locality 副本(slice 03
// 若评估合并再抽,本片不预抽)。
import { CodeBlockCopy } from "./reader-code-block";

export interface MarkdownReaderProps {
  doc: DocumentRead | null;
}

// 大纲项:level 2/3 + 文本 + 锚点 id(用于 scrollIntoView 跳转)。
interface OutlineItem {
  level: 2 | 3;
  text: string;
  anchor: string;
}

export function MarkdownReader({ doc }: MarkdownReaderProps) {
  // 搜索关键词(trim 后;大小写不敏感匹配,比对用 lowerQuery)。空串 = 无高亮。
  const [query, setQuery] = useState("");
  const trimmed = query.trim();
  const lowerQuery = trimmed.toLowerCase();

  // 当前高亮命中索引(用于上/下跳转 + 计数显示「N/M」)。
  const [activeIdx, setActiveIdx] = useState(0);
  // 本次渲染的匹配总数(由 useEffect 在 react-markdown 渲染后从 DOM 统计)。
  const [matchCount, setMatchCount] = useState(0);

  // 正文容器 ref —— 用于 querySelectorAll('mark') 收集命中元素(G5 跳转 + 计数)。
  // 比 callback-ref 收集更健壮(不受 react-markdown 子树重挂载顺序影响),且测试
  // 友好(getByTestId 容器后 querySelectorAll 直接断言)。
  const bodyRef = useRef<HTMLDivElement>(null);

  // 目录大纲:正则提取 ## / ### 标题(G7)。doc 变化时重算(用 useMemo 缓存)。
  // anchor 用「toc-<序号>」而非 slugify —— slugify 对中文/特殊字符需额外处理,
  // 且同一标题重复时 slug 冲突;序号法稳定唯一,跳转靠 getElementById 序号匹配。
  const outline = useMemo<OutlineItem[]>(() => {
    if (!doc) return [];
    return extractOutline(doc.content);
  }, [doc]);

  // 关键词变化时重置 activeIdx(避免索引越界新匹配数)。
  const handleQueryChange = (value: string) => {
    setQuery(value);
    setActiveIdx(0);
  };

  // 渲染后从 DOM 统计 mark 数 + 同步 matchCount。依赖 trimmed(关键词)+ doc
  // (内容变化重算)。ReactMarkdown 用 key={trimmed} 保证关键词变化时重挂载。
  useEffect(() => {
    const marks = bodyRef.current?.querySelectorAll("mark") ?? [];
    setMatchCount(marks.length);
    if (activeIdx >= marks.length && marks.length > 0) {
      setActiveIdx(0);
    }
  }, [trimmed, doc, activeIdx]);

  const jumpTo = (idx: number) => {
    const marks = bodyRef.current?.querySelectorAll("mark") ?? [];
    if (marks.length === 0) return;
    // 环形跳转:超过末尾回 0,小于 0 回末尾(对齐浏览器 Ctrl+F 直觉)。
    const wrapped = ((idx % marks.length) + marks.length) % marks.length;
    setActiveIdx(wrapped);
    marks[wrapped]?.scrollIntoView({ behavior: "smooth", block: "center" });
    marks[wrapped]?.classList.add("ring-2", "ring-ring");
    // ring 高亮短暂提示当前命中(500ms 后移除,避免堆积)。
    window.setTimeout(
      () => marks[wrapped]?.classList.remove("ring-2", "ring-ring"),
      500,
    );
  };

  return (
    <Card className="flex h-full flex-col">
      <CardHeader>
        <CardTitle className="text-sm">{doc ? doc.name : "阅读器"}</CardTitle>
        {doc && (
          <div className="flex flex-col gap-2">
            {/* 搜索框 + 计数 + 上下跳转(G5)。关键词空时只显示搜索框,无计数/按钮。 */}
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={query}
                  onChange={(e) => handleQueryChange(e.target.value)}
                  placeholder="在文档中搜索..."
                  className="pl-9"
                  aria-label="文档内搜索"
                />
              </div>
              {trimmed && (
                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                  <span className="tabular-nums" data-testid="match-count">
                    {matchCount === 0
                      ? "0/0"
                      : `${Math.min(activeIdx + 1, matchCount)}/${matchCount}`}
                  </span>
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-7 w-7"
                    onClick={() => jumpTo(activeIdx - 1)}
                    aria-label="上一个匹配"
                    disabled={matchCount === 0}
                  >
                    <ChevronUp className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-7 w-7"
                    onClick={() => jumpTo(activeIdx + 1)}
                    aria-label="下一个匹配"
                    disabled={matchCount === 0}
                  >
                    <ChevronDown className="h-4 w-4" />
                  </Button>
                </div>
              )}
            </div>
          </div>
        )}
      </CardHeader>
      <CardContent className="flex-1 overflow-y-auto">
        {!doc ? (
          <div className="flex flex-col items-center gap-3 py-12 text-center">
            <FileText className="h-10 w-10 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">选择左侧文档查看</p>
          </div>
        ) : (
          <div className="grid gap-4 lg:grid-cols-[180px_minmax(0,1fr)]">
            {/* 目录大纲(G7):左小栏(仅 lg+ 显示,窄屏隐藏免挤)。无标题时整栏不渲染。 */}
            {outline.length > 0 && (
              <nav
                className="hidden lg:block"
                aria-label="文档目录"
                data-testid="outline-nav"
              >
                <p className="mb-2 text-xs font-medium text-muted-foreground">
                  目录
                </p>
                <ul className="space-y-1 border-l border-border pl-2">
                  {outline.map((item) => (
                    <li key={item.anchor}>
                      <button
                        type="button"
                        onClick={() => jumpToAnchor(item.anchor)}
                        className={cn(
                          "block w-full text-left text-xs transition-colors hover:text-primary",
                          item.level === 3
                            ? "pl-3 text-muted-foreground"
                            : "font-medium",
                        )}
                      >
                        {item.text}
                      </button>
                    </li>
                  ))}
                </ul>
              </nav>
            )}

            {/* Markdown 正文(G5 搜索高亮 + G7 标题锚点)。key={trimmed} 让关键词
                变化时重挂载(useEffect 重新统计 mark 数)。bodyRef 收集 mark 跳转。 */}
            <div
              ref={bodyRef}
              className="prose prose-sm max-w-none break-words dark:prose-invert prose-pre:bg-transparent prose-pre:p-0 prose-code:before:content-none prose-code:after:content-none"
              data-testid="markdown-body"
            >
              <ReactMarkdown
                key={trimmed}
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeHighlight]}
                components={buildComponents(trimmed, lowerQuery, outline)}
              >
                {doc.content}
              </ReactMarkdown>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ---- 目录大纲提取(G7)----
// 正则 ``/^(#{2,3})\s+(.+)$/gm``:匹配行首 ## 或 ### + 空格 + 标题文本(g 标志
// 全文匹配 + m 标志跨行)。h1(#)不进大纲(避免冗余 —— 文档名已是 h1 级别在 CardTitle)。
// anchor = ``toc-<出现序号>``,稳定唯一(见上方 useMemo 注释)。
const HEADING_RE = /^(#{2,3})\s+(.+)$/gm;

function extractOutline(content: string): OutlineItem[] {
  const items: OutlineItem[] = [];
  let match: RegExpExecArray | null;
  HEADING_RE.lastIndex = 0; // g 标志正则复用前重置
  let i = 0;
  while ((match = HEADING_RE.exec(content)) !== null) {
    const hashes = match[1];
    const text = match[2].trim();
    if (!text) continue;
    items.push({
      level: (hashes.length as 2 | 3),
      text,
      anchor: `toc-${i}`,
    });
    i++;
  }
  return items;
}

function jumpToAnchor(anchor: string) {
  document
    .getElementById(anchor)
    ?.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---- react-markdown components 构建(G5 搜索高亮 + G7 标题锚点)----
// 每次渲染重建(闭包捕获 query / outline)。outline 用于给 h2/h3 匹配锚点(按出现
// 顺序 —— 与 extractOutline 同序,故 components 渲染时第 n 个 h2/h3 对应 outline[n])。
// 用计数器 headingIdx 跟踪当前渲染到第几个标题,取对应 outline[headingIdx++]。
//
// ⚠️ G5 搜索高亮策略说明:react-markdown v10 的 ``components.text`` 不拦截
// hast text 节点(文本经父元素直接渲染,``text`` key 无效 —— 实测 ``<mark>`` 不
// 出现)。故在**文本容器元素**(p / li / strong / em / td / th / h2-h6 / blockquote /
// a)的 render 里,只对 children 中**直接的字符串片段**做关键词拆分:react-markdown
// 渲染 ``<p>`` 时 children 通常是 ``[string, <a>, string, ...]`` 交错数组,字符串段
// 拆成 ``<mark>`` + ``<span>``,React 元素段(<a>/<strong>)原样保留 —— 其内部文本
// 由该元素自己的 component render 再处理(对 strong/em/a/td 等均注册了 render)。
// 这样只处理顶层字符串,无需递归遍历 React 元素树,简洁可靠。
// 仍用 react-markdown components 自定义 render + ``<mark>``,**不引新依赖**
// (符合 plan G5 精神;偏离仅是「text key → 文本容器 key」,实现层调整,行为等价)。
const TEXT_CONTAINERS = [
  "p",
  "li",
  "strong",
  "em",
  "td",
  "th",
  "h4",
  "h5",
  "h6",
  "blockquote",
] as const;

function buildComponents(
  trimmed: string,
  lowerQuery: string,
  outline: OutlineItem[],
) {
  // 标题渲染计数:h2/h3 按顺序对应 outline(同序)。
  let headingIdx = 0;

  // 文本容器高亮 render:遍历 children,对**直接字符串片段**做关键词拆分。
  // React 元素片段(<a>/<strong> 等)保留 —— 其内部文本由该元素自己的 component
  // render 再处理(本函数对 strong/em/a/td 等均注册了 render)。
  const highlightRender = ({
    children,
  }: {
    node?: unknown;
    children?: ReactNode;
  }) => <>{trimmed ? highlightStrings(children, lowerQuery) : children}</>;

  const components: Record<
    string,
    (props: { node?: unknown; children?: ReactNode; [k: string]: unknown }) => ReactNode
  > = {};

  // G7 标题锚点:h2/h3 加 id,与 outline 顺序一一对应。h2/h3 的文本也可被搜索高亮。
  components.h2 = ({ children }) => {
    const id = outline[headingIdx++]?.anchor;
    return (
      <h2 id={id} className="scroll-mt-4">
        {trimmed ? highlightStrings(children, lowerQuery) : children}
      </h2>
    );
  };
  components.h3 = ({ children }) => {
    const id = outline[headingIdx++]?.anchor;
    return (
      <h3 id={id} className="scroll-mt-4">
        {trimmed ? highlightStrings(children, lowerQuery) : children}
      </h3>
    );
  };

  // 文本容器元素注册高亮 render。
  for (const tag of TEXT_CONTAINERS) {
    components[tag] = highlightRender;
  }

  // 代码块:镜像 chat/markdown-view.tsx 的 pre/code 范式(深色背景 + copy 按钮)。
  components.pre = ({ children }) => {
    const text = extractText(children);
    return (
      <div className="group relative my-3 overflow-hidden rounded-md bg-zinc-900">
        <CodeBlockCopy code={text} />
        <pre className="overflow-x-auto p-4 text-xs leading-relaxed">
          {children}
        </pre>
      </div>
    );
  };
  components.code = ({
    className,
    children,
    ...props
  }: {
    className?: string;
    children?: ReactNode;
    node?: unknown;
    [k: string]: unknown;
  }) => {
    const isBlock = /language-/.test(className ?? "");
    if (isBlock) {
      return (
        <code className={className} {...props}>
          {children}
        </code>
      );
    }
    return (
      <code className="rounded bg-muted px-1.5 py-0.5 text-[0.85em]" {...props}>
        {children}
      </code>
    );
  };
  components.a = ({ children, ...props }) => (
    <a {...props} target="_blank" rel="noopener noreferrer">
      {trimmed ? highlightStrings(children, lowerQuery) : children}
    </a>
  );

  return components;
}

// ---- 搜索高亮 helper(G5)----
// 遍历 children:只对**直接字符串片段**做关键词拆分,React 元素原样保留。
// react-markdown 的 p/li/td 等 children 通常是 ``[string, <a>, string]`` 交错,
// 故只处理顶层字符串即可覆盖绝大多数正文(嵌套的 <strong>/<a> 内文本由其各自
// component render 调本 helper 再处理)。关键词为空时调用方已短路。
function highlightStrings(node: ReactNode, lowerQuery: string): ReactNode {
  if (node == null || node === false) return node;
  if (typeof node === "string") {
    return splitHighlightToReact(node, lowerQuery);
  }
  if (typeof node === "number") return node;
  if (Array.isArray(node)) {
    // 数组:逐项处理,字符串项拆分,元素项保留(保留元素原 key 若有)。
    return node.map((child, i) => {
      if (typeof child === "string") {
        return splitHighlightToReact(child, lowerQuery, i);
      }
      return child;
    });
  }
  // React 元素:原样返回(其内部文本由该元素的 component render 处理)。
  return node;
}

// 纯字符串 → ReactNode 数组(关键词拆分,大小写不敏感)。baseKey 用于数组项 key 命名。
function splitHighlightToReact(
  text: string,
  lowerQuery: string,
  baseKey?: number,
): ReactNode {
  if (!text.toLowerCase().includes(lowerQuery)) return text;
  const parts = splitHighlight(text, lowerQuery);
  return parts.map((part, i) => {
    const key = baseKey != null ? `${baseKey}-${i}` : i;
    return part.match ? (
      <mark key={key} className="rounded bg-warning/40 px-0.5">
        {part.text}
      </mark>
    ) : (
      <span key={key}>{part.text}</span>
    );
  });
}

// 按关键词拆分文本(大小写不敏感)。返回段数组,每段标 match: boolean。
function splitHighlight(
  text: string,
  lowerQuery: string,
): { text: string; match: boolean }[] {
  const parts: { text: string; match: boolean }[] = [];
  const lower = text.toLowerCase();
  let i = 0;
  while (i < text.length) {
    const found = lower.indexOf(lowerQuery, i);
    if (found === -1) {
      parts.push({ text: text.slice(i), match: false });
      break;
    }
    if (found > i) {
      parts.push({ text: text.slice(i, found), match: false });
    }
    parts.push({
      text: text.slice(found, found + lowerQuery.length),
      match: true,
    });
    i = found + lowerQuery.length;
  }
  return parts;
}

/** 遍历 <pre> 的 React children 收集嵌套 <code> 的纯文本(用于 copy 按钮)。 */
function extractText(node: ReactNode): string {
  if (node == null || node === false) return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(extractText).join("");
  if (typeof node === "object" && "props" in node) {
    const props = (node as { props: { children?: ReactNode } }).props;
    return extractText(props.children);
  }
  return "";
}
