import { Link } from "@tanstack/react-router"

import { MemberSelect } from "@/components/member-select"
import { Checkbox } from "@/components/ui/checkbox"
import { Spinner } from "@/components/ui/spinner"
import { useUpdateActionItem, type ActionItem } from "@/lib/api"
import { cn } from "@/lib/utils"

export function ActionItemList({
  items,
  showIncident = false,
}: {
  items: ActionItem[]
  showIncident?: boolean
}) {
  const update = useUpdateActionItem()

  if (items.length === 0) {
    return <p className="py-4 text-center text-sm text-muted-foreground">No action items.</p>
  }

  return (
    <ul className="divide-y">
      {items.map((item) => (
        <li key={item.id} className="flex flex-wrap items-center gap-3 py-3">
          {update.isPending && update.variables?.id === item.id ? (
            <Spinner className="size-4 text-muted-foreground" />
          ) : (
            <Checkbox
              checked={item.is_completed}
              aria-label="Completed"
              onCheckedChange={(checked) =>
                update.mutate({ id: item.id, is_completed: checked === true })
              }
            />
          )}
          <div className="min-w-0 flex-1">
            <p className={cn(item.is_completed && "text-muted-foreground line-through")}>
              {item.description}
            </p>
            {showIncident && (
              <Link
                to="/incidents/$incidentId"
                params={{ incidentId: item.incident_id }}
                className="text-xs text-muted-foreground hover:underline"
              >
                {item.incident_name}
              </Link>
            )}
          </div>
          <div className="w-44">
            <MemberSelect
              allowNone
              value={item.assignee_id}
              onChange={(assignee_id) => update.mutate({ id: item.id, assignee_id })}
            />
          </div>
        </li>
      ))}
    </ul>
  )
}
