/**
 * bookings/ index — three-way view router (the public page entry).
 *
 * Extracted from the original bookings-page.tsx (plan-bookings-page-split.md).
 * Pure locality move: zero behaviour change.
 *
 * Top-level three-way branch (slice 07):
 *
 *   isSuperAdmin(me) || isHQStaff(me) ? <HqView/>            // cross-tenant panorama
 *   : hasCustomerIdentity(me)         ? <MyBookingsView/>    // customer "my bookings"
 *   : <StoreView/>                                           // within-tenant CRUD
 *
 * HQ viewers take precedence over a customer binding (an HQ role wouldn't carry
 * one anyway). StoreView is the within-tenant CRUD surface. HqView is the
 * cross-tenant read-only panorama. MyBookingsView is the customer's read-only
 * list.
 */
import { useAuth } from "@/components/auth/auth-context";
import {
  hasCustomerIdentity,
  isHQStaff,
  isSuperAdmin,
} from "@/lib/permission";
import { HqView } from "./hq-view";
import { MyBookingsView } from "./my-bookings-view";
import { StoreView } from "./store-view";

export function BookingsPage() {
  const { me } = useAuth();

  // Three-way view fork (slice 07). HQ viewers take precedence over a customer
  // binding — an HQ role wouldn't carry one anyway, but ordering the checks
  // this way keeps the cross-tenant panorama authoritative. StoreView (slice 06)
  // is the fallthrough for everyone else: tenant owners/admins/members with no
  // customer identity.
  if (isSuperAdmin(me) || isHQStaff(me)) return <HqView />;
  if (hasCustomerIdentity(me)) return <MyBookingsView />;
  return <StoreView />;
}
