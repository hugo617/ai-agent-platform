import { PageHeader } from "@/components/layout/page-header";

/**
 * Bookings page — device-booking slice 05 placeholder.
 *
 * Slice 05 lays the frontend foundation (types / endpoints / queries / route /
 * nav) and intentionally ships NO UI here. This stub keeps `/bookings`
 * reachable so the route + nav item verify end-to-end; the real views land in
 * later slices:
 * - slice 06 — store view (list + filter chips + schedule grid + CRUD dialog)
 * - slice 07 — HQ panorama + customer "my bookings" view + the three-way
 *   branch (isSuperAdmin/isHQStaff → HqView, hasCustomerIdentity →
 *   MyBookingsView, else → StoreView).
 *
 * The placeholder stays intentionally minimal: a PageHeader (consistent with
 * every other page's shell) + a muted "coming soon" body. No data fetch — the
 * /me query already fires from the layout, and firing useBookings() here would
 * 403 a plain member on a fresh tenant that lacks the bookings seed (slice 02
 * backfills existing tenants, but the hook is best left to the real views).
 */
export function BookingsPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="预约" subtitle="设备预约订单管理" />
      <p className="text-sm text-muted-foreground">预约管理界面即将上线。</p>
    </div>
  );
}
