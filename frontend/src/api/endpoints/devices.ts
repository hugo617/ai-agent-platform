/**
 * endpoints/devices — devices (设备实例 CRUD, devices-crud-ui 系列 2/4).
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 */
import {
  api,
} from "../client";
import type {
  Device,
  DeviceBindRequest,
  DeviceBindResponse,
  DeviceCreate,
  DeviceHqRead,
  DeviceModelCreate,
  DeviceModelPublic,
  DeviceModelRead,
  DeviceModelUpdate,
  DeviceUpdate,
} from "../types";
// ---------- devices (设备实例 CRUD, devices-crud-ui 系列 2/4) ----------
//
// Reads branch on the caller's platform role on the backend:
// - tenant roles (owner/admin/member) → Device[] scoped to this tenant
// - super_admin / hq_staff            → DeviceHqRead[] cross-tenant panorama
// The two role-specific shapes are surfaced as ``fetchDevices`` (store) +
// ``fetchDevicesAll`` (HQ) below, each declaring the narrow return type at this
// seam rather than a union the caller must narrow with ``as`` at the view
// boundary (plan-union-cast-split §1/§4.0 D1). Writes (create/update/delete/
// bind) are tenant-scoped and return Device.
//
// bind/unbind are POST/DELETE on a sub-resource (/devices/{id}/bind) mirroring
// the attach/detach pattern used for groups and agents. bind returns 200 (not
// 201 — the device already exists, bind is an assignment); DeviceBindResponse.
// already_bound distinguishes a true new binding from an idempotent repeat.
// unbind returns 204 even when no binding exists (DELETE idempotency).
// GET /devices/ branches on platform_role (store roles get Device[], HQ roles
// get DeviceHqRead[]). Rather than return a union and force callers to narrow
// with ``as`` at every view boundary, we expose two role-specific fetch
// functions that each declare the narrow shape for their audience. Both hit
// the same URL; the type is fixed at this seam, with zero runtime difference
// (a session's platform_role is fixed, so only one of the two is ever called
// for a given user — the two caches never collide on the shared ``qk.devices``
// key). Mirrors the fetchBookings/fetchBookingsAll split (plan-union-cast-split
// §1/§4.0 D1, slice 2).
export async function fetchDevices(): Promise<Device[]> {
  const { data } = await api.get<Device[]>("/devices/");
  return data;
}

/** HQ panorama variant of ``fetchDevices`` — returns ``DeviceHqRead[]``
 * (``Device`` + tenant_name/model_name/customer_name pre-expanded) for the
 * super_admin / hq_staff cross-tenant view. Same endpoint as ``fetchDevices``;
 * the backend returns the panorama shape for HQ roles. */
export async function fetchDevicesAll(): Promise<DeviceHqRead[]> {
  const { data } = await api.get<DeviceHqRead[]>("/devices/");
  return data;
}

export async function fetchDevice(id: string): Promise<Device | DeviceHqRead> {
  const { data } = await api.get<Device | DeviceHqRead>(`/devices/${id}`);
  return data;
}

export async function createDevice(payload: DeviceCreate): Promise<Device> {
  const { data } = await api.post<Device>("/devices/", payload);
  return data;
}

export async function updateDevice(
  id: string,
  payload: DeviceUpdate,
): Promise<Device> {
  const { data } = await api.put<Device>(`/devices/${id}`, payload);
  return data;
}

// DELETE has no body (REST convention), so the cross-store target rides a
// ``tenant_id`` query param (platform-cross-tenant-write plan §4.5.4a 补丁 1).
// ``tenantId`` is optional — store principals omit it (backend uses
// ``user.tenant_id``, behaviour unchanged); platform writers MUST pass it.
export async function deleteDevice(
  id: string,
  tenantId?: string,
): Promise<void> {
  await api.delete(`/devices/${id}`, {
    params: tenantId ? { tenant_id: tenantId } : undefined,
  });
}

export async function bindDeviceCustomer(
  id: string,
  customerId: string,
  tenantId?: string,
): Promise<DeviceBindResponse> {
  const { data } = await api.post<DeviceBindResponse>(
    `/devices/${id}/bind`,
    {
      customer_id: customerId,
      ...(tenantId ? { tenant_id: tenantId } : {}),
    } satisfies DeviceBindRequest,
  );
  return data;
}

// DELETE /devices/{id}/bind — same query-param convention as deleteDevice
// (plan §4.5.4a 补丁 1).
export async function unbindDeviceCustomer(
  id: string,
  tenantId?: string,
): Promise<void> {
  await api.delete(`/devices/${id}/bind`, {
    params: tenantId ? { tenant_id: tenantId } : undefined,
  });
}

// ---------- device-models (平台级设备型号目录, device-models-crud +
//           device-models-admin-ui) ----------
//
// GET /device-models/ branches on platform_role server-side: tenant users get
// DeviceModelPublic {id, name, specs.form_factor} (device-picker dropdown),
// super_admin / hq_staff get DeviceModelRead (full fields incl. unit_cost +
// complete specs). Like devices/bookings, we expose two role-specific fetch
// functions that each declare the narrow shape rather than return a union and
// force callers to narrow with ``as`` at render. Same URL either way; same
// cache key (``qk.deviceModels``) — a session's platform_role is fixed, so
// only one of the two is ever called for a given user (plan-union-cast-split
// §1/§4.0 D1 + §4.5, slice 2). The store-path dropdown projects onto a
// ``{id, name}`` subset regardless, so the union added no value there either.
export async function fetchDeviceModels(): Promise<DeviceModelPublic[]> {
  const { data } = await api.get<DeviceModelPublic[]>("/device-models/");
  return data;
}

/** Super_admin / hq_staff catalogue variant of ``fetchDeviceModels`` — returns
 * ``DeviceModelRead[]`` (full fields: unit_cost + complete specs) for the
 * RequireSuperAdmin-guarded admin page. Same endpoint as ``fetchDeviceModels``;
 * the backend returns the full shape for HQ roles. */
export async function fetchDeviceModelsAll(): Promise<DeviceModelRead[]> {
  const { data } = await api.get<DeviceModelRead[]>("/device-models/");
  return data;
}

// ---------- device-models admin writes (super_admin catalogue management,
//           device-models-admin-ui) ----------
//
// Writes (POST/PUT/DELETE) require super_admin — the backend guards them with
// require_super_admin(); the frontend RequireSuperAdmin route guard is the UX
// layer on top. The auth interceptor attaches the token; no extra header.
// PUT is whole-replace on specs (backend DeviceModelUpdate semantics); the form
// always sends the full specs dict reconstructed by KeySpecRows. DELETE is
// soft-delete (is_deleted=true; the row stays as the audit trail and the name
// becomes reusable). Returns 204 — no body to consume.
export async function createDeviceModel(
  payload: DeviceModelCreate,
): Promise<DeviceModelRead> {
  const { data } = await api.post<DeviceModelRead>("/device-models/", payload);
  return data;
}

export async function updateDeviceModel(
  id: string,
  payload: DeviceModelUpdate,
): Promise<DeviceModelRead> {
  const { data } = await api.put<DeviceModelRead>(`/device-models/${id}`, payload);
  return data;
}

export async function deleteDeviceModel(id: string): Promise<void> {
  await api.delete(`/device-models/${id}`);
}

