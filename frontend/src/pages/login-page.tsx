import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/components/auth/auth-context";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/toast";
import { apiErrorMessage } from "@/api/client";

/**
 * Login page.
 *
 * MVP auth = dev token entry. The user pastes a Bearer token (e.g. issued by
 * Logto or minted for testing) and we store it. The real Logto OIDC redirect
 * flow is a TODO and the integration point is marked below.
 */
export function LoginPage() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const [token, setToken] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
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
          <CardTitle className="text-2xl">登录</CardTitle>
          <CardDescription>
            输入后端签发的 access token 以继续。生产环境将通过 Logto 自动获取。
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="token">Access Token</Label>
              <Input
                id="token"
                type="password"
                placeholder="粘贴你的 Bearer token"
                value={token}
                onChange={(e) => setToken(e.target.value)}
              />
            </div>
            <Button type="submit" className="w-full">
              登录
            </Button>

            {/* TODO: Logto OIDC integration point.
                Replace the manual token flow above with:
                <LogtoProvider ...>
                  <button onClick={() => logtoClient.signIn(callbackUri)}>
                    使用 Logto 登录
                  </button>
                </LogtoProvider>
            */}

            <div className="rounded-md border border-dashed bg-muted/40 p-3 text-xs text-muted-foreground">
              <p className="font-medium text-foreground">开发模式说明</p>
              <p className="mt-1">
                当前为 MVP 阶段：在输入框粘贴后端签发的 JWT access token。
                Logto 对接完成后此页将自动跳转到 Logto 登录页。
              </p>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
