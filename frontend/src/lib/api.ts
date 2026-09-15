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
export type Customer = Schemas["Customer"]
export type IncidentDetail = Schemas["IncidentDetail"]
export type IncidentStatus = Incident["status"]
export type ActionItem = Schemas["ActionItem"]
export type Member = Schemas["Member"]
export type MemberInput = Schemas["MemberInput"]
export type OnCallEntry = Schemas["OnCallEntry"]
export type OnCallLevel = OnCallEntry["level"]
export type Rotation = Schemas["Rotation"]
export type RotationInput = Schemas["RotationInput"]
export type Override = Schemas["Override"]
export type OverrideInput = Schemas["OverrideInput"]
export type Shift = Schemas["Shift"]
export type PageInput = Schemas["PageInput"]

const API_URL = import.meta.env.VITE_API_URL ?? ""

export const client = createClient<paths>({ baseUrl: API_URL, credentials: "include" })

export const loginUrl = (next: string) =>
  `${API_URL}/api/auth/login?next=${encodeURIComponent(next)}`

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
  if (response.status === 401 && window.location.pathname !== "/login") {
    const next = window.location.pathname + window.location.search
    window.location.assign(`/login?next=${encodeURIComponent(next)}`)
  }
  if (!response.ok) throw new ApiError(errorMessage(error))
  return data as T
}

// --- queries ---

export const meQuery = queryOptions({
  queryKey: ["me"],
  queryFn: () => unwrap(client.GET("/api/auth/me")),
  staleTime: Infinity,
})

export async function logout() {
  await client.POST("/api/auth/logout")
  window.location.assign("/login")
}

export const customersQuery = queryOptions({
  queryKey: ["customers"],
  queryFn: () => unwrap(client.GET("/api/customers")),
})

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

export const rotationsQuery = queryOptions({
  queryKey: ["oncall", "rotations"],
  queryFn: () => unwrap(client.GET("/api/rotations")),
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

export const useSaveCustomer = () =>
  useApiMutation(
    ({ id, name }: { id?: string; name: string }) =>
      id === undefined
        ? unwrap(client.POST("/api/customers", { body: { name } }))
        : unwrap(
            client.PUT("/api/customers/{customer_id}", {
              params: { path: { customer_id: id } },
              body: { name },
            }),
          ),
    { invalidate: [["customers"]], success: "Customer saved" },
  )

export const useUpdateIncidentCustomers = (id: string) =>
  useApiMutation(
    (customer_ids: string[]) =>
      unwrap(
        client.PUT("/api/incidents/{incident_id}/customers", {
          params: { path: { incident_id: id } },
          body: { customer_ids },
        }),
      ),
    { invalidate: [["incidents"]], success: "Affected customers updated" },
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
    ({ id, ...body }: Schemas["ActionItemUpdate"] & { id: string }) =>
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
    ({ id, ...body }: MemberInput & { id?: string }) =>
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
  useApiMutation(
    ({ level, ...body }: RotationInput & { level: OnCallLevel }) =>
      unwrap(client.PUT("/api/rotations/{level}", { params: { path: { level } }, body })),
    { invalidate: [["oncall"]], success: "Rotation saved" },
  )

export const useDeleteRotation = () =>
  useApiMutation(
    (level: OnCallLevel) =>
      unwrap(client.DELETE("/api/rotations/{level}", { params: { path: { level } } })),
    { invalidate: [["oncall"]], success: "Rotation removed" },
  )

export const useCreateOverride = () =>
  useApiMutation((body: OverrideInput) => unwrap(client.POST("/api/overrides", { body })), {
    invalidate: [["oncall"]],
    success: "Override added",
  })

export const useDeleteOverride = () =>
  useApiMutation(
    (id: string) =>
      unwrap(client.DELETE("/api/overrides/{override_id}", { params: { path: { override_id: id } } })),
    { invalidate: [["oncall"]], success: "Override removed" },
  )

export const usePage = () =>
  useApiMutation((body: PageInput) => unwrap(client.POST("/api/pages", { body })), {
    invalidate: [["incidents"]],
    success: "Page sent",
  })
