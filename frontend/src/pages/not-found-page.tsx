import { Link } from "react-router-dom";
import { Home } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * 404 page — polished but restrained.
 *
 * The revamp plan calls for "大字号 404 + 装饰背景(克制用 Aceternity aurora-
 * background) + 返回首页 CTA". We skip the full aurora-background (heavy SVG
 * animation) and instead use a token-driven radial gradient glow — enough to
 * give the page presence without a continuous animation (motion budget is
 * reserved for the 4 sanctioned use cases).
 */
export function NotFoundPage() {
  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden px-6 text-center">
      {/* subtle decorative glow — two soft radial blobs in primary/muted,
          token-driven so it tracks theme + tenant white-label. */}
      <div
        className="pointer-events-none absolute inset-0 -z-10 opacity-40"
        style={{
          background:
            "radial-gradient(circle at 30% 30%, hsl(var(--primary) / 0.15) 0, transparent 45%), radial-gradient(circle at 70% 70%, hsl(var(--muted)) 0, transparent 40%)",
        }}
      />

      <p className="text-[10rem] font-bold leading-none tracking-tighter text-primary/20 sm:text-[14rem]">
        404
      </p>
      <h1 className="-mt-6 text-2xl font-bold tracking-tight">页面走丢了</h1>
      <p className="mt-2 max-w-sm text-sm text-muted-foreground">
        你访问的页面不存在或已被移除。检查地址是否正确，或返回首页继续。
      </p>
      <div className="mt-8 flex items-center gap-3">
        <Link to="/">
          <Button>
            <Home className="mr-2 h-4 w-4" /> 返回首页
          </Button>
        </Link>
        <Link to="/chat">
          <Button variant="outline">去对话</Button>
        </Link>
      </div>
    </div>
  );
}
