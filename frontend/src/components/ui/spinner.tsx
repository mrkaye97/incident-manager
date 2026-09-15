import { Loader2Icon } from "lucide-react"

import { cn } from "@/lib/utils"

function Spinner({ className }: { className?: string }) {
  return (
    <Loader2Icon
      data-slot="spinner"
      role="status"
      aria-label="Loading"
      className={cn("animate-spin", className)}
    />
  )
}

function LoadingState({ className }: { className?: string }) {
  return (
    <div className={cn("flex justify-center py-10 text-muted-foreground", className)}>
      <Spinner className="size-5" />
    </div>
  )
}

export { LoadingState, Spinner }
