// @vitest-environment jsdom

import { describe, expect, it } from "vitest"

import { renderMarkdown } from "./markdown"

describe("renderMarkdown", () => {
  it("renders common Markdown", () => {
    const result = renderMarkdown("## Result\n\n- **One**\n- `two`")

    expect(result).toContain("<h2>Result</h2>")
    expect(result).toContain("<strong>One</strong>")
    expect(result).toContain("<code>two</code>")
  })

  it("does not render unsafe HTML or links", () => {
    const result = renderMarkdown('<script>alert(1)</script>\n\n[x](javascript:alert(1))')

    expect(result).not.toContain("<script")
    expect(result).not.toContain('href="javascript:')
  })

  it("rewrites workspace artifact links to the authenticated file API", () => {
    const result = renderMarkdown(
      "[report](/home/user/project/data/agents/assistant/workspace/reports/monthly%20report.xlsx)",
    )

    expect(result).toContain(
      'href="/api/files/download?path=reports%2Fmonthly%20report.xlsx"',
    )
    expect(result).not.toContain('target="_blank"')
  })

  it("does not rewrite paths that try to escape the workspace", () => {
    const result = renderMarkdown("[bad](/tmp/workspace/../secret.txt)")

    expect(result).toContain('href="/tmp/workspace/../secret.txt"')
    expect(result).not.toContain("/api/files/download")
  })
})
