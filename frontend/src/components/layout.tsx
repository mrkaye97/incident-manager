import { useQuery } from "@tanstack/react-query"
import { Link, Outlet } from "@tanstack/react-router"
import { ExternalLinkIcon, SirenIcon } from "lucide-react"

import { PageDialog } from "@/components/page-dialog"
import { Toaster } from "@/components/ui/sonner"
import { configQuery } from "@/lib/api"

const NAV = [
  { to: "/", label: "Overview" },
  { to: "/incidents", label: "Incidents" },
  { to: "/action-items", label: "Action items" },
  { to: "/oncall", label: "On-call" },
  { to: "/team", label: "Team" },
] as const

export function Layout() {
  const { data: config } = useQuery(configQuery)

  return (
    <div className="min-h-svh bg-muted/30">
      <header className="border-b bg-background">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <Link to="/" className="flex items-center gap-2 font-semibold">
            <SirenIcon className="size-5 text-destructive" />
            Incident Manager
          </Link>
          <nav className="flex flex-wrap gap-1 text-sm">
            {NAV.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                activeOptions={{ exact: item.to === "/" }}
                className="rounded-md px-3 py-1.5 text-muted-foreground hover:bg-muted hover:text-foreground data-[status=active]:bg-muted data-[status=active]:text-foreground"
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            {config && (
              <a
                href={config.status_page_url}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
              >
                Status page <ExternalLinkIcon className="size-3.5" />
              </a>
            )}
            <PageDialog />
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
      <Toaster richColors />
    </div>
  )
}
