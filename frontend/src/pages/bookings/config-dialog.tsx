/**
 * bookings/ BookingConfigDialog — two-level schedule-grid config editor
 * (booking-schedule-grid 切片 03).
 *
 * Edits the platform-wide default config row + an optional per-tenant
 * override. The Dialog is a PURE presentational body — it receives the loaded
 * configs + the caller's role as props and calls ``onSubmit(scope, payload)``
 * on save. The parent owns the react-query mutation + the toast + dialog-
 * close wiring (mirrors shared-dialog.tsx's "Dialog is a pure body, parent
 * owns mutation + toast" convention, so no toast logic is duplicated between
 * the eventual store-view + hq-view callers).
 *
 * Layout (AC3):
 * - super_admin: TWO columns — 「平台默认」(writes scope="platform") + 「当前
 *   target 店覆盖」(writes scope="tenant" against targetTenantId). Each column
 *   has its own 保存 button so the operator can save one tier without touching
 *   the other.
 * - owner / admin: ONE column — 「当前店覆盖」(writes scope="tenant" against
 *   targetTenantId, which is me.tenant_id on the store path).
 *
 * Inputs (AC4 + AC5):
 * - duration: 3 preset buttons (45/60/90 min, aria-pressed reflects selection)
 *   + a free-form ``<Input type="number">`` for arbitrary minutes (D3). The two
 *   stay in sync — picking a preset updates the number, typing a number that
 *   matches a preset re-selects it.
 * - window: two ``<input type="time">`` (start + end). Values are "HH:MM"
 *   strings, which the backend stores verbatim (String(5), not Time).
 *
 * Validation: the backend enforces ``default_duration_minutes >= 1`` and
 * ``HH:MM`` 5-char pattern on both fields (422 otherwise). We do a light
 * client-side guard (non-empty + numeric duration) so the operator gets
 * immediate feedback; the authoritative check stays server-side.
 */
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { FormField as Field } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import type { BookingConfig, BookingConfigUpsert } from "@/api/types";

/** Duration preset buttons (min). 45 is the backend's seeded default. */
const DURATION_PRESETS = [45, 60, 90] as const;

/** Backend hardcoded fallback (booking_config_service.py) used when neither a
 * tenant override nor a platform row exists. Centralised here so the form
 * stays operable on a fresh tenant without spelling the triple twice
 * (initialPayload seeds from it; ConfigColumn's useState mirrors the same
 * defaults so the inputs are non-empty before the first effect runs). */
const DEFAULT_BOOKING_CONFIG: BookingConfigUpsert = {
  default_duration_minutes: 45,
  window_start: "08:00",
  window_end: "22:00",
};

/** Build the initial upsert payload from a loaded config row, or fall back to
 * the backend's hardcoded defaults when the row doesn't exist yet (GET returns
 * null in that case). Keeps the form operable on a fresh tenant that hasn't
 * customised. */
function initialPayload(cfg: BookingConfig | null): BookingConfigUpsert {
  return cfg
    ? {
        default_duration_minutes: cfg.default_duration_minutes,
        window_start: cfg.window_start,
        window_end: cfg.window_end,
      }
    : { ...DEFAULT_BOOKING_CONFIG };
}

/**
 * One editable config column. Renders the duration preset row + custom number
 * input + two time inputs + a 保存 button. Self-contained state so the two
 * columns in super_admin mode are independent (editing one doesn't dirty the
 * other). State seeds from ``config`` via useEffect on ``config`` identity,
 * so re-opening the Dialog or swapping the target tenant refreshes the form.
 */
function ConfigColumn({
  title,
  config,
  isPending,
  onSubmit,
}: {
  title: string;
  config: BookingConfig | null;
  isPending: boolean;
  onSubmit: (payload: BookingConfigUpsert) => Promise<void>;
}) {
  const [duration, setDuration] = useState(DEFAULT_BOOKING_CONFIG.default_duration_minutes);
  const [windowStart, setWindowStart] = useState(DEFAULT_BOOKING_CONFIG.window_start);
  const [windowEnd, setWindowEnd] = useState(DEFAULT_BOOKING_CONFIG.window_end);
  const [error, setError] = useState<string | null>(null);

  // Seed from the loaded row whenever it changes (open / target switch /
  // parent refetch after a save). Empty deps would miss a target switch while
  // the Dialog stays open; ``config`` identity is the right trigger.
  useEffect(() => {
    const p = initialPayload(config);
    setDuration(p.default_duration_minutes);
    setWindowStart(p.window_start);
    setWindowEnd(p.window_end);
    setError(null);
  }, [config]);

  const submit = async () => {
    // Light client-side guard; the authoritative check is server-side (422).
    if (!Number.isFinite(duration) || duration < 1) {
      setError("单时段时长需为 ≥1 的整数");
      return;
    }
    if (!windowStart || !windowEnd) {
      setError("请填写营业时间起止");
      return;
    }
    setError(null);
    await onSubmit({
      default_duration_minutes: Math.floor(duration),
      window_start: windowStart,
      window_end: windowEnd,
    });
  };

  return (
    <div className="space-y-4 rounded-lg border p-4">
      <h4 className="text-sm font-semibold">{title}</h4>

      {/* duration: preset buttons + custom number input (AC4) */}
      <Field label="单时段时长(分钟)" hint="常用预设 + 自定义任意分钟数">
        <div className="flex flex-wrap items-center gap-2">
          {DURATION_PRESETS.map((preset) => {
            const selected = duration === preset;
            return (
              <Button
                key={preset}
                type="button"
                variant={selected ? "default" : "outline"}
                size="sm"
                aria-pressed={selected}
                onClick={() => setDuration(preset)}
              >
                {preset} 分钟
              </Button>
            );
          })}
          {/* Custom number input — syncs both ways with the presets. type=number
              gives a spinbox (role=spinbox) for the test seam + native UX. */}
          <Input
            type="number"
            min={1}
            value={duration}
            onChange={(e) => {
              const v = Number(e.target.value);
              setDuration(Number.isFinite(v) ? v : 0);
            }}
            className="w-24"
            aria-label="自定义单时段时长(分钟)"
          />
        </div>
      </Field>

      {/* window: two time inputs (AC5) */}
      <div className="grid grid-cols-2 gap-3">
        <Field label="营业开始">
          <Input
            type="time"
            value={windowStart}
            onChange={(e) => setWindowStart(e.target.value)}
          />
        </Field>
        <Field label="营业结束">
          <Input
            type="time"
            value={windowEnd}
            onChange={(e) => setWindowEnd(e.target.value)}
          />
        </Field>
      </div>

      {error && <p className="text-xs text-destructive">{error}</p>}

      <DialogFooter>
        <Button onClick={submit} disabled={isPending}>
          {isPending ? "保存中…" : "保存"}
        </Button>
      </DialogFooter>
    </div>
  );
}

/**
 * Two-level booking config editor Dialog.
 *
 * Props mirror the data the parent already has loaded (configs via the
 * usePlatformBookingConfig / useTenantBookingConfig hooks; role via
 * isSuperAdmin(me); target via the HQ picker or me.tenant_id). The Dialog
 * stays free of auth-context + hooks imports so it's a pure body — both the
 * store view and HQ view can mount it without re-wiring.
 *
 * ``onSubmit(scope, payload)`` returns a Promise the parent controls: it runs
 * the matching mutation (useUpdatePlatformBookingConfig for scope="platform",
 * useUpdateTenantBookingConfig for scope="tenant"), surfaces the toast, and
 * closes the Dialog. The Dialog does NOT catch — a rejected promise propagates
 * so the parent decides whether to close + toast-success or toast-error and
 * keep the Dialog open (same contract as shared-dialog.tsx).
 */
export function BookingConfigDialog({
  open,
  isSuperAdmin,
  targetTenantName,
  platformConfig,
  tenantConfig,
  isPending,
  onClose,
  onSubmit,
}: {
  open: boolean;
  /** Pre-computed by the parent via isSuperAdmin(me) — keeps the Dialog pure. */
  isSuperAdmin: boolean;
  /** Display name for the「当前店」column header (HQ view shows the picked
   * store; store view shows the caller's tenant). */
  targetTenantName: string;
  /** Loaded platform default row (null = none seeded yet). super_admin only. */
  platformConfig: BookingConfig | null;
  /** Loaded override row for the target tenant (null = not customised yet).
   * The parent already knows which tenant this is — it threads that id into
   * the matching useUpdateTenantBookingConfig(tenantId) hook, so the Dialog
   * itself doesn't need targetTenantId. */
  tenantConfig: BookingConfig | null;
  /** Pending flag from the active mutation — disables the matching 保存 button. */
  isPending: boolean;
  onClose: () => void;
  /** scope="platform" → write the platform row; scope="tenant" → write the
   * target tenant's override (the parent maps scope → the right hook, which
   * already carries the tenant id in its closure). */
  onSubmit: (
    scope: "platform" | "tenant",
    payload: BookingConfigUpsert,
  ) => Promise<void>;
}) {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>预约配置</DialogTitle>
          <DialogDescription>
            设置排期网格的单时段时长与营业时间窗口。平台默认对所有门店生效;
            单店覆盖优先于平台默认。
          </DialogDescription>
        </DialogHeader>

        {isSuperAdmin ? (
          // super_admin:两栏并排 — 平台默认 + 当前 target 店覆盖
          <div className="grid gap-4 md:grid-cols-2">
            <ConfigColumn
              title="平台默认"
              config={platformConfig}
              isPending={isPending}
              onSubmit={(payload) => onSubmit("platform", payload)}
            />
            <ConfigColumn
              title={`当前门店:${targetTenantName}`}
              config={tenantConfig}
              isPending={isPending}
              onSubmit={(payload) => onSubmit("tenant", payload)}
            />
          </div>
        ) : (
          // owner / admin:单栏 — 当前店覆盖
          <ConfigColumn
            title={`当前门店:${targetTenantName}`}
            config={tenantConfig}
            isPending={isPending}
            onSubmit={(payload) => onSubmit("tenant", payload)}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}
