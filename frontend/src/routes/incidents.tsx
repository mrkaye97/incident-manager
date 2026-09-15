import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"

import { CreateIncidentDialog } from "@/components/create-incident-dialog"
import { IncidentTable } from "@/components/incident-table"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { LoadingState } from "@/components/ui/spinner"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { incidentsQuery, type IncidentStatus } from "@/lib/api"

export type IncidentsSearch = { status?: IncidentStatus }

export function IncidentsPage({ status }: IncidentsSearch) {
  const navigate = useNavigate()
  const { data: incidents = [], isLoading } = useQuery(incidentsQuery(status))

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle>Incidents</CardTitle>
        <div className="flex flex-wrap items-center gap-2">
          <Tabs
            value={status ?? "ALL"}
            onValueChange={(v) =>
              navigate({
                to: "/incidents",
                search: v === "ALL" ? {} : { status: v as IncidentStatus },
              })
            }
          >
            <TabsList>
              <TabsTrigger value="OPEN">Open</TabsTrigger>
              <TabsTrigger value="RESOLVED">Resolved</TabsTrigger>
              <TabsTrigger value="ALL">All</TabsTrigger>
            </TabsList>
          </Tabs>
          <CreateIncidentDialog />
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? <LoadingState /> : <IncidentTable incidents={incidents} />}
      </CardContent>
    </Card>
  )
}
