import { createRootRoute, createRoute, createRouter } from "@tanstack/react-router"

import { Layout } from "@/components/layout"
import { ActionItemsPage } from "@/routes/action-items"
import { IncidentDetailPage } from "@/routes/incident-detail"
import { IncidentsPage, type IncidentsSearch } from "@/routes/incidents"
import { OnCallPage } from "@/routes/oncall"
import { OverviewPage } from "@/routes/overview"
import { TeamPage } from "@/routes/team"

const rootRoute = createRootRoute({ component: Layout })

const overviewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: OverviewPage,
})

const incidentsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/incidents",
  validateSearch: (search: Record<string, unknown>): IncidentsSearch => ({
    status: search.status === "OPEN" || search.status === "RESOLVED" ? search.status : undefined,
  }),
  component: function IncidentsRoute() {
    const { status } = incidentsRoute.useSearch()
    return <IncidentsPage status={status} />
  },
})

const incidentDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/incidents/$incidentId",
  component: function IncidentDetailRoute() {
    const { incidentId } = incidentDetailRoute.useParams()
    return <IncidentDetailPage incidentId={incidentId} />
  },
})

const actionItemsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/action-items",
  component: ActionItemsPage,
})

const oncallRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/oncall",
  component: OnCallPage,
})

const teamRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/team",
  component: TeamPage,
})

export const router = createRouter({
  routeTree: rootRoute.addChildren([
    overviewRoute,
    incidentsRoute,
    incidentDetailRoute,
    actionItemsRoute,
    oncallRoute,
    teamRoute,
  ]),
})

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}
