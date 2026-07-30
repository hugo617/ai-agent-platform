/**
 * queries/devices — devices (设备实例 CRUD, devices-crud-ui 系列 2/4).
 *
 * Extracted from queries.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for qk + useApiMutation.
 */
import { qk, useApiMutation } from "./core";
import { useQuery } from "@tanstack/react-query";
import {
  bindDeviceCustomer,
  createDevice,
  createDeviceModel,
  deleteDevice,
  deleteDeviceModel,
  fetchDeviceModels,
  fetchDeviceModelsAll,
  fetchDevices,
  fetchDevicesAll,
  unbindDeviceCustomer,
  updateDevice,
  updateDeviceModel,
} from "@/api/endpoints";
import type {
  DeviceCreate,
  DeviceModelCreate,
  DeviceModelUpdate,
  DeviceUpdate,
} from "@/api/types";
// ---------- devices (设备实例 CRUD, devices-crud-ui 系列 2/4) ----------
//
// useDevices drives the /devices page list for both store view (Device[]) and
// HQ panorama (DeviceHqRead[]) — the endpoint branches on platform_role, but
// the cache key is the same. Writes invalidate qk.devices so the list refreshes;
// bind/unbind also invalidate (they mutate customer_id, which the list shows).
//
// useDeviceModels feeds the store create/edit dialog's model dropdown
// (tenant users get DeviceModelPublic); useDeviceModelsAll feeds the super_admin
// catalogue page (DeviceModelRead). The endpoint branches on platform_role, and
// the union is now fixed at the hook layer (plan-union-cast-split slice 2) —
// callers no longer narrow at render. `enabled` defaults to true on
// useDeviceModels — callers that want to suppress the fetch (e.g. HQ read-only
// view) pass `enabled=false`, mirroring useAllTenants.
// useDevices / useDevicesAll both feed off GET /devices/ but declare different
// narrow shapes: store roles get Device[], HQ roles get DeviceHqRead[]. The
// endpoint branches on platform_role server-side; here the union is fixed at
// the hook layer so callers never narrow with ``as`` (plan-union-cast-split
// §1/§4.0 D1). queryKey is shared (qk.devices): a session's platform_role is
// fixed so only one of the two hooks runs for a given user — the two caches
// never coexist (plan §4.0 D5). Mirrors useBookings/useBookingsAll (slice 1).
export function useDevices() {
  return useQuery({ queryKey: qk.devices, queryFn: fetchDevices });
}

/** HQ panorama devices feed — ``DeviceHqRead[]`` (tenant/model/customer names
 * pre-expanded). Use this in cross-tenant views (super_admin / hq_staff); the
 * store-scoped ``useDevices`` is the within-tenant counterpart. Same queryKey
 * as ``useDevices`` (qk.devices) — see D5 above. */
export function useDevicesAll() {
  return useQuery({ queryKey: qk.devices, queryFn: fetchDevicesAll });
}

export function useCreateDevice() {
  // DeviceCreate.tenant_id (optional) carries the cross-store target for
  // platform writers; store principals omit it. No signature change — the
  // caller just includes ``tenant_id`` in the payload (platform-cross-tenant-
  // write plan §4.5.4a 补丁 1).
  return useApiMutation(
    (payload: DeviceCreate) => createDevice(payload),
    [qk.devices],
  );
}

export function useUpdateDevice() {
  // DeviceUpdate.tenant_id carries the platform-writer target like create.
  return useApiMutation(
    ({ id, payload }: { id: string; payload: DeviceUpdate }) =>
      updateDevice(id, payload),
    [qk.devices],
  );
}

// ``tenantId`` is the platform-writer cross-store target. We pass it through
// the hook closure rather than per-call so the store call site stays
// ``deleteMut.mutateAsync(id)`` (zero behaviour change for store callers +
// their tests). Platform callers (devices HqView) construct the hook with the
// selected target and the same ``mutateAsync(id)`` call transparently carries
// the target. ``tenantId`` undefined (store path) → no query param sent →
// backend uses ``user.tenant_id`` (plan §4.5.4a 补丁 1).
export function useDeleteDevice(tenantId?: string) {
  return useApiMutation(
    (id: string) => deleteDevice(id, tenantId),
    [qk.devices],
  );
}

export function useBindDeviceCustomer(tenantId?: string) {
  // Same closure pattern as useDeleteDevice. ``tenantId`` → body field
  // ``tenant_id`` (POST has a body); undefined (store path) omits the field.
  return useApiMutation(
    ({ deviceId, customerId }: { deviceId: string; customerId: string }) =>
      bindDeviceCustomer(deviceId, customerId, tenantId),
    [qk.devices],
  );
}

export function useUnbindDeviceCustomer(tenantId?: string) {
  // Same closure pattern as useDeleteDevice (query param on DELETE).
  return useApiMutation(
    (deviceId: string) => unbindDeviceCustomer(deviceId, tenantId),
    [qk.devices],
  );
}

// useDeviceModels / useDeviceModelsAll both feed off GET /device-models/ but
// declare different narrow shapes: tenant roles get DeviceModelPublic[] (the
// {id, name, specs.form_factor} dropdown view), super_admin / hq_staff get
// DeviceModelRead[] (full fields). The endpoint branches on platform_role
// server-side; here the union is fixed at the hook layer so callers never
// narrow with ``as`` (plan-union-cast-split §1/§4.0 D1 + §4.5). queryKey is
// shared (qk.deviceModels) — only one of the two hooks runs for a given user
// (plan §4.0 D5). The store-path dropdown projects onto ``{id, name}``
// regardless of shape, so the store hook's narrow type flows straight into the
// ModelOption cast-free path.
export function useDeviceModels(enabled = true) {
  return useQuery({
    queryKey: qk.deviceModels,
    queryFn: fetchDeviceModels,
    enabled,
  });
}

/** Super_admin / hq_staff catalogue feed — ``DeviceModelRead[]`` (full fields:
 * unit_cost + complete specs) for the RequireSuperAdmin-guarded admin page.
 * Same queryKey as ``useDeviceModels`` (qk.deviceModels) — see D5 above. */
export function useDeviceModelsAll() {
  return useQuery({
    queryKey: qk.deviceModels,
    queryFn: fetchDeviceModelsAll,
  });
}

// ---------- device-models admin writes (device-models-admin-ui,
//           super_admin catalogue management) ----------
//
// Reads reuse useDeviceModels above — the endpoint branches on platform_role,
// super_admin / hq_staff get DeviceModelRead (full fields), tenant users get
// DeviceModelPublic (dropdown view). The admin page (RequireSuperAdmin route)
// narrows the union to DeviceModelRead[] at render. These three mutations are
// super_admin-only writes (require_super_admin on the backend; RequireSuperAdmin
// route guard is the UX layer) that invalidate qk.deviceModels so every consumer
// (store dropdown + admin list) refreshes.
export function useCreateDeviceModel() {
  return useApiMutation(
    (payload: DeviceModelCreate) => createDeviceModel(payload),
    [qk.deviceModels],
  );
}

export function useUpdateDeviceModel() {
  return useApiMutation(
    ({ id, payload }: { id: string; payload: DeviceModelUpdate }) =>
      updateDeviceModel(id, payload),
    [qk.deviceModels],
  );
}

export function useDeleteDeviceModel() {
  return useApiMutation(
    (id: string) => deleteDeviceModel(id),
    [qk.deviceModels],
  );
}

