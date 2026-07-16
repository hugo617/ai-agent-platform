import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bot, ShieldCheck, Sparkles, Zap } from "lucide-react";
import { useAuth } from "@/components/auth/auth-context";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/toast";
import { apiErrorMessage } from "@/api/client";
import { devLogin, login } from "@/api/endpoints";

/**
 * Login page.
 *
 * Three login paths:
 *   1. (Primary) Username/password — POST /auth/login, mints an HS256 JWT.
 *   2. (Dev) One-click dev login — calls /dev/bootstrap + /dev/token on the
 *      backend, which mints a real RS256 JWT validated through the same code
 *      path as Logto tokens. Works without Logto configured.
 *   3. (Manual) Paste an existing access token (Logto-issued or otherwise).
 */
export function LoginPage() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const [devLoading, setDevLoading] = useState(false);
  const [token, setToken] = useState("");

  // username/password form state
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [pwLoading, setPwLoading] = useState(false);

  const handleDevLogin = async () => {
    setDevLoading(true);
    try {
      const accessToken = await devLogin();
      signIn(accessToken);
      toast.success("登录成功", "已使用开发账号登录");
      navigate("/", { replace: true });
    } catch (err) {
      toast.error("开发登录失败", apiErrorMessage(err));
    } finally {
      setDevLoading(false);
    }
  };

  const handleTokenLogin = (e: React.FormEvent) => {
    e.preventDefault();
    if (!token.trim()) {
      toast.error("请输入 token");
      return;
    }
    try {
      signIn(token.trim());
      toast.success("登录成功");
      navigate("/", { replace: true });
    } catch (err) {
      toast.error("登录失败", apiErrorMessage(err));
    }
  };

  const handlePasswordLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!identifier.trim() || !password) {
      toast.error("请输入用户名/邮箱和密码");
      return;
    }
    setPwLoading(true);
    try {
      // The identifier could be a username or email — send both; the backend
      // matches either.
      const looksLikeEmail = identifier.includes("@");
      const res = await login(
        looksLikeEmail
          ? { email: identifier, password }
          : { username: identifier, password }
      );
      signIn(res.access_token);
      toast.success("登录成功");
      navigate("/", { replace: true });
    } catch (err) {
      toast.error("登录失败", apiErrorMessage(err));
    } finally {
      setPwLoading(false);
    }
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      {/* ---- left: brand panel (shadcn login-04 split) ----
          Hidden on small screens. A muted gradient surface with the product
          name, a one-line value prop, and three feature bullets. Kept restrained
          — no Aceternity background beams, just tokens + a couple of lucide
          icons to anchor the layout. */}
      <div className="relative hidden flex-col justify-between overflow-hidden bg-primary p-10 text-primary-foreground lg:flex">
        {/* subtle radial accent — token-driven so it tracks tenant white-label */}
        <div
          className="pointer-events-none absolute inset-0 opacity-20"
          style={{
            background:
              "radial-gradient(circle at 20% 20%, hsl(var(--primary-foreground)) 0, transparent 40%)",
          }}
        />
        <div className="relative flex items-center gap-2 text-lg font-semibold">
          <Bot className="h-6 w-6" />
          智能体云平台
        </div>
        <div className="relative space-y-6">
          <div className="space-y-3">
            <h2 className="text-3xl font-bold leading-tight">
              让 AI 智能体<br />服务你的每一线业务
            </h2>
            <p className="max-w-md text-sm text-primary-foreground/80">
              多租户、可编排、可检索知识库的 AI 智能体 SaaS 平台。
              从对话到编排，开箱即用。
            </p>
          </div>
          <div className="space-y-3 text-sm">
            {[
              { icon: Zap, text: "流式对话,毫秒级首字响应" },
              { icon: Sparkles, text: "Supervisor 多智能体编排" },
              { icon: ShieldCheck, text: "多租户 RBAC 权限隔离" },
            ].map((f) => (
              <div key={f.text} className="flex items-center gap-2.5">
                <f.icon className="h-4 w-4 shrink-0 opacity-90" />
                <span className="text-primary-foreground/90">{f.text}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="relative text-xs text-primary-foreground/60">
          © {new Date().getFullYear()} 智能体云平台
        </div>
      </div>

      {/* ---- right: form panel ---- */}
      <div className="flex items-center justify-center bg-muted/30 px-4 py-10">
        <Card className="w-full max-w-md">
          <CardHeader className="space-y-1">
            {/* compact brand mark on mobile (where the left panel is hidden) */}
            <div className="mb-1 flex items-center gap-2 text-base font-semibold lg:hidden">
              <Bot className="h-5 w-5 text-primary" />
              智能体云平台
            </div>
            <CardTitle className="text-2xl">登录</CardTitle>
            <CardDescription>
              使用账号密码登录；或使用一键开发登录、粘贴 access token。
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Path 1: username / password */}
            <form onSubmit={handlePasswordLogin} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="identifier">用户名 / 邮箱</Label>
                <Input
                  id="identifier"
                  data-testid="login-identifier"
                  placeholder="admin 或 admin@example.com"
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  autoFocus
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">密码</Label>
                <Input
                  id="password"
                  type="password"
                  data-testid="login-password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
              <Button
                type="submit"
                className="w-full"
                disabled={pwLoading}
                data-testid="login-submit"
              >
                {pwLoading ? "登录中…" : "登录"}
              </Button>
              <p className="text-xs text-muted-foreground">
                首次使用？运行{" "}
                <code className="rounded bg-muted px-1 py-0.5">
                  python scripts/init_admin.py
                </code>{" "}
                创建管理员账号。
              </p>
            </form>

            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <span className="w-full border-t" />
              </div>
              <div className="relative flex justify-center text-xs uppercase">
                <span className="bg-card px-2 text-muted-foreground">或</span>
              </div>
            </div>

            {/* Path 2: one-click dev login */}
            <div className="space-y-3">
              <Button
                onClick={handleDevLogin}
                disabled={devLoading}
                variant="secondary"
                className="w-full"
              >
                {devLoading ? "登录中…" : "🚀 一键开发登录"}
              </Button>
              <p className="text-xs text-muted-foreground">
                使用内置开发账号（dev-user）登录，无需配置 Logto，适合本地开发。
              </p>
            </div>

            {/* Path 3: paste token */}
            <form onSubmit={handleTokenLogin} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="token">Access Token</Label>
                <Input
                  id="token"
                  type="password"
                  placeholder="粘贴 Bearer token"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                />
              </div>
              <Button type="submit" variant="outline" className="w-full">
                使用 Token 登录
              </Button>
            </form>

            {/* TODO: Logto OIDC integration point.
                Replace the manual flows above with:
                <LogtoProvider ...>
                  <button onClick={() => logtoClient.signIn(callbackUri)}>
                    使用 Logto 登录
                  </button>
                </LogtoProvider>
            */}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
