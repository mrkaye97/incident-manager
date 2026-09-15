import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { PencilIcon } from "lucide-react"
import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Label } from "@/components/ui/label"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { customersQuery, useUpdateIncidentCustomers, type Incident } from "@/lib/api"

export function CustomerBadges({ customerIds }: { customerIds: string[] }) {
  const { data: customers = [] } = useQuery(customersQuery)

  if (customerIds.length === 0) {
    return <span className="text-muted-foreground">—</span>
  }

  return (
    <div className="flex flex-wrap gap-1">
      {customerIds.map((id) => (
        <Badge key={id} variant="outline">
          {customers.find((c) => c.id === id)?.name ?? id}
        </Badge>
      ))}
    </div>
  )
}

export function CustomerCheckboxes({
  value,
  onChange,
}: {
  value: string[]
  onChange: (value: string[]) => void
}) {
  const { data: customers = [] } = useQuery(customersQuery)

  if (customers.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No customers yet. Add some on the{" "}
        <Link to="/customers" className="underline">
          Customers
        </Link>{" "}
        page.
      </p>
    )
  }

  return (
    <div className="grid grid-cols-2 gap-2">
      {customers.map((customer) => (
        <Label key={customer.id} className="flex items-center gap-2 font-normal">
          <Checkbox
            checked={value.includes(customer.id)}
            onCheckedChange={(checked) =>
              onChange(
                checked === true
                  ? [...value, customer.id]
                  : value.filter((id) => id !== customer.id),
              )
            }
          />
          {customer.name}
        </Label>
      ))}
    </div>
  )
}

export function AffectedCustomers({ incident }: { incident: Incident }) {
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState<string[]>([])
  const update = useUpdateIncidentCustomers(incident.id)

  const onOpenChange = (next: boolean) => {
    setOpen(next)
    if (next) setSelected(incident.customer_ids)
  }

  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <span className="text-muted-foreground">Affected customers:</span>
      <CustomerBadges customerIds={incident.customer_ids} />
      <Popover open={open} onOpenChange={onOpenChange}>
        <PopoverTrigger asChild>
          <Button variant="ghost" size="icon-xs" aria-label="Edit affected customers">
            <PencilIcon />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="grid w-64 gap-3">
          <p className="text-sm font-medium">Affected customers</p>
          <CustomerCheckboxes value={selected} onChange={setSelected} />
          <Button
            size="sm"
            loading={update.isPending}
            onClick={() => update.mutate(selected, { onSuccess: () => setOpen(false) })}
          >
            Save
          </Button>
        </PopoverContent>
      </Popover>
    </div>
  )
}
