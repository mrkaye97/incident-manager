import { useQuery } from "@tanstack/react-query"
import { PencilIcon, PlusIcon } from "lucide-react"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { LoadingState } from "@/components/ui/spinner"
import { customersQuery, useSaveCustomer, type Customer } from "@/lib/api"

export function CustomersPage() {
  const { data: customers = [], isLoading } = useQuery(customersQuery)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Customers</CardTitle>
        <CardDescription>Incidents can be tagged with the customers they affect.</CardDescription>
        <CardAction>
          <CustomerDialog />
        </CardAction>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <LoadingState />
        ) : customers.length === 0 ? (
          <p className="py-4 text-center text-sm text-muted-foreground">No customers yet.</p>
        ) : (
          <ul className="divide-y">
            {customers.map((customer) => (
              <li key={customer.id} className="flex items-center justify-between py-2 text-sm">
                <span className="font-medium">{customer.name}</span>
                <CustomerDialog customer={customer} />
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

function CustomerDialog({ customer }: { customer?: Customer }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState("")
  const save = useSaveCustomer()

  const onOpenChange = (next: boolean) => {
    setOpen(next)
    if (next) setName(customer?.name ?? "")
  }

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    save.mutate({ id: customer?.id, name: name.trim() }, { onSuccess: () => setOpen(false) })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        {customer ? (
          <Button variant="ghost" size="icon-sm" aria-label={`Rename ${customer.name}`}>
            <PencilIcon />
          </Button>
        ) : (
          <Button size="sm">
            <PlusIcon /> Add customer
          </Button>
        )}
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>{customer ? `Rename ${customer.name}` : "Add customer"}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="customer-name">Name</Label>
            <Input id="customer-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={!name.trim()} loading={save.isPending}>
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
