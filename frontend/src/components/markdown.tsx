import ReactMarkdown from "react-markdown"
import remarkBreaks from "remark-breaks"
import remarkGfm from "remark-gfm"

import { cn } from "@/lib/utils"

function withoutNode<T extends { node?: unknown }>(props: T): Omit<T, "node"> {
  const { node, ...rest } = props
  void node
  return rest
}

export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn("grid gap-2 text-sm break-words", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks]}
        components={{
          a: (props) => (
            <a {...withoutNode(props)} target="_blank" rel="noreferrer" className="underline" />
          ),
          pre: (props) => (
            <pre
              {...withoutNode(props)}
              className="max-h-96 overflow-auto rounded-md border bg-muted p-3 font-mono text-xs leading-relaxed whitespace-pre"
            />
          ),
          code: ({ className, ...props }) => (
            <code
              {...withoutNode(props)}
              className={cn(
                "font-mono text-xs",
                !className && "rounded bg-muted px-1 py-0.5 [pre_&]:bg-transparent [pre_&]:p-0",
                className,
              )}
            />
          ),
          ul: (props) => <ul {...withoutNode(props)} className="list-disc pl-5" />,
          ol: (props) => <ol {...withoutNode(props)} className="list-decimal pl-5" />,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  )
}
