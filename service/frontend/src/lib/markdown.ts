import DOMPurify from "dompurify"
import MarkdownIt from "markdown-it"

const markdown = new MarkdownIt({
  breaks: true,
  html: false,
  linkify: true,
  typographer: false,
})

const defaultLinkOpen = markdown.renderer.rules.link_open
markdown.renderer.rules.link_open = (tokens, index, options, environment, self) => {
  const token = tokens[index]
  const href = token?.attrGet("href")
  const workspaceHref = href ? workspaceDownloadHref(String(href)) : null
  if (workspaceHref) {
    token?.attrSet("href", workspaceHref)
  } else {
    token?.attrSet("target", "_blank")
    token?.attrSet("rel", "noopener noreferrer")
  }
  return defaultLinkOpen
    ? defaultLinkOpen(tokens, index, options, environment, self)
    : self.renderToken(tokens, index, options)
}

const defaultImage = markdown.renderer.rules.image
markdown.renderer.rules.image = (tokens, index, options, environment, self) => {
  const src = tokens[index]?.attrGet("src")
  const workspaceHref = src ? workspaceDownloadHref(String(src)) : null
  if (workspaceHref) tokens[index]?.attrSet("src", workspaceHref)
  return defaultImage
    ? defaultImage(tokens, index, options, environment, self)
    : self.renderToken(tokens, index, options)
}

function workspaceDownloadHref(value: string): string | null {
  let decoded: string
  try {
    decoded = decodeURI(value)
  } catch {
    return null
  }
  decoded = decoded.startsWith("file://") ? decoded.slice("file://".length) : decoded
  const marker = "/workspace/"
  const markerIndex = decoded.indexOf(marker)
  if (markerIndex < 0) return null
  const relative = decoded.slice(markerIndex + marker.length)
  const parts = relative.split("/").filter(Boolean)
  if (!parts.length || parts.some((part) => part === "." || part === "..")) return null
  return `/api/files/download?path=${encodeURIComponent(parts.join("/"))}`
}

export function renderMarkdown(content: string): string {
  return DOMPurify.sanitize(markdown.render(content), {
    USE_PROFILES: { html: true },
  })
}
