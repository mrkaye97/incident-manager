import { Link } from "@tanstack/react-router"

import { CustomerBadges } from "@/components/customers"
import { StatusBadge } from "@/components/status-badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { Incident } from "@/lib/api"
import { ago, duration } from "@/lib/format"

export function IncidentTable({ incidents }: { incidents: Incident[] }) {
  if (incidents.length === 0) {
    return <p className="py-6 text-center text-sm text-muted-foreground">No incidents.</p>
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Incident</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Lead</TableHead>
          <TableHead>Customers</TableHead>
          <TableHead>Started</TableHead>
          <TableHead>Duration</TableHead>
          <TableHead className="text-right">Action items</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {incidents.map((incident) => (
          <TableRow key={incident.id}>
            <TableCell className="font-medium">
              <Link
                to="/incidents/$incidentId"
                params={{ incidentId: incident.id }}
                className="hover:underline"
              >
                {incident.name}
              </Link>
            </TableCell>
            <TableCell>
              <StatusBadge status={incident.status} />
            </TableCell>
            <TableCell>{incident.lead_name}</TableCell>
            <TableCell>
              <CustomerBadges customerIds={incident.customer_ids} />
            </TableCell>
            <TableCell className="text-muted-foreground">{ago(incident.start_time)}</TableCell>
            <TableCell className="text-muted-foreground">
              {duration(incident.start_time, incident.end_time)}
            </TableCell>
            <TableCell className="text-right tabular-nums">
              {incident.open_action_items} open / {incident.total_action_items}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
