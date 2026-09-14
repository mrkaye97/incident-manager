import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"

import { IncidentTable } from "@/components/incident-table"
import { OnCallNow } from "@/components/oncall-now"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { actionItemsQuery, incidentsQuery } from "@/lib/api"

export function OverviewPage() {
  const { data: incidents = [] } = useQuery(incidentsQuery("OPEN"))
  const { data: actionItems = [] } = useQuery(actionItemsQuery(true))

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle>Open incidents</CardTitle>
        </CardHeader>
        <CardContent>
          <IncidentTable incidents={incidents} />
        </CardContent>
      </Card>
      <div className="grid content-start gap-6">
        <OnCallNow />
        <Card>
          <CardHeader>
            <CardTitle>Open action items</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2">
            <p className="text-3xl font-semibold tabular-nums">{actionItems.length}</p>
            <Link to="/action-items" className="text-sm text-muted-foreground hover:underline">
              View all →
            </Link>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
