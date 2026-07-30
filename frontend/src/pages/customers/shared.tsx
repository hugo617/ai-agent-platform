/**
 * customers/ shared — constants, schema, badges and pure helpers shared across
 * the store and HQ views.
 *
 * Extracted from the original customers-page.tsx (plan-customers-page-split.md).
 * Pure locality move: zero behaviour change.
 */
import { Badge } from "@/components/ui/badge";
import { z } from "zod";

// ---------- enum labels ----------
export const GENDERS = ["male", "female", "other"] as const;
export const GENDER_LABEL: Record<string, string> = {
  male: "男",
  female: "女",
  other: "其他",
};
export const STATUSES = ["active", "inactive", "vip", "blacklist"] as const;

// ---------- status badge ----------
export function statusBadge(status: string) {
  if (status === "vip") return <Badge variant="default">VIP</Badge>;
  if (status === "inactive") return <Badge variant="secondary">未激活</Badge>;
  if (status === "blacklist") return <Badge variant="destructive">黑名单</Badge>;
  return <Badge variant="success">活跃</Badge>;
}

// ---------- create/edit form schema ----------
export const formSchema = z.object({
  identity_key: z.string().min(1, "手机号/证件号不能为空").max(100),
  name: z.string().min(1, "姓名不能为空").max(100),
  gender: z.string().optional(),
  birthday: z.string().optional(),
  remark: z.string().optional(),
  tags_json: z.string().optional(), // JSON string; parsed on submit
  status: z.string(),
});
export type FormValues = z.input<typeof formSchema>;

export const EMPTY_FORM: FormValues = {
  identity_key: "",
  name: "",
  gender: "",
  birthday: "",
  remark: "",
  tags_json: "",
  status: "active",
};

// ---------- tags-JSON pure parser (D4) ----------
// Extracted from StoreView.buildPayload so the parse logic is independently
// testable (chat/build-working-list precedent). Empty/whitespace-only input
// returns undefined (no-op on the profile). Invalid JSON returns the error
// message verbatim — StoreView surfaces it via toast, keeping the original
// "标签 JSON 格式错误" wording byte-for-byte.
export type ParseTagsResult = {
  tags: Record<string, unknown> | undefined;
  error?: string;
};

/** Parse the customer profile tags-JSON textarea. Empty → undefined (no change). */
export function parseTagsJson(raw: string | undefined): ParseTagsResult {
  const trimmed = raw?.trim();
  if (!trimmed) return { tags: undefined };
  try {
    return { tags: JSON.parse(trimmed) as Record<string, unknown> };
  } catch {
    return { tags: undefined, error: "标签 JSON 格式错误" };
  }
}
