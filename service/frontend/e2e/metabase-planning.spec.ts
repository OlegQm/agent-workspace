import { expect, test, type Page } from "@playwright/test"

const planningId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"

async function showPlanningEntry(page: Page) {
  if ((page.viewportSize()?.width ?? 0) < 1024) {
    await page.getByRole("button", { name: "Open navigation" }).click()
  }
  return page.getByRole("button", { name: "Need a chart in Metabase" })
}

function actions(state: "collecting" | "plan_ready" | "submitted") {
  const review = state === "plan_ready"
  return {
    accept_match: { visible: false, enabled: false, disabled_reason: null },
    reject_match: { visible: false, enabled: false, disabled_reason: null },
    open_metabase: { visible: false, enabled: false, disabled_reason: null },
    send_for_review: {
      visible: review,
      enabled: review,
      disabled_reason: null,
      mode: review ? "create" : null,
    },
    refresh_status: {
      visible: state === "submitted",
      enabled: state === "submitted",
      disabled_reason: null,
    },
  }
}

function snapshot(
  state: "collecting" | "plan_ready" | "submitted",
  operationStatus: "failed" | "outcome_unknown" | null = null,
) {
  const statement = { text: "Monthly paid revenue", provenance: "user_confirmed" }
  return {
    state,
    requirements_revision: 0,
    workflow_version: state === "collecting" ? 0 : state === "plan_ready" ? 1 : 2,
    discovery_status: "no_match",
    operation: operationStatus ? {
      id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
      type: "review_create",
      status: operationStatus,
      safe_error_code: operationStatus === "failed" ? "review_rejected" : "review_unavailable",
    } : null,
    candidate: null,
    plan: state === "collecting" ? null : {
      revision: 1,
      is_current: true,
      content: {
        business_question: statement,
        metrics: [statement], sources: [statement], period: [statement], grain: [statement],
        dimensions: [], filters: [], comparisons: [], exclusions: [],
        visualization: [statement], expected_interpretation: [], assumptions: [], explicit_answers: [],
      },
    },
    review: {
      issue_key: state === "submitted" ? "BI-7" : null,
      status: state === "submitted" ? "Open" : null,
      last_submitted_revision: state === "submitted" ? 1 : null,
      submitted_at: state === "submitted" ? "2026-09-04T10:00:00Z" : null,
      status_checked_at: state === "submitted" ? "2026-09-04T10:00:00Z" : null,
      status_refresh_error: null,
    },
    actions: {
      ...actions(state),
      send_for_review: state === "plan_ready" && operationStatus === "outcome_unknown"
        ? { visible: true, enabled: false, disabled_reason: "operation_in_progress", mode: "create" }
        : actions(state).send_for_review,
    },
  }
}

async function mockPlanning(
  page: Page,
  admin = false,
  failFirstReview: false | "failed" | "outcome_unknown" = false,
) {
  let created = false
  let submitted = false
  let reviewAttempts = 0
  let statusRefreshAttempts = 0
  await page.route("**/api/**", async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === "/api/auth/me") {
      await route.fulfill({ json: {
        id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        username: admin ? "admin" : "assistant",
        agent_id: admin ? null : "assistant",
        agent_name: admin ? "Administration" : "Assistant",
        locale: "en", tools: admin ? [] : ["metabase"], is_admin: admin,
      } })
      return
    }
    if (admin && path === "/api/admin/users") {
      await route.fulfill({ json: [] })
      return
    }
    if (path === "/api/conversations" && request.method() === "GET") {
      await route.fulfill({ json: created ? [{
        id: planningId, title: "Monthly paid revenue", kind: "metabase_planning",
        created_at: "2026-09-04T09:00:00Z", updated_at: "2026-09-04T09:00:00Z",
      }] : [] })
      return
    }
    if (path === "/api/files" && request.method() === "GET") {
      await route.fulfill({ json: { entries: [], used_bytes: 0, limit_bytes: 1_000_000 } })
      return
    }
    if (path === "/api/metabase-planning/conversations/runs") {
      created = true
      await route.fulfill({ status: 202, json: {
        conversation: {
          id: planningId, title: "Monthly paid revenue", kind: "metabase_planning",
          created_at: "2026-09-04T09:00:00Z", updated_at: "2026-09-04T09:00:00Z",
          planning: snapshot("collecting"),
        },
        run: {
          id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc", conversation_id: planningId,
          status: "queued", model_mode: "medium", error: null,
          created_at: "2026-09-04T09:00:00Z", updated_at: "2026-09-04T09:00:00Z",
        },
      } })
      return
    }
    if (path === `/api/conversations/${planningId}`) {
      await route.fulfill({ json: {
        id: planningId, title: "Monthly paid revenue", kind: "metabase_planning",
        created_at: "2026-09-04T09:00:00Z", updated_at: "2026-09-04T09:00:00Z",
        messages: [{
          id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd", role: "assistant",
          content: "I have enough detail to propose a plan.", attachments: [],
          created_at: "2026-09-04T09:00:00Z",
        }],
        runs: [], planning: snapshot(
          submitted ? "submitted" : "plan_ready",
          reviewAttempts > 0 && failFirstReview ? failFirstReview : null,
        ),
      } })
      return
    }
    if (path.endsWith("/events")) {
      await route.fulfill({
        status: 200, contentType: "text/event-stream",
        body: 'event: stream-end\ndata: {"status":"completed"}\n\n',
      })
      return
    }
    if (path.endsWith("/review") && request.method() === "POST") {
      reviewAttempts += 1
      if (failFirstReview && reviewAttempts === 1) {
        await route.fulfill({ status: 503, json: { detail: "Review service is temporarily unavailable" } })
        return
      }
      submitted = true
      await route.fulfill({ json: snapshot("submitted") })
      return
    }
    if (path.endsWith("/review/status") && request.method() === "POST") {
      statusRefreshAttempts += 1
      await route.fulfill({ json: snapshot("submitted") })
      return
    }
    await route.fulfill({ status: 404, json: { detail: `Unhandled ${request.method()} ${path}` } })
  })
  return () => statusRefreshAttempts
}

function exactMatchSnapshot(state: "collecting" | "match_proposed" | "resolved_existing" | "plan_ready") {
  const base = snapshot(state === "plan_ready" ? "plan_ready" : "collecting")
  const proposed = state === "match_proposed"
  const resolved = state === "resolved_existing"
  return {
    ...base,
    state,
    workflow_version: state === "collecting" ? 0 : state === "match_proposed" ? 1 : state === "resolved_existing" ? 2 : 4,
    discovery_status: proposed || resolved ? "exact_match" : state === "plan_ready" ? "no_match" : "in_progress",
    candidate: proposed ? {
      question_id: 42,
      title: "Monthly revenue overview",
      summary: "Shows the requested paid revenue by month.",
    } : null,
    plan: state === "plan_ready" ? base.plan : null,
    actions: {
      ...base.actions,
      accept_match: { visible: proposed, enabled: proposed, disabled_reason: null },
      reject_match: { visible: proposed, enabled: proposed, disabled_reason: null },
      open_metabase: { visible: resolved, enabled: resolved, disabled_reason: null },
      send_for_review: state === "plan_ready"
        ? base.actions.send_for_review
        : { visible: false, enabled: false, disabled_reason: null, mode: null },
    },
  }
}

async function mockExactMatchPlanning(page: Page, staleAccept = false) {
  let created = false
  let phase: "collecting" | "match_proposed" | "resolved_existing" | "correcting" | "plan_ready" = "collecting"
  let correctionReceived = false
  await page.route("**/api/**", async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === "/api/auth/me") {
      await route.fulfill({ json: {
        id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", username: "assistant",
        agent_id: "assistant", agent_name: "Assistant", locale: "en",
        tools: ["metabase"], is_admin: false,
      } })
      return
    }
    if (path === "/api/conversations" && request.method() === "GET") {
      await route.fulfill({ json: created ? [{
        id: planningId, title: "Monthly paid revenue", kind: "metabase_planning",
        created_at: "2026-09-04T09:00:00Z", updated_at: "2026-09-04T09:00:00Z",
      }] : [] })
      return
    }
    if (path === "/api/files" && request.method() === "GET") {
      await route.fulfill({ json: { entries: [], used_bytes: 0, limit_bytes: 1_000_000 } })
      return
    }
    if (path === "/api/metabase-planning/conversations/runs") {
      created = true
      await route.fulfill({ status: 202, json: {
        conversation: {
          id: planningId, title: "Monthly paid revenue", kind: "metabase_planning",
          created_at: "2026-09-04T09:00:00Z", updated_at: "2026-09-04T09:00:00Z",
          planning: exactMatchSnapshot("collecting"),
        },
        run: {
          id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc", conversation_id: planningId,
          status: "queued", model_mode: "medium", error: null,
          created_at: "2026-09-04T09:00:00Z", updated_at: "2026-09-04T09:00:00Z",
        },
      } })
      return
    }
    if (path === `/api/metabase-planning/conversations/${planningId}/match/accept`) {
      expect((await request.postDataJSON()).workflow_version).toBe(1)
      await new Promise((resolve) => setTimeout(resolve, 250))
      if (staleAccept) {
        phase = "collecting"
        await route.fulfill({ status: 409, json: { detail: "Workflow state changed; reload the conversation" } })
        return
      }
      phase = "resolved_existing"
      await route.fulfill({ json: exactMatchSnapshot("resolved_existing") })
      return
    }
    if (path === `/api/metabase-planning/conversations/${planningId}/runs`) {
      const body = await request.postDataJSON()
      expect(body.workflow_version).toBe(2)
      correctionReceived = true
      phase = "correcting"
      await route.fulfill({ status: 202, json: {
        planning: exactMatchSnapshot("collecting"),
        run: {
          id: "ffffffff-ffff-4fff-8fff-ffffffffffff", conversation_id: planningId,
          status: "queued", model_mode: "medium", error: null,
          created_at: "2026-09-04T09:05:00Z", updated_at: "2026-09-04T09:05:00Z",
        },
      } })
      return
    }
    if (path === `/api/conversations/${planningId}`) {
      const state = phase === "correcting" ? "plan_ready" : phase
      phase = state
      await route.fulfill({ json: {
        id: planningId, title: "Monthly paid revenue", kind: "metabase_planning",
        created_at: "2026-09-04T09:00:00Z", updated_at: "2026-09-04T09:05:00Z",
        messages: [], runs: [], planning: exactMatchSnapshot(state),
      } })
      return
    }
    if (path.endsWith("/events")) {
      if (phase === "collecting") phase = "match_proposed"
      await route.fulfill({
        status: 200, contentType: "text/event-stream",
        body: 'event: stream-end\ndata: {"status":"completed"}\n\n',
      })
      return
    }
    await route.fulfill({ status: 404, json: { detail: `Unhandled ${request.method()} ${path}` } })
  })
  return () => correctionReceived
}

test("regular user plans and submits one Metabase Question responsively", async ({ page }, testInfo) => {
  await mockPlanning(page)
  await page.goto("/")
  const planningEntry = await showPlanningEntry(page)
  await expect(planningEntry).toBeVisible()
  await expect(planningEntry.evaluate((node) => node.nextElementSibling?.textContent)).resolves.toContain("Tools & data")
  await planningEntry.click()
  await page.getByPlaceholder("Describe the chart you need...").fill("Monthly paid revenue")
  await page.getByRole("button", { name: "Send" }).click()

  await expect(page.getByRole("heading", { name: "Business question" })).toBeVisible()
  await expect(page.getByText("Monthly paid revenue", { exact: true }).last()).toBeVisible()
  const metricsBox = await page.getByRole("heading", { name: "Metrics and definitions" }).boundingBox()
  const sourcesBox = await page.getByRole("heading", { name: "Business sources" }).boundingBox()
  expect(metricsBox).not.toBeNull()
  expect(sourcesBox).not.toBeNull()
  expect(Math.abs((metricsBox?.x ?? 0) - (sourcesBox?.x ?? 0))).toBeLessThan(2)
  expect(sourcesBox?.y ?? 0).toBeGreaterThan((metricsBox?.y ?? 0) + (metricsBox?.height ?? 0))
  await page.getByRole("button", { name: "Send for review" }).click()
  const dialog = page.getByRole("dialog", { name: "Send plan for review?" })
  await expect(dialog).toBeVisible()
  await dialog.getByRole("button", { name: "Send for review" }).click()
  await expect(page.getByText(/BI-7.*Open/)).toBeVisible()
  await expect(page.getByRole("button", { name: "Refresh status" })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath("metabase-planning.png"), fullPage: true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test("administrator never sees or invokes the planning entry point", async ({ page }) => {
  await mockPlanning(page, true)
  await page.goto("/")
  await expect(page.getByRole("button", { name: "Need a chart in Metabase" })).toHaveCount(0)
})

test("planning entry returns an existing draft from the tools page", async ({ page }) => {
  await mockPlanning(page)
  await page.goto("/")

  await (await showPlanningEntry(page)).click()
  await expect(page.getByPlaceholder("Describe the chart you need...")).toBeVisible()

  if ((page.viewportSize()?.width ?? 0) < 1024) {
    await page.getByRole("button", { name: "Open navigation" }).click()
  }
  await page.getByRole("button", { name: "Tools & data" }).click()
  await expect(page.getByRole("heading", { name: "Tools & data", level: 1 })).toBeVisible()

  await (await showPlanningEntry(page)).click()
  await expect(page.getByPlaceholder("Describe the chart you need...")).toBeVisible()
  await expect(page.getByRole("heading", { name: "Tools & data", level: 1 })).toHaveCount(0)
})

test("failed review submission keeps confirmation open for an explicit retry", async ({ page }) => {
  await mockPlanning(page, false, "failed")
  await page.goto("/")
  await (await showPlanningEntry(page)).click()
  await page.getByPlaceholder("Describe the chart you need...").fill("Monthly paid revenue")
  await page.getByRole("button", { name: "Send" }).click()
  await page.getByRole("button", { name: "Send for review" }).click()
  const dialog = page.getByRole("dialog", { name: "Send plan for review?" })

  await dialog.getByRole("button", { name: "Send for review" }).click()
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole("alert")).toHaveText("Review service is temporarily unavailable")

  await dialog.getByRole("button", { name: "Send for review" }).click()
  await expect(dialog).toBeHidden()
  await expect(page.getByText(/BI-7.*Open/)).toBeVisible()
})

test("unknown review outcome reloads authoritative state and prevents a duplicate", async ({ page }) => {
  await mockPlanning(page, false, "outcome_unknown")
  await page.goto("/")
  await (await showPlanningEntry(page)).click()
  await page.getByPlaceholder("Describe the chart you need...").fill("Monthly paid revenue")
  await page.getByRole("button", { name: "Send" }).click()
  await page.getByRole("button", { name: "Send for review" }).click()
  const dialog = page.getByRole("dialog", { name: "Send plan for review?" })

  await dialog.getByRole("button", { name: "Send for review" }).click()
  await expect(dialog).toBeVisible()
  await dialog.getByRole("button", { name: "Cancel" }).click()
  await expect(page.getByRole("button", { name: "Send for review" })).toBeDisabled()
})

test("accepted exact match opens safely and a correction resumes planning", async ({ page }) => {
  const correctionReceived = await mockExactMatchPlanning(page)
  await page.goto("/")
  await (await showPlanningEntry(page)).click()
  await page.getByPlaceholder("Describe the chart you need...").fill("Monthly paid revenue")
  await page.getByRole("button", { name: "Send" }).click()

  await expect(page.getByText("Monthly revenue overview", { exact: true })).toBeVisible()
  const accept = page.getByRole("button", { name: "Use this chart" })
  const acceptance = accept.click()
  await expect(accept).toHaveAttribute("aria-busy", "true")
  await expect(accept).toBeDisabled()
  await acceptance
  const open = page.getByRole("link", { name: "Open in Metabase" })
  await expect(open).toHaveAttribute("target", "_blank")
  await expect(open).toHaveAttribute("href", `/api/metabase-planning/conversations/${planningId}/open`)

  await page.getByPlaceholder("Describe the chart you need...").fill("Break it down by city instead")
  await page.getByRole("button", { name: "Send" }).click()
  await expect(open).toHaveCount(0)
  await expect(page.getByRole("heading", { name: "Business question" })).toBeVisible()
  expect(correctionReceived()).toBe(true)
})

test("review status refreshes only on open and explicit user action", async ({ page }) => {
  const statusRefreshAttempts = await mockPlanning(page)
  await page.goto("/")
  await (await showPlanningEntry(page)).click()
  await page.getByPlaceholder("Describe the chart you need...").fill("Monthly paid revenue")
  await page.getByRole("button", { name: "Send" }).click()
  await page.getByRole("button", { name: "Send for review" }).click()
  await page.getByRole("dialog", { name: "Send plan for review?" })
    .getByRole("button", { name: "Send for review" }).click()
  await expect(page.getByText(/BI-7.*Open/)).toBeVisible()
  expect(statusRefreshAttempts()).toBe(0)

  if ((page.viewportSize()?.width ?? 0) < 1024) {
    await page.getByRole("button", { name: "Open navigation" }).click()
  }
  await page.getByRole("button", {
    name: "Monthly paid revenue Metabase planning conversation",
  }).click()
  await expect.poll(statusRefreshAttempts).toBe(1)
  await page.waitForTimeout(250)
  expect(statusRefreshAttempts()).toBe(1)

  await page.getByRole("button", { name: "Refresh status" }).click()
  await expect.poll(statusRefreshAttempts).toBe(2)
})

test("a stale action reloads server-authoritative planning state", async ({ page }) => {
  await mockExactMatchPlanning(page, true)
  await page.goto("/")
  await (await showPlanningEntry(page)).click()
  await page.getByPlaceholder("Describe the chart you need...").fill("Monthly paid revenue")
  await page.getByRole("button", { name: "Send" }).click()
  await expect(page.getByText("Monthly revenue overview", { exact: true })).toBeVisible()

  await page.getByRole("button", { name: "Use this chart" }).click()
  await expect(page.getByText("Monthly revenue overview", { exact: true })).toHaveCount(0)
  await expect(page.getByText("Workflow state changed; reload the conversation").first()).toBeVisible()
})
