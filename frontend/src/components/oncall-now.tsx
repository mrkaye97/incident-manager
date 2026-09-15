import { useQuery } from "@tanstack/react-query"
import { BellRingIcon } from "lucide-react"

import { PageDialog } from "@/components/page-dialog"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { LoadingState } from "@/components/ui/spinner"
import { oncallQuery } from "@/lib/api"
import { levelLabel } from "@/lib/format"

export function OnCallNow() {
  const { data: oncall = [], isLoading } = useQuery(oncallQuery)

  return (
    <Card>
      <CardHeader>
        <CardTitle>On call now</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3">
        {isLoading && <LoadingState className="py-4" />}
        {!isLoading && oncall.length === 0 && (
          <p className="text-sm text-muted-foreground">Nobody is on call.</p>
        )}
        {oncall.map((entry) => (
          <div
            key={entry.level}
            className="flex items-center justify-between gap-2"
          >
            <div>
              <p className="font-medium">{entry.name}</p>
              <p className="text-xs text-muted-foreground">
                {levelLabel(entry.level)}
              </p>
            </div>
            <PageDialog
              memberId={entry.team_member_id}
              trigger={
                <Button variant="outline" size="sm">
                  <BellRingIcon /> Page
                </Button>
              }
            />
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
