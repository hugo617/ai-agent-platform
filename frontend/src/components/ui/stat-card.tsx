import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * Stat / counter card — a labelled metric tile in a ``<Card>``.
 *
 * Replaces the byte-identical ``CounterCard`` (billing-page) and
 * ``SummaryCard`` (billing-admin-page), both of which rendered the exact same
 * structure under different names. The customers-page ``Metric`` is a distinct
 * borderless variant (icon beside the label) and is left in place.
 */
export function StatCard({
  title,
  value,
  icon,
}: {
  title: string;
  value: string;
  icon?: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        {icon}
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
      </CardContent>
    </Card>
  );
}
