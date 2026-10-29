import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

export const MessageMarkdown = ({ content }: { content: string }) => (
  <div className="message-markdown min-w-0 text-sm leading-6 break-words">
    <Markdown
      remarkPlugins={[remarkGfm]}
      skipHtml
      components={{
        table: ({ children }) => (
          <div className="my-4 max-w-full overflow-x-auto rounded-lg border">
            <table>{children}</table>
          </div>
        ),
        img: ({ alt }) => <span className="text-muted-foreground">{alt}</span>,
        a: ({ children, href }) =>
          href ? (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ) : (
            <>{children}</>
          ),
      }}
    >
      {content}
    </Markdown>
  </div>
);
