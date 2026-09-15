import { Outlet, createRootRoute, createRoute, createRouter } from "@tanstack/react-router"

import { Layout } from "@/components/layout"
import { ActionItemsPage } from "@/routes/action-items"
import { CustomersPage } from "@/routes/customers"
import { IncidentDetailPage } from "@/routes/incident-detail"
import { IncidentsPage, type IncidentsSearch } from "@/routes/incidents"
import { LoginPage, type LoginSearch } from "@/routes/login"
import { OnCallPage } from "@/routes/oncall"
import { OverviewPage } from "@/routes/overview"
import { TeamPage } from "@/routes/team"

const rootRoute = createRootRoute({ component: Outlet })

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  validateSearch: (search: Record<string, unknown>): LoginSearch => ({
    next: typeof search.next === "string" ? search.next : undefined,
    error: typeof search.error === "string" ? search.error : undefined,
  }),
  component: function LoginRoute() {
    return <LoginPage {...loginRoute.useSearch()} />
  },
})

const appRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "app",
  component: Layout,
})

const overviewRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/",
  component: OverviewPage,
})

const incidentsRoute = createRoute({
  getParentRoute: () => appRoute,
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
  getParentRoute: () => appRoute,
  path: "/incidents/$incidentId",
  component: function IncidentDetailRoute() {
    const { incidentId } = incidentDetailRoute.useParams()
    return <IncidentDetailPage incidentId={incidentId} />
  },
})

const actionItemsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/action-items",
  component: ActionItemsPage,
})

const oncallRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/oncall",
  component: OnCallPage,
})

const customersRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/customers",
  component: CustomersPage,
})

const teamRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/team",
  component: TeamPage,
})

export const router = createRouter({
  routeTree: rootRoute.addChildren([
    loginRoute,
    appRoute.addChildren([
      overviewRoute,
      incidentsRoute,
      incidentDetailRoute,
      actionItemsRoute,
      oncallRoute,
      teamRoute,
      customersRoute,
    ]),
  ]),
})

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}
