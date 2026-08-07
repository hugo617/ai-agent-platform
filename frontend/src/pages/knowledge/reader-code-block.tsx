/**
 * knowledge/ reader-code-block — 阅读器代码块 copy 按钮(reader-ui slice 02)。
 *
 * 从 ``components/chat/markdown-view.tsx`` 镜像 CodeBlockCopy(逻辑零变化),作为
 * 阅读器 MarkdownReader 的 ``components.pre`` 渲染的 copy 按钮副本。不直接复用
 * chat 版本 —— 那是 chat 模块的内部组件(未 export),且阅读器与 chat 的 components
 * 对象各自持有;两份 CodeBlockCopy 是纯 locality 副本(slice 03 若评估合并再抽共享,
 * 本片不预抽 —— 避免为还不明确的共用点提前跨模块抽象)。
 */
import { useState } from "react";
import { Check, Copy } from "lucide-react";

export function CodeBlockCopy({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard 可能在非安全上下文不可用;静默失败。
    }
  };
  return (
    <button
      type="button"
      onClick={handleCopy}
      title="复制代码"
      className="absolute right-2 top-2 inline-flex h-7 w-7 items-center justify-center rounded text-zinc-400 opacity-0 transition-opacity hover:bg-zinc-700 hover:text-zinc-100 group-hover:opacity-100"
    >
      {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  );
}
