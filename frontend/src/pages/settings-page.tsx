import { useState } from "react";
import {
  AlertTriangle,
  Copy,
  Check,
  Eye,
  EyeOff,
  KeyRound,
  Palette,
  Plus,
  Server,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { FileUpload } from "@/components/ui/file-upload";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { apiErrorMessage } from "@/api/client";
import { useAuth } from "@/components/auth/auth-context";
import { hasPermission } from "@/lib/permission";
import type {
  ApiToken,
  ApiTokenCreated,
  LlmConfig,
  LlmConfigUpdate,
} from "@/api/types";
import {
  useApiTokens,
  useCreateApiToken,
  usePlatformLlmConfig,
  useRevokeApiToken,
  useTenantConfig,
  useTenantLlmConfig,
  useUpdatePlatformLlmConfig,
  useUpdateTenantConfig,
  useUpdateTenantLlmConfig,
} from "@/hooks/queries";

export function SettingsPage() {
  const { me } = useAuth();
  const isSuperAdmin = me?.platform_role === "super_admin";
  // The tenant LLM card requires settings:update; the API Token card requires
  // api_tokens:read. Both gate on the caller's effective api permissions
  // (super_admin bypasses via hasPermission).
  const canManageLlm = hasPermission(me, "settings", "update");
  const canManageTokens = hasPermission(me, "api_tokens", "read");
  const canManage = canManageLlm || canManageTokens;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">设置</h1>
        <p className="text-muted-foreground">
          管理 LLM 提供商配置（API Key、Base URL、可用模型）与 API Token（供
          agenthub CLI 等外部 Agent 接入）。
        </p>
      </div>

      {isSuperAdmin && <PlatformLlmCard />}

      {canManageLlm && <TenantLlmCard />}

      {canManageLlm && <TenantBrandingCard />}

      {canManageTokens && <ApiTokenCard />}

      {!isSuperAdmin && !canManage && (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            需要管理员权限才能查看设置。
          </CardContent>
        </Card>
      )}
    </div>
  );
}

/** Platform-wide config card — super admin only. */
function PlatformLlmCard() {
  const { data, isLoading } = usePlatformLlmConfig();
  const updateMut = useUpdatePlatformLlmConfig();
  return (
    <LlmConfigCard
      title="平台级配置"
      description="所有租户的默认 LLM 配置。无租户级配置时使用此项。"
      config={data}
      isLoading={isLoading}
      onSubmit={(payload) => updateMut.mutateAsync(payload)}
      pending={updateMut.isPending}
    />
  );
}

/** Tenant-level config card — owner/admin/super_admin. */
function TenantLlmCard() {
  const { data, isLoading } = useTenantLlmConfig();
  const updateMut = useUpdateTenantLlmConfig();
  return (
    <LlmConfigCard
      title="租户级配置"
      description="覆盖当前租户的平台级配置。留空字段将使用平台级 / 环境默认值。"
      config={data}
      isLoading={isLoading}
      onSubmit={(payload) => updateMut.mutateAsync(payload)}
      pending={updateMut.isPending}
    />
  );
}

// ------------------------------------------------------- tenant branding card

// A few curated brand colors so a tenant can pick without a color theory
// background. Each is a valid #RRGGBB. The swatch row complements the native
// color input + hex text field.
const PRESET_COLORS = [
  "#222222", // shadcn default (near-black)
  "#2563eb", // blue
  "#16a34a", // green
  "#db2777", // pink
  "#ea580c", // orange
  "#7c3aed", // violet
];

/** Tenant white-label branding card — display name, logo, theme color, login text.
 * Visible to owner/admin/super_admin (settings:update). Saves via the tenant
 * config upsert; the theme color is applied globally by useApplyTenantTheme. */
function TenantBrandingCard() {
  const toast = useToast();
  const { data, isLoading } = useTenantConfig();
  const updateMut = useUpdateTenantConfig();

  // Local editable state, seeded once from the fetched config. We keep the
  // fields as strings (empty = cleared) so the user can wipe a value and save.
  const [displayName, setDisplayName] = useState("");
  const [logoUrl, setLogoUrl] = useState("");
  const [themeColor, setThemeColor] = useState("#222222");
  const [loginText, setLoginText] = useState("");
  const [seeded, setSeeded] = useState(false);

  if (!seeded && !isLoading) {
    setDisplayName(data?.display_name ?? "");
    setLogoUrl(data?.logo_url ?? "");
    setThemeColor(data?.theme_color ?? "#222222");
    setLoginText(data?.login_text ?? "");
    setSeeded(true);
  }

  const handleSave = async () => {
    // Normalize empty strings to null (the backend stores null = use default).
    const payload = {
      display_name: displayName.trim() || null,
      logo_url: logoUrl.trim() || null,
      theme_color: themeColor || null,
      login_text: loginText.trim() || null,
    };
    try {
      await updateMut.mutateAsync(payload);
      toast.success("已保存", "品牌配置");
    } catch (err) {
      toast.error("保存失败", apiErrorMessage(err));
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Palette className="h-5 w-5" /> 品牌配置
        </CardTitle>
        <CardDescription>
          配置本租户的白标品牌：显示名称、Logo、主题色与登录页文案。主题色会
          应用到全站按钮与链接。
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
          <p className="py-6 text-center text-sm text-muted-foreground">加载中…</p>
        ) : (
          <>
            <div className="space-y-2">
              <Label>显示名称</Label>
              <Input
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="覆盖默认平台名称(留空则使用默认)"
              />
            </div>

            <div className="space-y-2">
              <Label>Logo</Label>
              {/* Upload fills the URL field automatically; the text input below
                  stays available for pasting an external CDN URL. An empty
                  onUploaded value clears the logo. */}
              <FileUpload
                value={logoUrl || null}
                accept="image/png,image/jpeg,image/webp,image/gif"
                maxSizeMb={10}
                label="点击或拖拽 Logo 图片上传"
                onUploaded={(url) => setLogoUrl(url)}
              />
              <Input
                value={logoUrl}
                onChange={(e) => setLogoUrl(e.target.value)}
                placeholder="https://cdn.example.com/logo.png"
              />
              <p className="text-xs text-muted-foreground">
                上传图片或粘贴图片地址(支持 PNG / JPEG / WebP / GIF,≤ 10MB)。
              </p>
            </div>

            <div className="space-y-2">
              <Label>主题色</Label>
              <div className="flex flex-wrap items-center gap-2">
                <input
                  type="color"
                  value={themeColor}
                  onChange={(e) => setThemeColor(e.target.value)}
                  className="h-9 w-12 cursor-pointer rounded border border-input bg-background p-1"
                  aria-label="选择主题色"
                />
                <Input
                  value={themeColor}
                  onChange={(e) => setThemeColor(e.target.value)}
                  placeholder="#RRGGBB"
                  className="w-32 font-mono"
                />
                <div className="flex flex-wrap gap-1.5">
                  {PRESET_COLORS.map((c) => (
                    <button
                      key={c}
                      type="button"
                      onClick={() => setThemeColor(c)}
                      className="h-7 w-7 rounded-full border border-border ring-offset-2 transition hover:scale-110"
                      style={{ backgroundColor: c }}
                      aria-label={`预设色 ${c}`}
                    />
                  ))}
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                应用到全站按钮 / 链接(实时预览见上方导航栏高亮色)。
              </p>
            </div>

            <div className="space-y-2">
              <Label>登录页文案</Label>
              <textarea
                className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                value={loginText}
                onChange={(e) => setLoginText(e.target.value)}
                placeholder="展示在登录页的欢迎 / 提示文案"
              />
            </div>

            <Button onClick={handleSave} disabled={updateMut.isPending}>
              {updateMut.isPending ? "保存中…" : "保存"}
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}

// --------------------------------------------------------------- shared card

function LlmConfigCard({
  title,
  description,
  config,
  isLoading,
  onSubmit,
  pending,
}: {
  title: string;
  description: string;
  config: LlmConfig | null | undefined;
  isLoading: boolean;
  onSubmit: (payload: LlmConfigUpdate) => Promise<unknown>;
  pending: boolean;
}) {
  const toast = useToast();
  const [showKey, setShowKey] = useState(false);
  // available_models editable tag list
  const [models, setModels] = useState<string[] | null>(null);
  const [newModel, setNewModel] = useState("");

  // Local editable field state; seeded from the fetched config once it loads.
  const [baseUrl, setBaseUrl] = useState("");
  const [defaultModel, setDefaultModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [seeded, setSeeded] = useState(false);

  // Seed local state when the config first arrives (or when it's absent).
  if (!seeded && !isLoading) {
    setBaseUrl(config?.base_url ?? "");
    setDefaultModel(config?.default_model ?? "");
    setModels(config ? [...config.available_models] : []);
    setSeeded(true);
  }

  const resolvedModels = models ?? [];

  const addModel = () => {
    const m = newModel.trim();
    if (m && !resolvedModels.includes(m)) {
      setModels([...resolvedModels, m]);
    }
    setNewModel("");
  };

  const removeModel = (m: string) => {
    setModels(resolvedModels.filter((x) => x !== m));
  };

  const handleSave = async () => {
    // Build payload: only send api_key when the user typed something new.
    const payload: LlmConfigUpdate = {
      base_url: baseUrl,
      default_model: defaultModel,
      available_models: resolvedModels,
    };
    if (apiKey.trim()) {
      payload.api_key = apiKey.trim();
    }
    try {
      await onSubmit(payload);
      toast.success("已保存", title);
      setApiKey("");
    } catch (err) {
      toast.error("保存失败", apiErrorMessage(err));
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Server className="h-5 w-5" /> {title}
        </CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
          <p className="py-6 text-center text-sm text-muted-foreground">加载中…</p>
        ) : (
          <>
            <div className="space-y-2">
              <Label>API Key</Label>
              <div className="flex items-center gap-2">
                <div className="relative flex-1">
                  <KeyRound className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    type={showKey ? "text" : "password"}
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder={
                      config?.api_key_hint
                        ? `当前 ${config.api_key_hint}（留空则不修改）`
                        : "输入 API Key（如 sk-...）"
                    }
                    className="pl-9 pr-9"
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey((v) => !v)}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    aria-label={showKey ? "隐藏" : "显示"}
                  >
                    {showKey ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </button>
                </div>
              </div>
              {config?.api_key_hint && (
                <p className="text-xs text-muted-foreground">
                  当前存储的 Key：{config.api_key_hint}
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label>Base URL</Label>
              <Input
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="https://api.deepseek.com"
              />
            </div>

            <div className="space-y-2">
              <Label>默认模型</Label>
              <Select
                value={defaultModel}
                onValueChange={setDefaultModel}
                disabled={resolvedModels.length === 0}
              >
                <SelectTrigger>
                  <SelectValue placeholder="选择默认模型" />
                </SelectTrigger>
                <SelectContent>
                  {resolvedModels.map((m) => (
                    <SelectItem key={m} value={m}>
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>可用模型</Label>
              <div className="flex flex-wrap gap-2">
                {resolvedModels.map((m) => (
                  <Badge
                    key={m}
                    variant="secondary"
                    className="gap-1 pr-1"
                  >
                    {m}
                    <button
                      type="button"
                      onClick={() => removeModel(m)}
                      className="rounded-full hover:bg-muted-foreground/20"
                      aria-label={`移除 ${m}`}
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))}
                {resolvedModels.length === 0 && (
                  <span className="text-sm text-muted-foreground">暂无模型</span>
                )}
              </div>
              <div className="flex gap-2">
                <Input
                  value={newModel}
                  onChange={(e) => setNewModel(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      addModel();
                    }
                  }}
                  placeholder="如 deepseek-chat，回车添加"
                />
                <Button type="button" variant="outline" size="icon" onClick={addModel}>
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
            </div>

            <Button onClick={handleSave} disabled={pending}>
              {pending ? "保存中…" : "保存"}
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}

// --------------------------------------------------------------- API tokens

const fmt = (s: string | null): string =>
  s ? new Date(s).toLocaleString() : "-";

/** API Token management card — issue/list/revoke tokens for external agents. */
function ApiTokenCard() {
  const toast = useToast();
  const { data: tokens, isLoading } = useApiTokens();
  const createMut = useCreateApiToken();
  const revokeMut = useRevokeApiToken();

  const [issueOpen, setIssueOpen] = useState(false);
  const [name, setName] = useState("");
  const [expiresDays, setExpiresDays] = useState("0"); // 0 = never
  // The freshly issued token — shown once with a copy button + warning until
  // the user acknowledges. null = no token to reveal (issue dialog closed).
  const [revealed, setRevealed] = useState<ApiTokenCreated | null>(null);
  const [copied, setCopied] = useState(false);
  const [revokeTarget, setRevokeTarget] = useState<ApiToken | null>(null);

  const resetForm = () => {
    setName("");
    setExpiresDays("0");
  };

  const openIssue = () => {
    resetForm();
    setIssueOpen(true);
  };

  const handleIssue = async () => {
    if (!name.trim()) {
      toast.error("请填写 Token 名称");
      return;
    }
    const days = Number.parseInt(expiresDays, 10);
    const expires_at =
      Number.isFinite(days) && days > 0
        ? new Date(Date.now() + days * 86400_000).toISOString()
        : null;
    try {
      const created = await createMut.mutateAsync({
        name: name.trim(),
        expires_at,
      });
      // Switch the dialog to the "reveal" view: the plaintext is shown only now.
      setRevealed(created);
      setCopied(false);
      setIssueOpen(false);
      toast.success("Token 已颁发", "请立即复制保存,关闭后无法再看到");
    } catch (err) {
      toast.error("颁发失败", apiErrorMessage(err));
    }
  };

  const handleCopy = async (token: string) => {
    try {
      await navigator.clipboard.writeText(token);
      setCopied(true);
      toast.success("已复制到剪贴板");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard may be unavailable (insecure context); fall back to selecting
      toast.error("复制失败", "请手动选中上方文本复制");
    }
  };

  const handleRevoke = async () => {
    if (!revokeTarget) return;
    try {
      await revokeMut.mutateAsync(revokeTarget.id);
      toast.success("已吊销 Token", revokeTarget.name);
      setRevokeTarget(null);
    } catch (err) {
      toast.error("吊销失败", apiErrorMessage(err));
    }
  };

  const list = tokens ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5" /> API Token 管理
        </CardTitle>
        <CardDescription>
          为外部 AI Agent（agenthub CLI 等）颁发长效 Token。Token 继承你当前
          的全部权限并固定租户——妥善保管,定期吊销。
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex justify-end">
          <Button onClick={openIssue}>
            <Plus className="mr-2 h-4 w-4" /> 颁发新 Token
          </Button>
        </div>

        {isLoading ? (
          <p className="py-6 text-center text-sm text-muted-foreground">加载中…</p>
        ) : list.length === 0 ? (
          <div className="flex flex-col items-center gap-3 py-12 text-center">
            <KeyRound className="h-10 w-10 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              暂无 Token,点击「颁发新 Token」创建
            </p>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>名称</TableHead>
                <TableHead>前缀</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>创建时间</TableHead>
                <TableHead>最后使用</TableHead>
                <TableHead>过期</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {list.map((t) => (
                <TableRow key={t.id}>
                  <TableCell className="font-medium">{t.name}</TableCell>
                  <TableCell>
                    <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
                      {t.token_prefix}
                    </code>
                  </TableCell>
                  <TableCell>
                    <Badge variant={t.is_active ? "success" : "secondary"}>
                      {t.is_active ? "生效中" : "已吊销"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {fmt(t.created_at)}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {fmt(t.last_used_at)}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {t.expires_at ? fmt(t.expires_at) : "永不过期"}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => setRevokeTarget(t)}
                      aria-label="吊销"
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>

      {/* issue dialog */}
      <Dialog open={issueOpen} onOpenChange={setIssueOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>颁发新 Token</DialogTitle>
            <DialogDescription>
              新 Token 将继承你当前的全部权限并固定到本租户。明文仅在创建后显示
              一次,请立即复制保存。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>名称</Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="如 my-cursor-agent"
              />
            </div>
            <div className="space-y-2">
              <Label>有效期</Label>
              <Select value={expiresDays} onValueChange={setExpiresDays}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="0">永不过期</SelectItem>
                  <SelectItem value="7">7 天</SelectItem>
                  <SelectItem value="30">30 天</SelectItem>
                  <SelectItem value="90">90 天</SelectItem>
                  <SelectItem value="365">365 天</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <p className="text-xs text-muted-foreground">
              权限范围:继承你的全部权限(细粒度 scope 编辑暂不支持)
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIssueOpen(false)}>
              取消
            </Button>
            <Button onClick={handleIssue} disabled={createMut.isPending}>
              {createMut.isPending ? "颁发中…" : "颁发"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* reveal dialog — plaintext token shown only once */}
      <Dialog
        open={!!revealed}
        onOpenChange={(o) => !o && setRevealed(null)}
      >
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-amber-500" />
              Token 已颁发 — 立即复制保存
            </DialogTitle>
            <DialogDescription>
              这是该 Token 唯一一次明文展示。关闭后将永远无法再次查看,只能吊销
              重发。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
              <div className="flex items-center gap-2 font-medium text-amber-700 dark:text-amber-400">
                <AlertTriangle className="h-4 w-4" />
                请立即复制下方 Token 并妥善保管
              </div>
            </div>
            <div className="space-y-2">
              <Label>Token（明文,仅显示一次）</Label>
              <div className="flex items-center gap-2">
                <Input
                  readOnly
                  value={revealed?.token ?? ""}
                  className="font-mono text-xs"
                  onFocus={(e) => e.currentTarget.select()}
                />
                <Button
                  variant="outline"
                  size="icon"
                  onClick={() => revealed && handleCopy(revealed.token)}
                  aria-label="复制"
                >
                  {copied ? (
                    <Check className="h-4 w-4 text-green-600" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                </Button>
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              名称:{revealed?.name} · 前缀:{revealed?.token_prefix}
            </p>
          </div>
          <DialogFooter>
            <Button onClick={() => setRevealed(null)}>我已保存,关闭</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* revoke confirm */}
      <Dialog
        open={!!revokeTarget}
        onOpenChange={(o) => !o && setRevokeTarget(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认吊销</DialogTitle>
            <DialogDescription>
              确定吊销「{revokeTarget?.name}」?吊销后使用此 Token 的 Agent 将立
              即无法访问,且不可恢复。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRevokeTarget(null)}>
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={handleRevoke}
              disabled={revokeMut.isPending}
            >
              <Trash2 className="mr-2 h-4 w-4" /> 吊销
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
