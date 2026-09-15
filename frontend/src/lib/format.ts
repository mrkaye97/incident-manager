import { format, formatDistanceStrict, formatDistanceToNow } from "date-fns"

export const slackChannelUrl = (channelId: string) =>
  `https://slack.com/app_redirect?channel=${encodeURIComponent(channelId)}`

// TODO: deep-link to the incident once the status page integration exists
export const statusPageUrl = (base: string, _incidentId: string) => base

export const dateTime = (iso: string) => format(new Date(iso), "MMM d, HH:mm")

export const date = (iso: string) => format(new Date(iso), "EEE MMM d")

export const ago = (iso: string) => formatDistanceToNow(new Date(iso), { addSuffix: true })

export const duration = (start: string, end: string | null | undefined) =>
  formatDistanceStrict(new Date(start), end ? new Date(end) : new Date())

export const levelLabel = (level: "PRIMARY" | "SECONDARY") =>
  level === "PRIMARY" ? "Primary" : "Secondary"
