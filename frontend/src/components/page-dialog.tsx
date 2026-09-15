import { useQuery } from "@tanstack/react-query"
import { BellRingIcon } from "lucide-react"
import { useState, type ReactNode } from "react"

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
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { incidentsQuery, oncallQuery, usePage } from "@/lib/api"

const NO_INCIDENT = "none"

export function PageDialog({
  memberId = null,
  incidentId = null,
  trigger,
}: {
  memberId?: string | null
  incidentId?: string | null
  trigger?: ReactNode
}) {
  const [open, setOpen] = useState(false)
  const [target, setTarget] = useState<string | null>(memberId)
  const [incident, setIncident] = useState<string | null>(incidentId)
  const [reason, setReason] = useState("")
  const { data: openIncidents = [] } = useQuery({ ...incidentsQuery("OPEN"), enabled: open })
  const { data: oncall = [] } = useQuery(oncallQuery)
  const page = usePage()

  const onOpenChange = (next: boolean) => {
    setOpen(next)
    if (next) {
      setTarget(memberId ?? oncall[0]?.team_member_id ?? null)
      setIncident(incidentId)
      setReason("")
    }
  }

  const submit = () => {
    if (target === null) return
    page.mutate(
      { team_member_id: target, incident_id: incident, reason: reason.trim() || null },
      { onSuccess: () => setOpen(false) },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        {trigger ?? (
          <Button variant="destructive">
            <BellRingIcon /> Page someone
          </Button>
        )}
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Page someone</DialogTitle>
          <DialogDescription>
            Posts in the incident's Slack channel, or DMs them if there's no incident.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="page-target">Who</Label>
            <MemberSelect id="page-target" value={target} onChange={setTarget} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="page-incident">Incident</Label>
            <Select
              value={incident ?? NO_INCIDENT}
              onValueChange={(v) => setIncident(v === NO_INCIDENT ? null : v)}
            >
              <SelectTrigger id="page-incident" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_INCIDENT}>No incident</SelectItem>
                {openIncidents.map((i) => (
                  <SelectItem key={i.id} value={i.id}>
                    {i.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="page-reason">Reason</Label>
            <Textarea
              id="page-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="What do they need to know?"
            />
          </div>
        </div>
        <DialogFooter>
          <Button
            variant="destructive"
            disabled={target === null}
            loading={page.isPending}
            onClick={submit}
          >
            <BellRingIcon /> Send page
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
