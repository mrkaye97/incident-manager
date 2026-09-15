import { useQuery } from "@tanstack/react-query"
import { useState } from "react"

import { ActionItemList } from "@/components/action-item-list"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { LoadingState } from "@/components/ui/spinner"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { actionItemsQuery } from "@/lib/api"

export function ActionItemsPage() {
  const [openOnly, setOpenOnly] = useState(true)
  const { data: items = [], isLoading } = useQuery(actionItemsQuery(openOnly))

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle>Action items</CardTitle>
        <Tabs value={openOnly ? "open" : "all"} onValueChange={(v) => setOpenOnly(v === "open")}>
          <TabsList>
            <TabsTrigger value="open">Open</TabsTrigger>
            <TabsTrigger value="all">All</TabsTrigger>
          </TabsList>
        </Tabs>
      </CardHeader>
      <CardContent>
        {isLoading ? <LoadingState /> : <ActionItemList items={items} showIncident />}
      </CardContent>
    </Card>
  )
}
