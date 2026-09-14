import { useNavigate } from "@tanstack/react-router"
import { PlusIcon } from "lucide-react"
import { useState } from "react"

import { MemberSelect } from "@/components/member-select"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { useCreateIncident } from "@/lib/api"

export function CreateIncidentDialog() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState("")
  const [leadId, setLeadId] = useState<number | null>(null)
  const [description, setDescription] = useState("")
  const create = useCreateIncident()

  const onOpenChange = (next: boolean) => {
    setOpen(next)
    if (next) {
      setName("")
      setLeadId(null)
      setDescription("")
    }
  }

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    create.mutate(
      { name: name.trim(), lead_id: leadId, description: description.trim() || null },
      {
        onSuccess: (incident) => {
          setOpen(false)
          navigate({ to: "/incidents/$incidentId", params: { incidentId: incident.id } })
        },
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button size="sm">
          <PlusIcon /> New incident
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>New incident</DialogTitle>
            <DialogDescription>Creates a Slack channel and invites the lead.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="incident-name">Name</Label>
            <Input id="incident-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="incident-lead">Lead</Label>
            <MemberSelect
              id="incident-lead"
              allowNone
              noneLabel="Whoever is on call"
              value={leadId}
              onChange={setLeadId}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="incident-description">Description</Label>
            <Textarea
              id="incident-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={!name.trim() || create.isPending}>
              Create incident
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
