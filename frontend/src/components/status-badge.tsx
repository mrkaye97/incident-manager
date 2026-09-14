import { Badge } from "@/components/ui/badge"
import type { IncidentStatus } from "@/lib/api"

export function StatusBadge({ status }: { status: IncidentStatus }) {
  return status === "OPEN" ? (
    <Badge variant="destructive">Open</Badge>
  ) : (
    <Badge variant="secondary">Resolved</Badge>
  )
}
