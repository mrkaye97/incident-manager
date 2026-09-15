import { useQuery } from "@tanstack/react-query"

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { membersQuery } from "@/lib/api"

const NONE = "none"

export function MemberSelect({
  value,
  onChange,
  placeholder = "Select a person",
  allowNone = false,
  noneLabel = "Unassigned",
  id,
}: {
  value: string | null
  onChange: (value: string | null) => void
  placeholder?: string
  allowNone?: boolean
  noneLabel?: string
  id?: string
}) {
  const { data: members = [] } = useQuery(membersQuery)

  return (
    <Select
      value={value ?? (allowNone ? NONE : "")}
      onValueChange={(v) => onChange(v === NONE ? null : v)}
    >
      <SelectTrigger id={id} className="w-full">
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {allowNone && <SelectItem value={NONE}>{noneLabel}</SelectItem>}
        {members.map((m) => (
          <SelectItem key={m.id} value={m.id}>
            {m.name}
            {!m.slack_user_id && <span className="text-muted-foreground"> (no Slack)</span>}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
