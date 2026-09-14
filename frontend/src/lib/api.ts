import {
  queryOptions,
  useMutation,
  useQueryClient,
  type QueryKey,
} from "@tanstack/react-query"
import createClient from "openapi-fetch"
import { toast } from "sonner"

import type { components, paths } from "@/lib/api-schema"

type Schemas = components["schemas"]

export type AppConfig = Schemas["AppConfig"]
export type Incident = Schemas["IncidentSummary"]
export type IncidentDetail = Schemas["IncidentDetail"]
export type IncidentStatus = Incident["status"]
export type ActionItem = Schemas["ActionItem"]
export type Member = Schemas["Member"]
export type MemberInput = Schemas["MemberInput"]
export type OnCallEntry = Schemas["OnCallEntry"]
export type Rotation = Schemas["Rotation"]
export type RotationInput = Schemas["RotationInput"]
export type Override = Schemas["Override"]
export type OverrideInput = Schemas["OverrideInput"]
export type Shift = Schemas["Shift"]
export type PageInput = Schemas["PageInput"]

export const client = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_URL ?? "http://localhost:8000",
})

export class ApiError extends Error {}

function errorMessage(error: unknown): string {
  const detail = (error as { detail?: unknown } | undefined)?.detail
  if (typeof detail === "string") return detail
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => `${d.loc?.slice(1).join(".")}: ${d.msg}`)
      .join("; ")
  }
  return "Request failed"
}

async function unwrap<T>(
  request: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await request
  if (!response.ok) throw new ApiError(errorMessage(error))
  return data as T
}

// --- queries ---

export const configQuery = queryOptions({
  queryKey: ["config"],
  queryFn: () => unwrap(client.GET("/api/config")),
  staleTime: Infinity,
})

export const incidentsQuery = (status?: IncidentStatus) =>
  queryOptions({
    queryKey: ["incidents", { status }],
    queryFn: () => unwrap(client.GET("/api/incidents", { params: { query: { status } } })),
  })

export const incidentQuery = (id: string) =>
  queryOptions({
    queryKey: ["incidents", id],
    queryFn: () =>
      unwrap(client.GET("/api/incidents/{incident_id}", { params: { path: { incident_id: id } } })),
  })

export const actionItemsQuery = (openOnly: boolean) =>
  queryOptions({
    queryKey: ["action-items", { openOnly }],
    queryFn: () =>
      unwrap(client.GET("/api/action-items", { params: { query: { open_only: openOnly } } })),
  })

export const membersQuery = queryOptions({
  queryKey: ["members"],
  queryFn: () => unwrap(client.GET("/api/members")),
})

export const oncallQuery = queryOptions({
  queryKey: ["oncall", "current"],
  queryFn: () => unwrap(client.GET("/api/oncall")),
  refetchInterval: 60_000,
})

export const rotationQuery = queryOptions({
  queryKey: ["oncall", "rotation"],
  queryFn: () => unwrap(client.GET("/api/rotation")),
})

export const scheduleQuery = (start: string, end: string) =>
  queryOptions({
    queryKey: ["oncall", "schedule", { start, end }],
    queryFn: () => unwrap(client.GET("/api/schedule", { params: { query: { start, end } } })),
  })

export const overridesQuery = (start: string, end: string) =>
  queryOptions({
    queryKey: ["oncall", "overrides", { start, end }],
    queryFn: () => unwrap(client.GET("/api/overrides", { params: { query: { start, end } } })),
  })

// --- mutations ---

function useApiMutation<TVars, TData>(
  mutationFn: (vars: TVars) => Promise<TData>,
  { invalidate, success }: { invalidate: QueryKey[]; success?: string },
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: async () => {
      if (success) toast.success(success)
      await Promise.all(invalidate.map((queryKey) => queryClient.invalidateQueries({ queryKey })))
    },
    onError: (error) => toast.error(error.message),
  })
}

export const useCreateIncident = () =>
  useApiMutation(
    (body: Schemas["IncidentCreate"]) => unwrap(client.POST("/api/incidents", { body })),
    { invalidate: [["incidents"]], success: "Incident created" },
  )

export const useUpdateIncident = (id: string) =>
  useApiMutation(
    (description: string) =>
      unwrap(
        client.PATCH("/api/incidents/{incident_id}", {
          params: { path: { incident_id: id } },
          body: { description },
        }),
      ),
    { invalidate: [["incidents"]], success: "Description updated" },
  )

export const useResolveIncident = (id: string) =>
  useApiMutation(
    () =>
      unwrap(
        client.POST("/api/incidents/{incident_id}/resolve", {
          params: { path: { incident_id: id } },
        }),
      ),
    { invalidate: [["incidents"]], success: "Incident resolved" },
  )

export const useCreateActionItem = (incidentId: string) =>
  useApiMutation(
    (body: Schemas["ActionItemCreate"]) =>
      unwrap(
        client.POST("/api/incidents/{incident_id}/action-items", {
          params: { path: { incident_id: incidentId } },
          body,
        }),
      ),
    { invalidate: [["incidents"], ["action-items"]], success: "Action item added" },
  )

export const useUpdateActionItem = () =>
  useApiMutation(
    ({ id, ...body }: Schemas["ActionItemUpdate"] & { id: number }) =>
      unwrap(
        client.PATCH("/api/action-items/{action_item_id}", {
          params: { path: { action_item_id: id } },
          body,
        }),
      ),
    { invalidate: [["incidents"], ["action-items"]] },
  )

export const useSaveMember = () =>
  useApiMutation(
    ({ id, ...body }: MemberInput & { id?: number }) =>
      id === undefined
        ? unwrap(client.POST("/api/members", { body }))
        : unwrap(client.PUT("/api/members/{member_id}", { params: { path: { member_id: id } }, body })),
    { invalidate: [["members"], ["oncall"]], success: "Team member saved" },
  )

export const useSyncMembers = () =>
  useApiMutation(() => unwrap(client.POST("/api/members/sync")), {
    invalidate: [["members"]],
    success: "Slack sync started — refresh in a moment",
  })

export const useSaveRotation = () =>
  useApiMutation((body: RotationInput) => unwrap(client.PUT("/api/rotation", { body })), {
    invalidate: [["oncall"]],
    success: "Rotation saved",
  })

export const useCreateOverride = () =>
  useApiMutation((body: OverrideInput) => unwrap(client.POST("/api/overrides", { body })), {
    invalidate: [["oncall"]],
    success: "Override added",
  })

export const useDeleteOverride = () =>
  useApiMutation(
    (id: number) =>
      unwrap(client.DELETE("/api/overrides/{override_id}", { params: { path: { override_id: id } } })),
    { invalidate: [["oncall"]], success: "Override removed" },
  )

export const usePage = () =>
  useApiMutation((body: PageInput) => unwrap(client.POST("/api/pages", { body })), {
    invalidate: [["incidents"]],
    success: "Page sent",
  })
