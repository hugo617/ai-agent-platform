import { useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { Check, Copy } from "lucide-react";

// highlight.js github-dark theme — code blocks render on a fixed dark background
// (see <pre> className below), consistent across light/dark app modes (à la
// ChatGPT). Importing once here keeps the theme co-located with the renderer.
import "highlight.js/styles/github-dark.css";

/**
 * A small "copy" button overlay for fenced code blocks. Extracted so each code
 * block keeps its own copied-state without re-rendering the whole message.
 */
function CodeBlockCopy({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard may be unavailable (insecure context); fail silently
    }
  };
  return (
    <button
      type="button"
      onClick={handleCopy}
      title="复制代码"
      className="absolute right-2 top-2 inline-flex h-7 w-7 items-center justify-center rounded text-zinc-400 opacity-0 transition-opacity hover:bg-zinc-700 hover:text-zinc-100 group-hover:opacity-100"
    >
      {copied ? (
        <Check className="h-3.5 w-3.5" />
      ) : (
        <Copy className="h-3.5 w-3.5" />
      )}
    </button>
  );
}

/**
 * Render assistant message content as GFM Markdown with syntax-highlighted code
 * blocks. User messages stay plain text (see chat-page) — only assistant output
 * goes through here, so user input is never parsed as Markdown (no injection).
 *
 * Streaming-safe: react-markdown re-parses on each `content` change; message
 * bodies are small (<2KB typically) so re-rendering per delta is fine.
 *
 * Security: react-markdown does NOT render raw HTML by default (no rehype-raw),
 * so `<script>` in model output is escaped to text. Links open in a new tab.
 */
export function MarkdownView({ content }: { content: string }) {
  return (
    <div className="prose prose-sm max-w-none break-words dark:prose-invert prose-pre:bg-transparent prose-pre:p-0 prose-code:before:content-none prose-code:after:content-none">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{
          // Fenced code blocks: wrap in a relative container with a copy button.
          // `node` is unused but required by react-markdown's component signature.
          pre({ children }: { node?: unknown; children?: ReactNode }) {
            // Extract the raw text from the nested <code> child for copying.
            const text = extractText(children);
            return (
              <div className="group relative my-3 overflow-hidden rounded-md bg-zinc-900">
                <CodeBlockCopy code={text} />
                <pre className="overflow-x-auto p-4 text-xs leading-relaxed">
                  {children}
                </pre>
              </div>
            );
          },
          code({
            className,
            children,
            ...props
          }: {
            className?: string;
            children?: ReactNode;
            node?: unknown;
          }) {
            // Inline code (no language class) gets a subtle background; block
            // code is handled by <pre> above and left untouched here.
            const isBlock = /language-/.test(className ?? "");
            if (isBlock) {
              return (
                <code className={className} {...props}>
                  {children}
                </code>
              );
            }
            return (
              <code
                className="rounded bg-muted px-1.5 py-0.5 text-[0.85em]"
                {...props}
              >
                {children}
              </code>
            );
          },
          a({ children, ...props }: { node?: unknown; children?: ReactNode }) {
            return (
              <a {...props} target="_blank" rel="noopener noreferrer">
                {children}
              </a>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

/**
 * Walk the React node tree of a <pre>'s children and collect the raw string
 * content of the nested <code> element. Used to populate the copy button.
 */
function extractText(node: ReactNode): string {
  if (node == null || node === false) return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(extractText).join("");
  // React element: descend into its children.
  if (typeof node === "object" && "props" in node) {
    const props = (node as { props: { children?: ReactNode } }).props;
    return extractText(props.children);
  }
  return "";
}
