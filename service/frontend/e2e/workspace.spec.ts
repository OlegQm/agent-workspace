import { expect, test, type Page } from "@playwright/test"

const conversation = {
  id: "11111111-1111-4111-8111-111111111111",
  title: "Markdown conversation",
  kind: "standard" as const,
  created_at: "2026-08-16T00:00:00Z",
  updated_at: "2026-08-16T00:00:00Z",
}

async function mockWorkspace(
  page: Page,
  toolIds = ["metabase", "bigquery"],
  modelModes = [
    { value: "small", label: "Luna", description: "GPT-5.6 Luna" },
    { value: "medium", label: "Terra", description: "GPT-5.6 Terra" },
    { value: "high", label: "Sol", description: "GPT-5.6 Sol" },
  ],
  defaultModelMode = "medium",
) {
  const selectedConversation = { ...conversation }
  let conversations = [selectedConversation]
  let submittedModel: string | null = null
  let newConversationStarts = 0
  let expired = false
  let workspaceFiles = [{
    name: "outputs",
    path: "outputs",
    type: "directory",
    size: null,
    modified_at: 1_786_800_000,
    preview_kind: null,
    no_user_access: false,
    no_user_access_explicit: false,
    no_user_access_inherited: false,
    can_download: true,
    can_modify: true,
    can_copy: true,
  }, {
    name: "monthly-report.xlsx",
    path: "monthly-report.xlsx",
    type: "file",
    size: 12_400,
    modified_at: 1_786_800_000,
    preview_kind: "xlsx" as const,
    no_user_access: false,
    no_user_access_explicit: false,
    no_user_access_inherited: false,
    can_download: true,
    can_modify: true,
    can_copy: true,
  }, {
    name: "confidential.docx",
    path: "confidential.docx",
    type: "file",
    size: 4_200,
    modified_at: 1_786_800_000,
    preview_kind: "docx" as const,
    no_user_access: true,
    no_user_access_explicit: true,
    no_user_access_inherited: false,
    can_download: false,
    can_modify: false,
    can_copy: false,
  }, {
    name: "board-report.pdf",
    path: "board-report.pdf",
    type: "file",
    size: 8_200,
    modified_at: 1_786_800_000,
    preview_kind: "pdf" as const,
    no_user_access: false,
    no_user_access_explicit: false,
    no_user_access_inherited: false,
    can_download: true,
    can_modify: true,
    can_copy: true,
  }, {
    name: "calculation-notes.txt",
    path: "calculation-notes.txt",
    type: "file",
    size: 180,
    modified_at: 1_786_800_000,
    preview_kind: "txt" as const,
    no_user_access: false,
    no_user_access_explicit: false,
    no_user_access_inherited: false,
    can_download: true,
    can_modify: true,
    can_copy: true,
  }, {
    name: "usage-chart.png",
    path: "usage-chart.png",
    type: "file",
    size: 96,
    modified_at: 1_786_800_000,
    preview_kind: "image" as const,
    no_user_access: false,
    no_user_access_explicit: false,
    no_user_access_inherited: false,
    can_download: true,
    can_modify: true,
    can_copy: true,
  }]
  const messages = new Map<string, object[]>([[conversation.id, [{
    id: "33333333-3333-4333-8333-333333333333",
    role: "assistant",
    content: "## Result\n\n- **One**\n- Two\n\n| Source | Rows |\n| --- | ---: |\n| BigQuery | 12 |",
    attachments: [],
    created_at: "2026-08-16T00:00:00Z",
  }]]])

  await page.route("**/api/**", async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname

    if (expired && path !== "/api/auth/login") {
      await route.fulfill({ status: 401, json: { detail: "Session expired" } })
      return
    }

    if (path === "/api/auth/me") {
      await route.fulfill({ json: {
        id: "22222222-2222-4222-8222-222222222222",
        username: "assistant",
        agent_id: "assistant",
        agent_name: "Assistant",
        locale: "en",
        tools: toolIds,
        model_modes: modelModes,
        default_model_mode: defaultModelMode,
        is_admin: false,
      } })
      return
    }
    if (path === "/api/conversations" && request.method() === "GET") {
      await route.fulfill({ json: conversations })
      return
    }
    const conversationMatch = path.match(/^\/api\/conversations\/([^/]+)$/)
    if (conversationMatch && request.method() === "GET") {
      const item = conversations.find((entry) => entry.id === conversationMatch[1])
      if (!item) {
        await route.fulfill({ status: 404, json: { detail: "Not found" } })
        return
      }
      await route.fulfill({ json: {
        ...item,
        messages: messages.get(item.id) ?? [],
        runs: [],
      } })
      return
    }
    if (conversationMatch && request.method() === "DELETE") {
      conversations = conversations.filter((item) => item.id !== conversationMatch[1])
      await route.fulfill({ status: 204, body: "" })
      return
    }
    if (path === "/api/conversations/runs" && request.method() === "POST") {
      const payload = request.postDataJSON()
      const item = {
        id: "55555555-5555-4555-8555-555555555555",
        title: payload.content,
        created_at: "2026-08-16T00:00:00Z",
        updated_at: "2026-08-16T00:00:00Z",
      }
      newConversationStarts += 1
      submittedModel = payload.model_mode
      conversations = [item, ...conversations]
      messages.set(item.id, [{
        id: "66666666-6666-4666-8666-666666666666",
        role: "user",
        content: payload.content,
        attachments: payload.attachments,
        created_at: "2026-08-16T00:00:00Z",
      }])
      await route.fulfill({ status: 202, json: {
        conversation: item,
        run: {
          id: "77777777-7777-4777-8777-777777777777",
          conversation_id: item.id,
          status: "queued",
          model_mode: submittedModel,
          error: null,
          created_at: "2026-08-16T00:00:00Z",
          updated_at: "2026-08-16T00:00:00Z",
        },
      } })
      return
    }
    if (path === `/api/conversations/${conversation.id}/runs` && request.method() === "POST") {
      submittedModel = request.postDataJSON().model_mode
      await route.fulfill({ status: 202, json: {
        id: "44444444-4444-4444-8444-444444444444",
        conversation_id: conversation.id,
        status: "queued",
        model_mode: submittedModel,
        error: null,
        created_at: "2026-08-16T00:00:00Z",
        updated_at: "2026-08-16T00:00:00Z",
      } })
      return
    }
    if (path.endsWith("/events") && request.method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: "event: stream-end\ndata: {\"status\":\"completed\"}\n\n",
      })
      return
    }
    if (path === "/api/files" && request.method() === "GET") {
      const requestedPath = new URL(request.url()).searchParams.get("path") ?? ""
      await route.fulfill({ json: {
        entries: requestedPath ? [] : workspaceFiles,
        used_bytes: 12_400,
        limit_bytes: 10_000_000,
      } })
      return
    }
    if (path === "/api/files" && request.method() === "PATCH") {
      const payload = request.postDataJSON()
      const entry = workspaceFiles.find((item) => item.path === payload.path)
      if (!entry) {
        await route.fulfill({ status: 404, json: { detail: "Path not found" } })
        return
      }
      const parent = entry.path.split("/").slice(0, -1).join("/")
      const renamedPath = [parent, payload.new_name].filter(Boolean).join("/")
      workspaceFiles = workspaceFiles.map((item) => item.path === entry.path
        ? { ...item, name: payload.new_name, path: renamedPath }
        : item)
      await route.fulfill({ json: { path: renamedPath } })
      return
    }
    if (path === "/api/files/preview" && request.method() === "GET") {
      const requestedPath = new URL(request.url()).searchParams.get("path") ?? ""
      if (requestedPath.endsWith(".pdf")) {
        await route.fulfill({ json: { kind: "pdf", page_count: 2, pages: [{ width: 595, height: 842 }, { width: 595, height: 842 }] } })
        return
      }
      if (requestedPath.endsWith(".txt")) {
        await route.fulfill({ json: {
          kind: "txt",
          content: "Utilization summary\n\nIn use = resources assigned to an active project\nAvailable = ready resources without an assignment",
          truncated: false,
        } })
        return
      }
      if (requestedPath.endsWith(".png")) {
        await route.fulfill({ json: {
          kind: "image",
          media_type: "image/png",
          width: 1,
          height: 1,
        } })
        return
      }
      if (requestedPath.endsWith(".xlsx")) {
        const detailRows = Array.from({ length: 498 }, (_, index) => [
          { value: `Detail row ${index + 3}`, display: `Detail row ${index + 3}`, style_id: 0, row_span: 1, column_span: 1 },
          { value: "EUR", display: "EUR", style_id: 0, row_span: 1, column_span: 1 },
          { value: index, display: String(index), style_id: 2, row_span: 1, column_span: 1 },
        ])
        await route.fulfill({ json: {
          kind: "xlsx",
          sheets: ["vyuctovanie", "superfaktura"],
          sheet: "vyuctovanie",
          rows: [
            [
              { value: "Monthly settlement", display: "Monthly settlement", style_id: 1, row_span: 1, column_span: 3 },
              null,
              null,
            ],
            [
              { value: "Revenue", display: "Revenue", style_id: 0, row_span: 1, column_span: 1 },
              { value: "EUR", display: "EUR", style_id: 0, row_span: 1, column_span: 1 },
              { value: 1696.44, display: "1,696.44", style_id: 2, row_span: 1, column_span: 1 },
            ],
            ...detailRows,
          ],
          column_widths: [220, 70, 110],
          row_heights: [28, 22, ...Array.from({ length: 498 }, () => 22)],
          styles: [
            {},
            { bold: true, font_color: "#FFFFFF", fill_color: "#002060", horizontal: "center" },
            { horizontal: "right", border_bottom: { style: "thin", color: "#808080" } },
          ],
          show_gridlines: true,
          truncated: false,
          styled: true,
        } })
        return
      }
      await route.fulfill({ json: {
        kind: "docx",
        blocks: [{
          type: "paragraph",
          text: "Protected summary",
          style: "Heading 1",
          alignment: "left",
          list_kind: null,
          list_level: null,
          space_before: 0,
          space_after: 8,
          left_indent: null,
          right_indent: null,
          first_line_indent: null,
          line_spacing_pixels: null,
          line_spacing_multiple: 1.15,
          runs: [
            {
              text: "Protected summary ", href: null, bold: true, italic: false, underline: false,
              strike: false, superscript: false, subscript: false, font_size: 18,
              font_color: null, font_name: "Aptos", highlight_color: null,
            },
            {
              text: "Policy", href: "https://example.com/policy", bold: false, italic: false,
              underline: true, strike: false, superscript: false, subscript: false,
              font_size: 18, font_color: "#0563C1", font_name: "Aptos", highlight_color: null,
            },
          ],
        }],
        truncated: false,
        page: { width: 794, height: 1123, margin_top: 72, margin_right: 72, margin_bottom: 72, margin_left: 72 },
      } })
      return
    }
    if (path === "/api/files/preview/pdf-page" && request.method() === "GET") {
      await route.fulfill({
        contentType: "image/png",
        body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=", "base64"),
      })
      return
    }
    if (path === "/api/files/preview/image" && request.method() === "GET") {
      await route.fulfill({
        contentType: "image/png",
        body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=", "base64"),
      })
      return
    }

    await route.fulfill({ status: 404, json: { detail: `Unhandled test route: ${request.method()} ${path}` } })
  })

  return {
    expireSession: () => { expired = true },
    newConversationStarts: () => newConversationStarts,
    submittedModel: () => submittedModel,
  }
}

async function mockLoggedOut(page: Page) {
  await page.route("**/api/**", async (route) => {
    await route.fulfill({ status: 401, json: { detail: "Not authenticated" } })
  })
}

async function mockAdmin(page: Page) {
  let restricted = true
  const conversationId = "77777777-7777-4777-8777-777777777777"
  const managedUser = {
    id: "88888888-8888-4888-8888-888888888888",
    username: "assistant",
    agent_id: "assistant",
    agent_name: "Assistant",
    locale: "en",
    is_active: true,
  }
  await page.route("**/api/**", async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === "/api/auth/me") {
      await route.fulfill({ json: {
        id: "99999999-9999-4999-8999-999999999999",
        username: "admin",
        agent_id: null,
        agent_name: "Administration",
        locale: "en",
        tools: [],
        is_admin: true,
      } })
      return
    }
    if (path === "/api/admin/users") {
      await route.fulfill({ json: [managedUser] })
      return
    }
    if (path === `/api/admin/users/${managedUser.id}/conversations` && request.method() === "GET") {
      await route.fulfill({ json: [{
        id: conversationId,
        title: "July revenue review",
        kind: "metabase_planning",
        created_at: "2026-08-15T08:00:00Z",
        updated_at: "2026-08-16T09:30:00Z",
      }] })
      return
    }
    if (path === `/api/admin/users/${managedUser.id}/conversations/${conversationId}` && request.method() === "GET") {
      await route.fulfill({ json: {
        id: conversationId,
        title: "July revenue review",
        kind: "metabase_planning",
        created_at: "2026-08-15T08:00:00Z",
        updated_at: "2026-08-16T09:30:00Z",
        messages: [
          {
            id: "66666666-6666-4666-8666-666666666661",
            role: "user",
            content: "Compare July revenue with June.",
            attachments: ["reports/july.xlsx"],
            created_at: "2026-08-16T09:25:00Z",
          },
          {
            id: "66666666-6666-4666-8666-666666666662",
            role: "assistant",
            content: "## Result\n\nRevenue increased by **12%**.\n\n- July is higher\n- VAT treatment is unchanged",
            attachments: [],
            created_at: "2026-08-16T09:30:00Z",
          },
        ],
        runs: [],
      } })
      return
    }
    if (path === `/api/admin/users/${managedUser.id}/conversations/${conversationId}/export` && request.method() === "GET") {
      await route.fulfill({
        body: JSON.stringify({ id: conversationId, title: "July revenue review", messages: [], runs: [] }),
        contentType: "application/json",
        headers: { "Content-Disposition": `attachment; filename="conversation-${conversationId}.json"` },
      })
      return
    }
    if (path === `/api/admin/users/${managedUser.id}/files` && request.method() === "GET") {
      await route.fulfill({ json: {
        entries: [{
          name: "board-report.pdf",
          path: "board-report.pdf",
          type: "file",
          size: 8_200,
          modified_at: 1_786_800_000,
          preview_kind: "pdf",
          no_user_access: restricted,
          no_user_access_explicit: restricted,
          no_user_access_inherited: false,
          can_download: true,
          can_modify: true,
          can_copy: true,
        }],
        used_bytes: 8_200,
        limit_bytes: 10_000_000,
      } })
      return
    }
    if (path.endsWith("/files/access") && request.method() === "PUT") {
      restricted = request.postDataJSON().no_user_access
      await route.fulfill({ json: { path: "board-report.pdf", no_user_access: restricted } })
      return
    }
    if (path.endsWith("/files/preview") && request.method() === "GET") {
      await route.fulfill({ json: { kind: "pdf", page_count: 1, pages: [{ width: 595, height: 842 }] } })
      return
    }
    if (path.endsWith("/files/preview/pdf-page") && request.method() === "GET") {
      await route.fulfill({
        contentType: "image/png",
        body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=", "base64"),
      })
      return
    }
    await route.fulfill({ status: 404, json: { detail: `Unhandled admin route: ${request.method()} ${path}` } })
  })
}

test("login form uses the available viewport width", async ({ page }, testInfo) => {
  await mockLoggedOut(page)
  await page.goto("/")

  const panel = page.locator("main section")
  await expect(panel).toBeVisible()
  const box = await panel.boundingBox()
  expect(box).not.toBeNull()
  expect(box!.width).toBeGreaterThan(testInfo.project.name === "mobile" ? 350 : 500)
  expect(box!.width).toBeLessThanOrEqual(page.viewportSize()!.width - 32)
  await page.screenshot({ path: testInfo.outputPath("login.png"), fullPage: true })
})

test("renders Markdown and removes a deleted conversation", async ({ page }, testInfo) => {
  await mockWorkspace(page)
  await page.goto("/")

  if (testInfo.project.name === "mobile") {
    await page.getByRole("button", { name: "Open navigation" }).click()
  }
  await page.getByRole("button", { name: conversation.title, exact: true }).click()

  await expect(page.getByRole("heading", { name: "Result" })).toBeVisible()
  await expect(page.locator("strong", { hasText: "One" })).toBeVisible()
  await expect(page.getByRole("cell", { name: "BigQuery" })).toBeVisible()
  if (testInfo.project.name === "mobile") await page.waitForTimeout(250)
  await page.screenshot({ path: testInfo.outputPath("markdown-workspace.png"), fullPage: true })

  if (testInfo.project.name === "mobile") {
    await page.getByRole("button", { name: "Open navigation" }).click()
  }
  page.once("dialog", (dialog) => dialog.accept())
  await page.getByRole("button", { name: `Delete: ${conversation.title}` }).click()

  await expect(page.getByRole("button", { name: conversation.title, exact: true })).toHaveCount(0)
  await expect(page.getByRole("heading", { name: "Start a focused workspace conversation" })).toBeVisible()
  await expect(page.getByPlaceholder("Message your agent...")).toHaveCount(0)
})

test("keeps one local draft and creates it with the first message", async ({ page }, testInfo) => {
  await page.addInitScript(() => {
    Object.defineProperty(Crypto.prototype, "randomUUID", {
      configurable: true,
      value: undefined,
    })
  })
  const capture = await mockWorkspace(page)
  await page.goto("/")

  await expect(page.getByPlaceholder("Message your agent...")).toHaveCount(0)
  await page.screenshot({ path: testInfo.outputPath("start-screen.png"), fullPage: true })
  await page.getByRole("button", { name: "New conversation" }).last().click()
  await expect(page.getByPlaceholder("Message your agent...")).toBeVisible()

  if (testInfo.project.name === "mobile") {
    await page.getByRole("button", { name: "Open navigation" }).click()
    await page.getByRole("button", { name: "New conversation" }).first().click()
  } else {
    await page.getByRole("button", { name: "New conversation" }).click()
  }
  await expect.poll(capture.newConversationStarts).toBe(0)

  await page.getByPlaceholder("Message your agent...").fill("First persisted message")
  await page.getByRole("button", { name: "Send" }).click()
  await expect.poll(capture.newConversationStarts).toBe(1)
})

test("returns to login when an authenticated request receives 401", async ({ page }, testInfo) => {
  const capture = await mockWorkspace(page)
  await page.goto("/")

  if (testInfo.project.name === "mobile") {
    await page.getByRole("button", { name: "Open navigation" }).click()
  }
  await expect(page.getByRole("button", { name: conversation.title, exact: true })).toBeVisible()
  capture.expireSession()
  page.once("dialog", (dialog) => dialog.accept())
  await page.getByRole("button", { name: conversation.title, exact: true }).hover()
  await page.getByRole("button", { name: `Delete: ${conversation.title}` }).click()

  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible()
  await expect(page.getByText("Your session expired. Sign in again.")).toBeVisible()
})

test("selects a fixed GPT-5.6 mode and submits its server mode", async ({ page }, testInfo) => {
  const capture = await mockWorkspace(page)
  await page.addInitScript(() => localStorage.setItem("open-agent-workspace-model-mode", "medium"))
  await page.goto("/")

  if (testInfo.project.name === "mobile") {
    await page.getByRole("button", { name: "Open navigation" }).click()
  }
  await page.getByRole("button", { name: conversation.title, exact: true }).click()

  const medium = page.getByRole("radio", { name: "Medium - GPT-5.6 Terra" })
  await expect(medium).toHaveAttribute("aria-checked", "true")
  await medium.click()
  await expect(medium).toHaveAttribute("aria-checked", "true")
  await page.getByPlaceholder("Message your agent...").fill("Use the selected model")
  await page.getByRole("button", { name: "Send" }).click()

  await expect.poll(capture.submittedModel).toBe("medium")
  await expect.poll(() => page.evaluate(() => localStorage.getItem("open-agent-workspace-model-mode-v2"))).toBe("medium")
})

test("uses the agent's configured model names and default mode", async ({ page }, testInfo) => {
  await mockWorkspace(page, ["metabase"], [
    { value: "small", label: "Quick", description: "Example Quick" },
    { value: "medium", label: "Balanced", description: "Example Balanced" },
    { value: "high", label: "Deep", description: "Example Deep" },
  ], "high")
  await page.goto("/")
  if (testInfo.project.name === "mobile") {
    await page.getByRole("button", { name: "Open navigation" }).click()
  }
  await page.getByRole("button", { name: conversation.title, exact: true }).click()

  await expect(page.getByRole("radio", { name: "High - Example Deep" })).toHaveAttribute("aria-checked", "true")
  await expect(page.getByRole("radio", { name: "Medium - Example Balanced" })).toBeVisible()
})

test("mobile navigation and files are usable without horizontal overflow", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile", "Mobile-only layout check")
  await mockWorkspace(page)
  await page.goto("/")

  await page.getByRole("button", { name: "Open navigation" }).click()
  const navigation = page.getByLabel("Conversation navigation")
  await expect(navigation).toBeVisible()
  await navigation.getByRole("button", { name: "Close navigation" }).click()

  await page.getByTitle("Files").click()
  const files = page.getByLabel("Workspace files")
  await expect(files).toBeVisible()
  await page.waitForTimeout(250)
  await page.screenshot({ path: testInfo.outputPath("mobile-files.png"), fullPage: true })
  await files.getByRole("button", { name: "Close files" }).click()

  const hasOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
  expect(hasOverflow).toBe(false)
})

test("renames entries and copies workspace-relative paths", async ({ page, context }, testInfo) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"])
  await mockWorkspace(page)
  await page.goto("/")

  if (testInfo.project.name === "mobile") await page.getByTitle("Files").click()
  const panel = page.getByLabel("Workspace files")
  await panel.getByRole("button", { name: "Actions: monthly-report.xlsx" }).click()
  await panel.getByRole("button", { name: "Rename", exact: true }).click()

  const dialog = page.getByRole("dialog", { name: "Rename file or folder" })
  await expect(dialog).toBeVisible()
  const dialogBox = await dialog.boundingBox()
  const viewport = page.viewportSize()
  expect(dialogBox).not.toBeNull()
  expect(viewport).not.toBeNull()
  expect(dialogBox!.x).toBeGreaterThanOrEqual(0)
  expect(dialogBox!.x + dialogBox!.width).toBeLessThanOrEqual(viewport!.width + 1)
  expect(dialogBox!.y + dialogBox!.height).toBeLessThanOrEqual(viewport!.height + 1)
  if (testInfo.project.name === "desktop") {
    expect(Math.abs(dialogBox!.x + dialogBox!.width / 2 - viewport!.width / 2)).toBeLessThan(2)
  } else {
    expect(Math.abs(dialogBox!.y + dialogBox!.height - viewport!.height)).toBeLessThan(2)
  }
  await page.screenshot({ path: testInfo.outputPath("rename-dialog.png"), fullPage: true })
  await dialog.getByLabel("New name").fill("july-report.xlsx")
  await dialog.getByRole("button", { name: "Save" }).click()
  await expect(panel.getByText("july-report.xlsx", { exact: true })).toBeVisible()

  await panel.getByRole("button", { name: "Actions: july-report.xlsx" }).click()
  await panel.getByRole("button", { name: "Copy relative path" }).click()
  await expect(panel.getByRole("status")).toContainText("july-report.xlsx")
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe("july-report.xlsx")
  await page.screenshot({ path: testInfo.outputPath("file-actions.png"), fullPage: true })
})

test("tools page reflects the authenticated agent allowlist", async ({ page }, testInfo) => {
  await mockWorkspace(page, [
    "metabase", "bigquery", "google_ads", "meta_ads", "google_analytics", "clickup", "code",
  ])
  await page.goto("/")

  if (testInfo.project.name === "mobile") await page.getByRole("button", { name: "Open navigation" }).click()
  const navigation = page.getByLabel("Conversation navigation")
  await navigation.getByRole("button", { name: "Tools & data" }).click()
  if (testInfo.project.name === "mobile") await expect(navigation).not.toBeVisible()

  await expect(page.getByRole("heading", { name: "Google Ads" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Meta Ads" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Google Analytics" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "SuperFaktúra" })).toHaveCount(0)
  await page.screenshot({ path: testInfo.outputPath("tools-page.png"), fullPage: true })
})

test("protected documents are preview-only for regular users", async ({ page, context }, testInfo) => {
  await mockWorkspace(page)
  await page.goto("/")
  if (testInfo.project.name === "mobile") await page.getByTitle("Files").click()

  const panel = page.getByLabel("Workspace files")
  await expect(panel.getByRole("button", { name: "Actions: confidential.docx" })).toHaveCount(0)
  await panel.getByText("confidential.docx", { exact: true }).click()

  const dialog = page.getByRole("dialog", { name: "Read-only preview: confidential.docx" })
  await expect(dialog.getByText("Confidential file. Preview only")).toBeVisible()
  await expect(dialog.getByText("Protected summary")).toBeVisible()
  const policyLink = dialog.getByRole("link", { name: "Policy" })
  await expect(policyLink).toHaveAttribute("href", "https://example.com/policy")
  const openPages = context.pages().length
  await policyLink.click()
  await expect.poll(() => context.pages().length).toBe(openPages)
  const fullscreenButton = dialog.getByRole("button", { name: "Open full screen" })
  await expect(fullscreenButton).toBeVisible()
  await fullscreenButton.click()
  await expect.poll(() => page.evaluate(() => document.fullscreenElement?.getAttribute("role"))).toBe("dialog")
  await dialog.getByRole("button", { name: "Exit full screen" }).click()
  await expect.poll(() => page.evaluate(() => document.fullscreenElement)).toBeNull()
  await expect(dialog.getByRole("link", { name: "Download" })).toHaveCount(0)
  await page.screenshot({ path: testInfo.outputPath("protected-preview.png"), fullPage: true })
})

test("Excel preview preserves spreadsheet layout", async ({ page }, testInfo) => {
  await mockWorkspace(page)
  await page.goto("/")
  if (testInfo.project.name === "mobile") await page.getByTitle("Files").click()

  await page.getByLabel("Workspace files").getByText("monthly-report.xlsx", { exact: true }).click()
  const dialog = page.getByRole("dialog", { name: "Read-only preview: monthly-report.xlsx" })
  await expect(dialog.getByText("Monthly settlement")).toBeVisible()
  await expect(dialog.getByText("1,696.44")).toBeVisible()
  await expect(dialog.getByRole("columnheader", { name: "A" })).toBeVisible()
  await expect(dialog.getByRole("button", { name: "vyuctovanie" })).toBeVisible()
  await expect(dialog.getByText("Detail row 500", { exact: true })).toHaveCount(0)
  await dialog.getByTestId("excel-scroll-region").evaluate((element) => {
    element.scrollTop = element.scrollHeight
    element.dispatchEvent(new Event("scroll"))
  })
  await expect(dialog.getByText("Detail row 500", { exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath("excel-preview.png"), fullPage: true })
})

test("PDF preview provides responsive page and zoom controls", async ({ page }, testInfo) => {
  await mockWorkspace(page)
  await page.goto("/")
  if (testInfo.project.name === "mobile") await page.getByTitle("Files").click()

  await page.getByLabel("Workspace files").getByText("board-report.pdf", { exact: true }).click()
  const dialog = page.getByRole("dialog", { name: "Read-only preview: board-report.pdf" })
  await expect(dialog.getByText("1 / 2", { exact: true })).toBeVisible()
  await dialog.getByRole("button", { name: "Zoom in" }).click()
  await expect(dialog.getByText("110%", { exact: true })).toBeVisible()
  await dialog.getByRole("button", { name: "Next" }).click()
  await expect(dialog.getByText("2 / 2", { exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath("pdf-preview.png"), fullPage: true })
})

test("text and image files open in responsive read-only previews", async ({ page }, testInfo) => {
  await mockWorkspace(page)
  await page.goto("/")
  if (testInfo.project.name === "mobile") await page.getByTitle("Files").click()

  const panel = page.getByLabel("Workspace files")
  await panel.getByText("calculation-notes.txt", { exact: true }).click()
  const textDialog = page.getByRole("dialog", { name: "Read-only preview: calculation-notes.txt" })
  await expect(textDialog.getByTestId("text-preview")).toContainText("In use = resources assigned to an active project")
  await expect(textDialog.getByTestId("text-preview")).toHaveCSS("white-space", "pre-wrap")
  await page.screenshot({ path: testInfo.outputPath("text-preview.png"), fullPage: true })
  await textDialog.getByRole("button", { name: "Close" }).click()

  await panel.getByText("usage-chart.png", { exact: true }).click()
  const imageDialog = page.getByRole("dialog", { name: "Read-only preview: usage-chart.png" })
  const image = imageDialog.getByRole("img", { name: "usage-chart.png" })
  await expect(image).toBeVisible()
  await expect.poll(() => image.evaluate((element: HTMLImageElement) => element.naturalWidth)).toBe(1)
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath("text-image-preview.png"), fullPage: true })
})

test("administrator manages a user workspace and access policy", async ({ page }, testInfo) => {
  await mockAdmin(page)
  await page.goto("/")

  await expect(page.getByRole("heading", { name: "Workspace administration" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Assistant" })).toBeVisible()
  await page.getByRole("button", { name: "Actions: board-report.pdf" }).click()
  await page.getByRole("button", { name: "Allow user access" }).click()
  await page.getByRole("button", { name: "Actions: board-report.pdf" }).click()
  await expect(page.getByRole("button", { name: "Set No user access" })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath("admin-workspace.png"), fullPage: true })
})

test("administrator reviews user conversations without mutation controls", async ({ page }, testInfo) => {
  await mockAdmin(page)
  await page.goto("/")

  await page.getByRole("button", { name: "Conversations" }).click()
  await expect(page.getByRole("heading", { name: "Conversation history" })).toBeVisible()
  await page.getByRole("button", { name: /July revenue review/ }).click()
  await expect(page.getByRole("article").filter({ hasText: "Compare July revenue with June." })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Result" })).toBeVisible()
  await expect(page.getByRole("article").filter({ hasText: "Revenue increased by 12%." })).toBeVisible()
  await expect(page.getByText("reports/july.xlsx", { exact: true })).toBeVisible()
  await expect(page.getByText("Read-only", { exact: true })).toBeVisible()
  const conversationHeader = page.getByRole("heading", { name: "July revenue review" }).locator("..")
  await expect(conversationHeader.getByText(/Metabase planning conversation/)).toBeVisible()
  await expect(page.getByPlaceholder("Message your agent...")).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Delete" })).toHaveCount(0)
  await page.screenshot({ path: testInfo.outputPath("admin-conversation-detail.png"), fullPage: true })

  if (testInfo.project.name === "mobile") {
    await page.getByRole("button", { name: "Back to conversations" }).click()
    await expect(page.getByRole("heading", { name: "Conversation history" })).toBeVisible()
  }
  await page.screenshot({ path: testInfo.outputPath("admin-conversations.png"), fullPage: true })
})

test("administrator exports a conversation as a JSON download", async ({ page }) => {
  await mockAdmin(page)
  await page.goto("/")

  await page.getByRole("button", { name: "Conversations" }).click()
  await page.getByRole("button", { name: /July revenue review/ }).click()
  const downloadPromise = page.waitForEvent("download")
  await page.getByRole("link", { name: "Export conversation" }).click()
  const download = await downloadPromise

  expect(download.suggestedFilename()).toBe("conversation-77777777-7777-4777-8777-777777777777.json")
})

test("authenticated workspace fits desktop and mobile viewports", async ({ page }, testInfo) => {
  const password = process.env.UI_TEST_PASSWORD
  test.skip(!password, "UI_TEST_PASSWORD is required for authenticated E2E")

  await page.goto("/")
  await page.getByLabel("Username").fill("assistant-validation")
  await page.getByLabel("Password").fill(password!)
  await page.getByRole("button", { name: "Sign in" }).click()

  await expect(page.getByText("Assistant", { exact: true }).first()).toBeVisible()
  await page.getByRole("button", { name: "New conversation" }).last().click()
  await expect(page.locator("header").getByText("New conversation", { exact: true })).toBeVisible()
  await expect(page.locator("body")).not.toHaveCSS("overflow-x", "scroll")
  await page.screenshot({ path: testInfo.outputPath("workspace.png"), fullPage: true })
})
