import { useState } from "react";
import { useNavigate } from "react-router-dom";
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
import { devLogin } from "@/api/endpoints";

/**
 * Login page.
 *
 * Two login paths:
 *   1. (Dev) One-click dev login — calls /dev/bootstrap + /dev/token on the
 *      backend, which mints a real RS256 JWT validated through the same code
 *      path as Logto tokens. Works without Logto configured.
 *   2. (Manual) Paste an existing access token (Logto-issued or otherwise).
 */
export function LoginPage() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const [devLoading, setDevLoading] = useState(false);
  const [token, setToken] = useState("");

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

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/30 px-4">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1">
          <CardTitle className="text-2xl">登录权限控制台</CardTitle>
          <CardDescription>
            选择开发登录快速进入，或粘贴 access token。
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Path 1: one-click dev login */}
          <div className="space-y-3">
            <Button
              onClick={handleDevLogin}
              disabled={devLoading}
              className="w-full"
              size="lg"
            >
              {devLoading ? "登录中…" : "🚀 一键开发登录"}
            </Button>
            <p className="text-xs text-muted-foreground">
              使用内置开发账号（dev-user）登录，自动创建租户并签发 JWT。
              无需配置 Logto，适合本地开发。
            </p>
          </div>

          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <span className="w-full border-t" />
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-card px-2 text-muted-foreground">或</span>
            </div>
          </div>

          {/* Path 2: paste token */}
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
  );
}
