import { useQuery } from "@tanstack/react-query"
import { PencilIcon, PlusIcon, RefreshCwIcon } from "lucide-react"
import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { membersQuery, useSaveMember, useSyncMembers, type Member } from "@/lib/api"

export function TeamPage() {
  const { data: members = [] } = useQuery(membersQuery)
  const sync = useSyncMembers()

  return (
    <Card>
      <CardHeader>
        <CardTitle>Team</CardTitle>
        <CardDescription>
          Synced nightly from the Slack @eng group. Manual edits to names are overwritten by the
          next sync.
        </CardDescription>
        <CardAction className="flex gap-2">
          <Button variant="outline" size="sm" disabled={sync.isPending} onClick={() => sync.mutate()}>
            <RefreshCwIcon /> Sync from Slack
          </Button>
          <MemberDialog />
        </CardAction>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Slack handle</TableHead>
              <TableHead>Slack user ID</TableHead>
              <TableHead>Phone paging</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {members.map((member) => (
              <TableRow key={member.id}>
                <TableCell className="font-medium">{member.name}</TableCell>
                <TableCell>{member.slack_handle ? `@${member.slack_handle}` : "—"}</TableCell>
                <TableCell className="font-mono text-xs">{member.slack_user_id ?? "—"}</TableCell>
                <TableCell>
                  {member.pushover_user_key ? (
                    <Badge variant="secondary">Pushover</Badge>
                  ) : (
                    <span className="text-muted-foreground">Slack only</span>
                  )}
                </TableCell>
                <TableCell className="text-right">
                  <MemberDialog member={member} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

function MemberDialog({ member }: { member?: Member }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState("")
  const [slackUserId, setSlackUserId] = useState("")
  const [slackHandle, setSlackHandle] = useState("")
  const [pushoverUserKey, setPushoverUserKey] = useState("")
  const save = useSaveMember()

  const onOpenChange = (next: boolean) => {
    setOpen(next)
    if (next) {
      setName(member?.name ?? "")
      setSlackUserId(member?.slack_user_id ?? "")
      setSlackHandle(member?.slack_handle ?? "")
      setPushoverUserKey(member?.pushover_user_key ?? "")
    }
  }

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    save.mutate(
      {
        id: member?.id,
        name: name.trim(),
        slack_user_id: slackUserId.trim() || null,
        slack_handle: slackHandle.trim().replace(/^@/, "") || null,
        pushover_user_key: pushoverUserKey.trim() || null,
      },
      { onSuccess: () => setOpen(false) },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        {member ? (
          <Button variant="ghost" size="icon-sm" aria-label={`Edit ${member.name}`}>
            <PencilIcon />
          </Button>
        ) : (
          <Button size="sm">
            <PlusIcon /> Add member
          </Button>
        )}
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>{member ? `Edit ${member.name}` : "Add team member"}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="member-name">Name</Label>
            <Input id="member-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="member-slack-id">Slack user ID</Label>
            <Input
              id="member-slack-id"
              placeholder="U0123ABCD"
              value={slackUserId}
              onChange={(e) => setSlackUserId(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="member-slack-handle">Slack handle</Label>
            <Input
              id="member-slack-handle"
              value={slackHandle}
              onChange={(e) => setSlackHandle(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="member-pushover">Pushover user key</Label>
            <Input
              id="member-pushover"
              className="font-mono"
              placeholder="Shown on the Pushover app's home screen"
              value={pushoverUserKey}
              onChange={(e) => setPushoverUserKey(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={!name.trim() || save.isPending}>
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
