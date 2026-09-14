import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import {
  ArrowLeftIcon,
  CheckCircle2Icon,
  ExternalLinkIcon,
  HashIcon,
  PencilIcon,
  PlusIcon,
} from "lucide-react"
import { useState } from "react"

import { ActionItemList } from "@/components/action-item-list"
import { MemberSelect } from "@/components/member-select"
import { PageDialog } from "@/components/page-dialog"
import { StatusBadge } from "@/components/status-badge"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  configQuery,
  incidentQuery,
  useCreateActionItem,
  useResolveIncident,
  useUpdateIncident,
  type Incident,
} from "@/lib/api"
import { ago, dateTime, duration, slackChannelUrl, statusPageUrl } from "@/lib/format"

export function IncidentDetailPage({ incidentId }: { incidentId: string }) {
  const { data, isLoading, error } = useQuery(incidentQuery(incidentId))
  const { data: config } = useQuery(configQuery)

  if (isLoading) return null
  if (error || !data) {
    return <p className="text-muted-foreground">{error?.message ?? "Incident not found"}</p>
  }

  const { incident, action_items, alerts, pages } = data

  return (
    <div className="grid gap-6">
      <div className="grid gap-3">
        <Link
          to="/incidents"
          className="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeftIcon className="size-4" /> Incidents
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="grid gap-1">
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-semibold">{incident.name}</h1>
              <StatusBadge status={incident.status} />
            </div>
            <p className="text-sm text-muted-foreground">
              Led by {incident.lead_name} · started {dateTime(incident.start_time)} (
              {ago(incident.start_time)}) ·{" "}
              {incident.end_time ? "lasted" : "ongoing for"}{" "}
              {duration(incident.start_time, incident.end_time)}
            </p>
            <div className="flex flex-wrap gap-4 pt-1 text-sm">
              <a
                href={slackChannelUrl(incident.slack_channel_id)}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1 hover:underline"
              >
                <HashIcon className="size-4" /> Slack channel
              </a>
              {config && (
                <a
                  href={statusPageUrl(config.status_page_url, incident.id)}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-1 hover:underline"
                >
                  <ExternalLinkIcon className="size-4" /> Status page
                </a>
              )}
            </div>
          </div>
          <div className="flex gap-2">
            <PageDialog incidentId={incident.status === "OPEN" ? incident.id : null} />
            {incident.status === "OPEN" && <ResolveButton incident={incident} />}
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="grid content-start gap-6 lg:col-span-2">
          <DescriptionCard incident={incident} />
          <Card>
            <CardHeader>
              <CardTitle>Action items</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-2">
              <ActionItemList items={action_items} />
              <NewActionItem incidentId={incident.id} />
            </CardContent>
          </Card>
        </div>

        <div className="grid content-start gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Alerts</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3">
              {alerts.length === 0 && (
                <p className="text-sm text-muted-foreground">No alerts linked.</p>
              )}
              {alerts.map((alert) => (
                <div key={alert.id} className="grid gap-1 text-sm">
                  <div className="flex items-center gap-2">
                    {alert.state && (
                      <Badge variant={alert.state === "ALERT" ? "destructive" : "secondary"}>
                        {alert.state}
                      </Badge>
                    )}
                    <span className="text-muted-foreground">{dateTime(alert.created_at)}</span>
                  </div>
                  <p className="font-medium">{alert.title}</p>
                  {alert.body && (
                    <p className="line-clamp-3 whitespace-pre-wrap text-muted-foreground">
                      {alert.body}
                    </p>
                  )}
                  {alert.source_url && (
                    <a
                      href={alert.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="flex w-fit items-center gap-1 hover:underline"
                    >
                      View in HyperDX <ExternalLinkIcon className="size-3.5" />
                    </a>
                  )}
                </div>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Pages</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-2 text-sm">
              {pages.length === 0 && <p className="text-muted-foreground">Nobody paged.</p>}
              {pages.map((page) => (
                <div key={page.id} className="flex items-center justify-between gap-2">
                  <div className="grid">
                    <span>{page.member_name}</span>
                    <span className="text-xs text-muted-foreground">{dateTime(page.paged_at)}</span>
                  </div>
                  {page.acknowledged_at ? (
                    <Badge variant="secondary">Acked {dateTime(page.acknowledged_at)}</Badge>
                  ) : page.pushed ? (
                    <Badge variant="destructive">Not acked</Badge>
                  ) : (
                    <span className="text-xs text-muted-foreground">Slack only</span>
                  )}
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}

function DescriptionCard({ incident }: { incident: Incident }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState("")
  const update = useUpdateIncident(incident.id)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Description</CardTitle>
        {!editing && (
          <CardAction>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setDraft(incident.description ?? "")
                setEditing(true)
              }}
            >
              <PencilIcon /> Edit
            </Button>
          </CardAction>
        )}
      </CardHeader>
      <CardContent>
        {editing ? (
          <div className="grid gap-2">
            <Textarea rows={6} value={draft} onChange={(e) => setDraft(e.target.value)} />
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setEditing(false)}>
                Cancel
              </Button>
              <Button
                disabled={update.isPending}
                onClick={() => update.mutate(draft, { onSuccess: () => setEditing(false) })}
              >
                Save
              </Button>
            </div>
          </div>
        ) : (
          <p className="whitespace-pre-wrap text-sm">
            {incident.description || (
              <span className="text-muted-foreground">No description yet.</span>
            )}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function NewActionItem({ incidentId }: { incidentId: string }) {
  const [description, setDescription] = useState("")
  const [assignee, setAssignee] = useState<number | null>(null)
  const create = useCreateActionItem(incidentId)

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!description.trim()) return
    create.mutate(
      { description: description.trim(), assignee_id: assignee },
      {
        onSuccess: () => {
          setDescription("")
          setAssignee(null)
        },
      },
    )
  }

  return (
    <form onSubmit={submit} className="flex flex-wrap gap-2 border-t pt-4">
      <Input
        className="min-w-48 flex-1"
        placeholder="New action item"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />
      <div className="w-44">
        <MemberSelect allowNone value={assignee} onChange={setAssignee} />
      </div>
      <Button type="submit" disabled={!description.trim() || create.isPending}>
        <PlusIcon /> Add
      </Button>
    </form>
  )
}

function ResolveButton({ incident }: { incident: Incident }) {
  const [open, setOpen] = useState(false)
  const resolve = useResolveIncident(incident.id)

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline">
          <CheckCircle2Icon /> Resolve
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Resolve {incident.name}?</DialogTitle>
          <DialogDescription>
            This marks the incident resolved and posts in its Slack channel.
            {incident.open_action_items > 0 &&
              ` ${incident.open_action_items} action item(s) are still open.`}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="ghost">Cancel</Button>
          </DialogClose>
          <Button
            disabled={resolve.isPending}
            onClick={() => resolve.mutate(undefined, { onSuccess: () => setOpen(false) })}
          >
            Resolve
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
