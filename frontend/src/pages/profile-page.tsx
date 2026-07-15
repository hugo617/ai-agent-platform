import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { MessageSquare, User as UserIcon } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { FormField as Field } from "@/components/ui/form-field";
import { useToast } from "@/components/ui/toast";
import { apiErrorMessage } from "@/api/client";
import { useAuth } from "@/components/auth/auth-context";
import {
  useChangePassword,
  useConversations,
  useUpdateMe,
} from "@/hooks/queries";
import { formatDateTime as fmt } from "@/lib/format";

/**
 * 个人中心 — self-service account management.
 *
 * Three cards:
 *   1. 资料编辑 — display_name / real_name / phone (PUT /auth/me)
 *   2. 修改密码 — verify old → set new (PUT /auth/me/password)
 *   3. 我的会话 — recent conversations with a link to /chat
 *
 * No permission guard: every authenticated user manages their own account.
 */
export function ProfilePage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">个人中心</h1>
        <p className="text-muted-foreground">
          管理你的账号资料、密码，并查看最近的会话记录。
        </p>
      </div>

      <ProfileCard />
      <PasswordCard />
      <SessionsCard />
    </div>
  );
}

// --------------------------------------------------------------- 资料编辑

// Only editable profile columns — platform_role/status/username are not here
// (the backend ignores them too, so smuggling them in is a no-op).
const profileSchema = z.object({
  display_name: z.string().max(128).optional(),
  real_name: z.string().max(100).optional(),
  phone: z.string().max(20).optional(),
});
type ProfileFormValues = z.infer<typeof profileSchema>;

function ProfileCard() {
  const { me } = useAuth();
  const toast = useToast();
  const updateMut = useUpdateMe();

  const form = useForm<ProfileFormValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: {
      // The /me response does not carry profile fields, so the inputs start
      // blank and only send what the user types (omit = leave unchanged).
      display_name: "",
      real_name: "",
      phone: "",
    },
  });

  const onSubmit = async (values: ProfileFormValues) => {
    // Drop empty strings so we don't clobber existing values with blanks.
    const payload = {
      display_name: values.display_name?.trim() || undefined,
      real_name: values.real_name?.trim() || undefined,
      phone: values.phone?.trim() || undefined,
    };
    if (!payload.display_name && !payload.real_name && !payload.phone) {
      toast.error("请至少填写一项");
      return;
    }
    try {
      await updateMut.mutateAsync(payload);
      toast.success("资料已更新");
      form.reset({ display_name: "", real_name: "", phone: "" });
    } catch (err) {
      toast.error("保存失败", apiErrorMessage(err));
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <UserIcon className="h-5 w-5" /> 资料编辑
        </CardTitle>
        <CardDescription>
          修改你在本平台的个人资料。留空的字段不会被修改。
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="账号" hint="登录账号，不可自行修改">
              <Input value={me?.email ?? me?.user_id ?? ""} readOnly disabled />
            </Field>
            <Field label="显示昵称">
              <Input
                placeholder="设置显示昵称"
                {...form.register("display_name")}
              />
            </Field>
            <Field label="真实姓名">
              <Input placeholder="真实姓名" {...form.register("real_name")} />
            </Field>
            <Field label="手机号">
              <Input placeholder="手机号" {...form.register("phone")} />
            </Field>
          </div>
          <Button type="submit" disabled={updateMut.isPending}>
            {updateMut.isPending ? "保存中…" : "保存资料"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

// --------------------------------------------------------------- 修改密码

const passwordSchema = z
  .object({
    old_password: z.string().min(1, "请输入当前密码"),
    new_password: z.string().min(8, "新密码至少 8 位"),
    confirm: z.string().min(1, "请再次输入新密码"),
  })
  .refine((v) => v.new_password === v.confirm, {
    path: ["confirm"],
    message: "两次输入的新密码不一致",
  });
type PasswordFormValues = z.infer<typeof passwordSchema>;

function PasswordCard() {
  const toast = useToast();
  const changeMut = useChangePassword();

  const form = useForm<PasswordFormValues>({
    resolver: zodResolver(passwordSchema),
    defaultValues: { old_password: "", new_password: "", confirm: "" },
  });

  const onSubmit = async (values: PasswordFormValues) => {
    try {
      await changeMut.mutateAsync({
        old_password: values.old_password,
        new_password: values.new_password,
      });
      toast.success("密码已修改", "下次登录请使用新密码");
      form.reset({ old_password: "", new_password: "", confirm: "" });
    } catch (err) {
      toast.error("修改失败", apiErrorMessage(err));
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>修改密码</CardTitle>
        <CardDescription>
          需要先验证当前密码。OIDC（Logto）账号不在本平台托管密码，无法在此修改。
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
          <div className="grid gap-4 sm:max-w-md">
            <Field label="当前密码" error={form.formState.errors.old_password?.message}>
              <Input
                type="password"
                autoComplete="current-password"
                {...form.register("old_password")}
              />
            </Field>
            <Field label="新密码" error={form.formState.errors.new_password?.message}>
              <Input
                type="password"
                autoComplete="new-password"
                placeholder="至少 8 位"
                {...form.register("new_password")}
              />
            </Field>
            <Field label="确认新密码" error={form.formState.errors.confirm?.message}>
              <Input
                type="password"
                autoComplete="new-password"
                {...form.register("confirm")}
              />
            </Field>
          </div>
          <Button type="submit" disabled={changeMut.isPending}>
            {changeMut.isPending ? "修改中…" : "修改密码"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

// --------------------------------------------------------------- 我的会话

function SessionsCard() {
  const { data, isLoading } = useConversations();
  const navigate = useNavigate();
  const conversations = data ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MessageSquare className="h-5 w-5" /> 我的会话
        </CardTitle>
        <CardDescription>最近的对话记录。点击进入聊天继续。</CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="py-6 text-center text-sm text-muted-foreground">加载中…</p>
        ) : conversations.length === 0 ? (
          <div className="flex flex-col items-center gap-3 py-12 text-center">
            <MessageSquare className="h-10 w-10 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">还没有会话记录</p>
            <Button variant="outline" onClick={() => navigate("/chat")}>
              开始对话
            </Button>
          </div>
        ) : (
          <ul className="divide-y">
            {conversations.slice(0, 8).map((c) => (
              <li
                key={c.id}
                className="flex items-center justify-between gap-3 py-3"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {c.title || "未命名会话"}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {fmt(c.updated_at ?? c.created_at)}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => navigate("/chat")}
                >
                  继续
                </Button>
              </li>
            ))}
          </ul>
        )}
        {conversations.length > 0 && (
          <div className="mt-3 flex items-center justify-between">
            <Badge variant="secondary">共 {conversations.length} 条</Badge>
            <Button variant="link" onClick={() => navigate("/chat")}>
              查看全部
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// --------------------------------------------------------------- Field helper

// (FormField is imported from @/components/ui/form-field as `Field`.)
