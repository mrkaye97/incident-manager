import { useQuery } from "@tanstack/react-query"
import { addDays, format, startOfDay } from "date-fns"
import { ArrowDownIcon, ArrowUpIcon, PlusIcon, Trash2Icon, XIcon } from "lucide-react"
import { useMemo, useState } from "react"

import { MemberSelect } from "@/components/member-select"
import { OnCallNow } from "@/components/oncall-now"
import { Badge } from "@/components/ui/badge"
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { LoadingState } from "@/components/ui/spinner"
import {
  membersQuery,
  overridesQuery,
  rotationsQuery,
  scheduleQuery,
  useCreateOverride,
  useDeleteOverride,
  useDeleteRotation,
  useSaveRotation,
  type Member,
  type OnCallLevel,
  type Rotation,
} from "@/lib/api"
import { dateTime, levelLabel } from "@/lib/format"
import { cn } from "@/lib/utils"

const WINDOW_DAYS = 28

const MEMBER_COLORS = [
  "bg-sky-100 text-sky-900 border-sky-300",
  "bg-amber-100 text-amber-900 border-amber-300",
  "bg-emerald-100 text-emerald-900 border-emerald-300",
  "bg-violet-100 text-violet-900 border-violet-300",
  "bg-rose-100 text-rose-900 border-rose-300",
  "bg-teal-100 text-teal-900 border-teal-300",
  "bg-orange-100 text-orange-900 border-orange-300",
  "bg-indigo-100 text-indigo-900 border-indigo-300",
]

const LEVELS: OnCallLevel[] = ["PRIMARY", "SECONDARY"]

const memberColor = (id: string) => {
  let hash = 0
  for (const char of id) hash = (hash * 31 + char.charCodeAt(0)) >>> 0
  return MEMBER_COLORS[hash % MEMBER_COLORS.length]
}

export function OnCallPage() {
  const [window] = useState(() => {
    const start = startOfDay(new Date())
    return { start: start.toISOString(), end: addDays(start, WINDOW_DAYS).toISOString() }
  })
  const { data: members = [] } = useQuery(membersQuery)
  const { data: rotations = [], isLoading } = useQuery(rotationsQuery)
  const membersById = useMemo(() => new Map(members.map((m) => [m.id, m])), [members])

  return (
    <div className="grid gap-6">
      <div className="grid gap-6 lg:grid-cols-3">
        <OnCallNow />
        <div className="grid content-start gap-6 lg:col-span-2">
          {isLoading ? (
            <LoadingState />
          ) : (
            LEVELS.map((level) => (
              <RotationCard
                key={level}
                level={level}
                rotation={rotations.find((r) => r.level === level) ?? null}
                membersById={membersById}
              />
            ))
          )}
        </div>
      </div>
      <ScheduleCard windowStart={window.start} windowEnd={window.end} membersById={membersById} />
      <OverridesCard windowStart={window.start} windowEnd={window.end} />
    </div>
  )
}

function ScheduleCard({
  windowStart,
  windowEnd,
  membersById,
}: {
  windowStart: string
  windowEnd: string
  membersById: Map<string, Member>
}) {
  const { data: shifts = [], isLoading } = useQuery(scheduleQuery(windowStart, windowEnd))
  const start = new Date(windowStart).getTime()
  const span = new Date(windowEnd).getTime() - start
  const now = Date.now()

  const lanes = useMemo(
    () =>
      LEVELS.map((level) => [level, shifts.filter((s) => s.level === level)] as const).filter(
        ([, laneShifts]) => laneShifts.length > 0,
      ),
    [shifts],
  )

  const pct = (iso: string) =>
    Math.min(100, Math.max(0, ((new Date(iso).getTime() - start) / span) * 100))

  const days = Array.from({ length: WINDOW_DAYS }, (_, i) => addDays(new Date(windowStart), i))

  return (
    <Card>
      <CardHeader>
        <CardTitle>Schedule</CardTitle>
        <CardDescription>Next {WINDOW_DAYS} days, including overrides.</CardDescription>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        {isLoading ? (
          <LoadingState />
        ) : lanes.length === 0 ? (
          <p className="text-sm text-muted-foreground">No rotation configured.</p>
        ) : (
          <div className="grid min-w-[720px] grid-cols-[6rem_1fr] gap-y-2">
            <div />
            <div className="relative flex text-[10px] text-muted-foreground">
              {days.map((day) => (
                <div key={day.toISOString()} className="flex-1 border-l pl-0.5 whitespace-nowrap">
                  {day.getDay() === 1 || day.getTime() === start ? format(day, "MMM d") : ""}
                </div>
              ))}
            </div>
            {lanes.map(([level, laneShifts]) => (
              <div key={level} className="contents">
                <div className="self-center text-sm font-medium">{levelLabel(level)}</div>
                <div className="relative h-10 rounded-md bg-muted">
                  {laneShifts.map((shift) => {
                    const left = pct(shift.start)
                    const width = pct(shift.end) - left
                    const name = membersById.get(shift.team_member_id)?.name ?? "?"
                    return (
                      <div
                        key={`${shift.start}-${shift.team_member_id}-${shift.override_id}`}
                        title={`${name}: ${dateTime(shift.start)} → ${dateTime(shift.end)}${shift.override_id ? " (override)" : ""}`}
                        className={cn(
                          "absolute inset-y-0.5 flex items-center overflow-hidden rounded border px-1.5 text-xs whitespace-nowrap",
                          memberColor(shift.team_member_id),
                          shift.override_id &&
                            "border-2 border-dashed bg-[repeating-linear-gradient(45deg,transparent,transparent_4px,rgb(0_0_0/0.05)_4px,rgb(0_0_0/0.05)_8px)]",
                        )}
                        style={{ left: `${left}%`, width: `${width}%` }}
                      >
                        {name}
                      </div>
                    )
                  })}
                  {now >= start && now < start + span && (
                    <div
                      className="absolute inset-y-0 w-0.5 bg-destructive"
                      style={{ left: `${((now - start) / span) * 100}%` }}
                    />
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function RotationCard({
  level,
  rotation,
  membersById,
}: {
  level: OnCallLevel
  rotation: Rotation | null
  membersById: Map<string, Member>
}) {
  const remove = useDeleteRotation()

  return (
    <Card>
      <CardHeader>
        <CardTitle>{levelLabel(level)} rotation</CardTitle>
        <CardDescription>
          {rotation
            ? `Rotates every ${rotation.period_days} day(s) since ${format(new Date(`${rotation.anchor.slice(0, 10)}T00:00:00`), "MMM d, yyyy")} (UTC).`
            : level === "PRIMARY"
              ? "No primary rotation yet — nobody will be paged by default."
              : "Optional. Without one, there's no secondary on call."}
        </CardDescription>
        <CardAction className="flex gap-2">
          {rotation && level === "SECONDARY" && (
            <Button
              variant="ghost"
              size="sm"
              loading={remove.isPending}
              onClick={() => remove.mutate(level)}
            >
              Remove
            </Button>
          )}
          <RotationDialog level={level} rotation={rotation} membersById={membersById} />
        </CardAction>
      </CardHeader>
      {rotation && (
        <CardContent>
          <ol className="flex flex-wrap items-center gap-2 text-sm">
            {rotation.member_ids.map((id, i) => (
              <li key={id} className="flex items-center gap-2">
                {i > 0 && <span className="text-muted-foreground">→</span>}
                <span className={cn("rounded border px-2 py-0.5", memberColor(id))}>
                  {membersById.get(id)?.name ?? "Unknown"}
                </span>
              </li>
            ))}
          </ol>
        </CardContent>
      )}
    </Card>
  )
}

function RotationDialog({
  level,
  rotation,
  membersById,
}: {
  level: OnCallLevel
  rotation: Rotation | null
  membersById: Map<string, Member>
}) {
  const [open, setOpen] = useState(false)
  const [memberIds, setMemberIds] = useState<string[]>([])
  const [periodDays, setPeriodDays] = useState("7")
  const [anchor, setAnchor] = useState("")
  const save = useSaveRotation()

  const onOpenChange = (next: boolean) => {
    setOpen(next)
    if (next) {
      setMemberIds(rotation?.member_ids ?? [])
      setPeriodDays(String(rotation?.period_days ?? 7))
      // anchors are stored as UTC midnight, matching the old Slack flow
      setAnchor(rotation ? rotation.anchor.slice(0, 10) : format(new Date(), "yyyy-MM-dd"))
    }
  }

  const move = (index: number, delta: number) => {
    const next = [...memberIds]
    ;[next[index], next[index + delta]] = [next[index + delta], next[index]]
    setMemberIds(next)
  }

  const period = Number(periodDays)
  const valid = memberIds.length > 0 && Number.isInteger(period) && period >= 1 && anchor

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          {rotation ? "Edit" : "Configure"}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Configure {levelLabel(level).toLowerCase()} rotation</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label>Members, in rotation order</Label>
            <ol className="grid gap-1">
              {memberIds.map((id, i) => (
                <li key={id} className="flex items-center gap-1 rounded-md border px-2 py-1 text-sm">
                  <span className="w-5 text-muted-foreground tabular-nums">{i + 1}.</span>
                  <span className="flex-1">{membersById.get(id)?.name ?? "Unknown"}</span>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label="Move up"
                    disabled={i === 0}
                    onClick={() => move(i, -1)}
                  >
                    <ArrowUpIcon />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label="Move down"
                    disabled={i === memberIds.length - 1}
                    onClick={() => move(i, 1)}
                  >
                    <ArrowDownIcon />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label="Remove"
                    onClick={() => setMemberIds(memberIds.filter((m) => m !== id))}
                  >
                    <XIcon />
                  </Button>
                </li>
              ))}
            </ol>
            <MemberSelect
              value={null}
              placeholder="Add a member…"
              onChange={(id) => id !== null && !memberIds.includes(id) && setMemberIds([...memberIds, id])}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="period-days">Days per person</Label>
              <Input
                id="period-days"
                type="number"
                min={1}
                value={periodDays}
                onChange={(e) => setPeriodDays(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="anchor">First handoff (UTC)</Label>
              <Input
                id="anchor"
                type="date"
                value={anchor}
                onChange={(e) => setAnchor(e.target.value)}
              />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button
            disabled={!valid}
            loading={save.isPending}
            onClick={() =>
              save.mutate(
                {
                  level,
                  member_ids: memberIds,
                  period_days: period,
                  anchor: `${anchor}T00:00:00Z`,
                },
                { onSuccess: () => setOpen(false) },
              )
            }
          >
            Save rotation
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function OverridesCard({ windowStart, windowEnd }: { windowStart: string; windowEnd: string }) {
  const { data: overrides = [], isLoading } = useQuery(overridesQuery(windowStart, windowEnd))
  const remove = useDeleteOverride()

  return (
    <Card>
      <CardHeader>
        <CardTitle>Overrides</CardTitle>
        <CardDescription>Temporary swaps that take precedence over the rotation.</CardDescription>
        <CardAction>
          <OverrideDialog />
        </CardAction>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <LoadingState />
        ) : overrides.length === 0 ? (
          <p className="text-sm text-muted-foreground">No upcoming overrides.</p>
        ) : (
          <ul className="divide-y text-sm">
            {overrides.map((o) => (
              <li key={o.id} className="flex flex-wrap items-center gap-3 py-2">
                <Badge variant="outline">{levelLabel(o.level)}</Badge>
                <span className="font-medium">{o.member_name}</span>
                <span className="text-muted-foreground">
                  {dateTime(o.start)} → {dateTime(o.end)}
                </span>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="ml-auto"
                  aria-label="Delete override"
                  loading={remove.isPending && remove.variables === o.id}
                  onClick={() => remove.mutate(o.id)}
                >
                  <Trash2Icon />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

const toLocalInput = (d: Date) => format(d, "yyyy-MM-dd'T'HH:mm")

function OverrideDialog() {
  const [open, setOpen] = useState(false)
  const [memberId, setMemberId] = useState<string | null>(null)
  const [level, setLevel] = useState<OnCallLevel>("PRIMARY")
  const [start, setStart] = useState("")
  const [end, setEnd] = useState("")
  const create = useCreateOverride()

  const onOpenChange = (next: boolean) => {
    setOpen(next)
    if (next) {
      const now = new Date()
      setMemberId(null)
      setLevel("PRIMARY")
      setStart(toLocalInput(now))
      setEnd(toLocalInput(addDays(now, 1)))
    }
  }

  const valid = memberId !== null && start && end && new Date(end) > new Date(start)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <PlusIcon /> Add override
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add override</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="override-member">Who</Label>
            <MemberSelect id="override-member" value={memberId} onChange={setMemberId} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="override-level">Covering</Label>
            <Select value={level} onValueChange={(v) => setLevel(v as OnCallLevel)}>
              <SelectTrigger id="override-level" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LEVELS.map((l) => (
                  <SelectItem key={l} value={l}>
                    {levelLabel(l)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="override-start">Start</Label>
              <Input
                id="override-start"
                type="datetime-local"
                value={start}
                onChange={(e) => setStart(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="override-end">End</Label>
              <Input
                id="override-end"
                type="datetime-local"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
              />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button
            disabled={!valid}
            loading={create.isPending}
            onClick={() =>
              memberId !== null &&
              create.mutate(
                {
                  team_member_id: memberId,
                  level,
                  start: new Date(start).toISOString(),
                  end: new Date(end).toISOString(),
                },
                { onSuccess: () => setOpen(false) },
              )
            }
          >
            Add override
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
