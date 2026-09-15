import { SirenIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { loginUrl } from "@/lib/api"

const ERRORS: Record<string, string> = {
  not_allowed: "Only full members of the Slack workspace can sign in.",
  invalid_state: "That sign-in link expired. Try again.",
  slack_error: "Slack couldn't complete the sign-in. Try again.",
  access_denied: "Sign-in was cancelled.",
}

export type LoginSearch = { next?: string; error?: string }

export function LoginPage({ next, error }: LoginSearch) {
  return (
    <div className="flex min-h-svh items-center justify-center bg-muted/30 px-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="items-center text-center">
          <SirenIcon className="mx-auto size-8 text-destructive" />
          <CardTitle>Incident Manager</CardTitle>
          <CardDescription>Sign in with your Slack account.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          {error && (
            <p className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
              {ERRORS[error] ?? "Sign-in failed. Try again."}
            </p>
          )}
          <Button asChild>
            <a href={loginUrl(next ?? "/")}>Sign in with Slack</a>
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
