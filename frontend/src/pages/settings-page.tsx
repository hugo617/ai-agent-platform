import { useState } from "react";
import { Eye, EyeOff, KeyRound, Plus, Server, X } from "lucide-react";

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
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useToast } from "@/components/ui/toast";
import { apiErrorMessage } from "@/api/client";
import { useAuth } from "@/components/auth/auth-context";
import { canManageUsers } from "@/lib/permission";
import type { LlmConfig, LlmConfigUpdate } from "@/api/types";
import {
  usePlatformLlmConfig,
  useTenantLlmConfig,
  useUpdatePlatformLlmConfig,
  useUpdateTenantLlmConfig,
} from "@/hooks/queries";

export function SettingsPage() {
  const { me } = useAuth();
  const isSuperAdmin = me?.platform_role === "super_admin";
  const canManage = canManageUsers(me);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">设置</h1>
        <p className="text-muted-foreground">
          管理 LLM 提供商配置（API Key、Base URL、可用模型）。
        </p>
      </div>

      {isSuperAdmin && <PlatformLlmCard />}

      {canManage && <TenantLlmCard />}

      {!isSuperAdmin && !canManage && (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            需要管理员权限才能查看 LLM 配置。
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
