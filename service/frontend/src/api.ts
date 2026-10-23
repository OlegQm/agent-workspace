export type User = {
  id: string
  username: string
  agent_id: string | null
  agent_name: string
  locale: "en" | "sk"
  tools: string[]
  is_admin: boolean
  model_modes?: ModelModeDescriptor[]
  default_model_mode?: ModelMode
}

export type AdminManagedUser = {
  id: string
  username: string
  agent_id: string
  agent_name: string
  locale: "en" | "sk"
  is_active: boolean
}

export type ModelMode = "small" | "medium" | "high"

export type ModelModeDescriptor = {
  value: ModelMode
  label: string
  description: string
}

export type Conversation = {
  id: string
  title: string
  kind: "standard" | "metabase_planning"
  created_at: string
  updated_at: string
}

export type PlanningAction = {
  visible: boolean
  enabled: boolean
  disabled_reason: string | null
  mode?: "create" | "update" | null
}

export type PlanningStatement = {
  text: string
  provenance: "user_confirmed" | "authorized_discovery"
}

export type StructuredPlanningPlan = {
  business_question: PlanningStatement
  metrics: PlanningStatement[]
  sources: PlanningStatement[]
  period: PlanningStatement[]
  grain: PlanningStatement[]
  dimensions: PlanningStatement[]
  filters: PlanningStatement[]
  comparisons: PlanningStatement[]
  exclusions: PlanningStatement[]
  visualization: PlanningStatement[]
  expected_interpretation: PlanningStatement[]
  assumptions: PlanningStatement[]
  explicit_answers: PlanningStatement[]
}

export type PlanningSnapshot = {
  state: "collecting" | "match_proposed" | "resolved_existing" | "plan_ready" | "submitted"
  requirements_revision: number
  workflow_version: number
  discovery_status: string
  operation: { id: string; type: string; status: string; safe_error_code: string | null } | null
  candidate: { question_id: number; title: string; summary: string } | null
  plan: { revision: number; is_current: boolean; content: StructuredPlanningPlan } | null
  review: {
    issue_key: string | null
    status: string | null
    last_submitted_revision: number | null
    submitted_at: string | null
    status_checked_at: string | null
    status_refresh_error?: string | null
  }
  actions: {
    accept_match: PlanningAction
    reject_match: PlanningAction
    open_metabase: PlanningAction
    send_for_review: PlanningAction
    refresh_status: PlanningAction
  }
}

export type Message = {
  id: string
  role: "user" | "assistant"
  content: string
  attachments: string[]
  created_at: string
}

export type Run = {
  id: string
  conversation_id: string
  status: string
  model_mode: ModelMode
  error: string | null
  created_at: string
  updated_at: string
}

export type ConversationDetail = Conversation & {
  messages: Message[]
  runs: Run[]
  planning?: PlanningSnapshot | null
}

export type FileEntry = {
  name: string
  path: string
  type: "file" | "directory"
  size: number | null
  modified_at: number
  preview_kind: "pdf" | "docx" | "xlsx" | "txt" | "image" | null
  no_user_access: boolean
  no_user_access_explicit: boolean
  no_user_access_inherited: boolean
  can_download: boolean
  can_modify: boolean
  can_copy: boolean
}

export type ExcelBorder = {
  style: string
  color: string
}

export type ExcelCellStyle = {
  bold?: boolean
  italic?: boolean
  underline?: boolean
  font_size?: number | null
  font_color?: string | null
  fill_color?: string | null
  horizontal?: string | null
  vertical?: string | null
  wrap_text?: boolean
  indent?: number
  border_left?: ExcelBorder | null
  border_right?: ExcelBorder | null
  border_top?: ExcelBorder | null
  border_bottom?: ExcelBorder | null
}

export type ExcelCell = {
  value: unknown
  display: string
  style_id: number
  row_span: number
  column_span: number
}

export type ExcelPreview = {
  kind: "xlsx"
  sheets: string[]
  sheet: string | null
  rows: (ExcelCell | null)[][]
  column_widths: number[]
  row_heights: number[]
  styles: ExcelCellStyle[]
  show_gridlines: boolean
  truncated: boolean
  styled: boolean
}

export type DocxRun = {
  text: string
  href: string | null
  bold: boolean
  italic: boolean
  underline: boolean
  strike: boolean
  superscript: boolean
  subscript: boolean
  font_size: number | null
  font_color: string | null
  font_name: string | null
  highlight_color: string | null
}

export type DocxParagraphBlock = {
  type: "paragraph"
  text: string
  style: string | null
  alignment: "left" | "center" | "right" | "justify" | null
  list_kind: "bullet" | "number" | null
  list_level: number | null
  space_before: number | null
  space_after: number | null
  left_indent: number | null
  right_indent: number | null
  first_line_indent: number | null
  line_spacing_pixels: number | null
  line_spacing_multiple: number | null
  runs: DocxRun[]
}

export type DocxTableCell = {
  paragraphs: DocxParagraphBlock[]
  fill_color: string | null
  vertical_alignment: "top" | "center" | "bottom" | null
}

export type DocxPreviewBlock = DocxParagraphBlock | {
  type: "table"
  rows: DocxTableCell[][]
  column_widths: (number | null)[]
  header_row: boolean
  style: string | null
}

export type DocxPreview = {
  kind: "docx"
  blocks: DocxPreviewBlock[]
  truncated: boolean
  page: {
    width: number | null
    height: number | null
    margin_top: number | null
    margin_right: number | null
    margin_bottom: number | null
    margin_left: number | null
  }
}

export type PdfPreview = {
  kind: "pdf"
  page_count: number
  pages: { width: number; height: number }[]
}

export type TextPreview = {
  kind: "txt"
  content: string
  truncated: boolean
}

export type ImagePreview = {
  kind: "image"
  media_type: "image/png" | "image/jpeg" | "image/gif" | "image/webp"
  width: number
  height: number
}

export type DocumentPreview = ExcelPreview | DocxPreview | PdfPreview | TextPreview | ImagePreview

export const AUTH_EXPIRED_EVENT = "open-agent-workspace-auth-expired"

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = "ApiError"
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...init,
    headers: init?.body instanceof FormData
      ? init.headers
      : { "Content-Type": "application/json", ...init?.headers },
  })
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      detail = body.detail ?? detail
    } catch { /* response is not JSON */ }
    if (response.status === 401 && path !== "/api/auth/login") {
      window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT))
    }
    throw new ApiError(detail, response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  me: () => request<User>("/api/auth/me"),
  refreshSession: () => request<{ status: string }>("/api/auth/refresh", { method: "POST" }),
  login: (username: string, password: string) => request<{ user: User }>("/api/auth/login", {
    method: "POST", body: JSON.stringify({ username, password }),
  }),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  conversations: () => request<Conversation[]>("/api/conversations"),
  conversation: (id: string) => request<ConversationDetail>(`/api/conversations/${id}`),
  deleteConversation: (id: string) => request<void>(`/api/conversations/${id}`, { method: "DELETE" }),
  startRun: (id: string, content: string, attachments: string[], modelMode: ModelMode) => request<Run>(`/api/conversations/${id}/runs`, {
    method: "POST", body: JSON.stringify({ content, attachments, model_mode: modelMode }),
  }),
  startConversation: (content: string, attachments: string[], modelMode: ModelMode) => request<{ conversation: Conversation; run: Run }>("/api/conversations/runs", {
    method: "POST", body: JSON.stringify({ content, attachments, model_mode: modelMode }),
  }),
  startPlanningConversation: (content: string, attachments: string[], modelMode: ModelMode) => request<{ conversation: Conversation & { planning: PlanningSnapshot }; run: Run }>("/api/metabase-planning/conversations/runs", {
    method: "POST", body: JSON.stringify({ content, attachments, model_mode: modelMode }),
  }),
  continuePlanningConversation: (id: string, content: string, attachments: string[], modelMode: ModelMode, workflowVersion: number) => request<{ run: Run; planning: PlanningSnapshot }>(`/api/metabase-planning/conversations/${id}/runs`, {
    method: "POST", body: JSON.stringify({ content, attachments, model_mode: modelMode, workflow_version: workflowVersion }),
  }),
  acceptPlanningMatch: (id: string, workflowVersion: number) => request<PlanningSnapshot>(`/api/metabase-planning/conversations/${id}/match/accept`, {
    method: "POST", body: JSON.stringify({ workflow_version: workflowVersion }),
  }),
  rejectPlanningMatch: (id: string, workflowVersion: number) => request<PlanningSnapshot>(`/api/metabase-planning/conversations/${id}/match/reject`, {
    method: "POST", body: JSON.stringify({ workflow_version: workflowVersion }),
  }),
  sendPlanningReview: (id: string, workflowVersion: number, planRevision: number, idempotencyKey: string) => request<PlanningSnapshot>(`/api/metabase-planning/conversations/${id}/review`, {
    method: "POST", body: JSON.stringify({ workflow_version: workflowVersion, plan_revision: planRevision, idempotency_key: idempotencyKey }),
  }),
  refreshPlanningStatus: (id: string) => request<PlanningSnapshot>(`/api/metabase-planning/conversations/${id}/review/status`, { method: "POST" }),
  planningMetabaseUrl: (id: string) => `/api/metabase-planning/conversations/${id}/open`,
  planningReviewUrl: (id: string) => `/api/metabase-planning/conversations/${id}/review/open`,
  stopRun: (id: string) => request<{ status: string }>(`/api/runs/${id}/stop`, { method: "POST" }),
  approveRun: (id: string, decision: string) => request<{ status: string }>(`/api/runs/${id}/approval`, {
    method: "POST", body: JSON.stringify({ decision }),
  }),
  files: (path = "") => request<{ entries: FileEntry[]; used_bytes: number; limit_bytes: number }>(`/api/files?path=${encodeURIComponent(path)}`),
  upload: async (file: File, path = "") => {
    const body = new FormData()
    body.append("path", path)
    body.append("upload", file)
    return request<{ path: string; size: number }>("/api/files/upload", { method: "POST", body })
  },
  mkdir: (path: string) => request<{ path: string }>("/api/files/folder", { method: "POST", body: JSON.stringify({ path }) }),
  rename: (path: string, newName: string) => request<{ path: string }>("/api/files", {
    method: "PATCH", body: JSON.stringify({ path, new_name: newName }),
  }),
  remove: (path: string) => request<void>(`/api/files?path=${encodeURIComponent(path)}`, { method: "DELETE" }),
  preview: (path: string, sheet?: string) => request<DocumentPreview>(`/api/files/preview?path=${encodeURIComponent(path)}${sheet ? `&sheet=${encodeURIComponent(sheet)}` : ""}`),
  pdfPageUrl: (path: string, page: number) => `/api/files/preview/pdf-page?path=${encodeURIComponent(path)}&page=${page}`,
  imagePreviewUrl: (path: string) => `/api/files/preview/image?path=${encodeURIComponent(path)}`,
  adminUsers: () => request<AdminManagedUser[]>("/api/admin/users"),
  adminConversations: (userId: string) => request<Conversation[]>(`/api/admin/users/${userId}/conversations`),
  adminConversation: (userId: string, conversationId: string) => request<ConversationDetail>(`/api/admin/users/${userId}/conversations/${conversationId}`),
  adminConversationExportUrl: (userId: string, conversationId: string) => `/api/admin/users/${userId}/conversations/${conversationId}/export`,
  adminFiles: (userId: string, path = "") => request<{ entries: FileEntry[]; used_bytes: number; limit_bytes: number }>(`/api/admin/users/${userId}/files?path=${encodeURIComponent(path)}`),
  adminUpload: async (userId: string, file: File, path = "") => {
    const body = new FormData()
    body.append("path", path)
    body.append("upload", file)
    return request<{ path: string; size: number }>(`/api/admin/users/${userId}/files/upload`, { method: "POST", body })
  },
  adminMkdir: (userId: string, path: string) => request<{ path: string }>(`/api/admin/users/${userId}/files/folder`, { method: "POST", body: JSON.stringify({ path }) }),
  adminRename: (userId: string, path: string, newName: string) => request<{ path: string }>(`/api/admin/users/${userId}/files`, {
    method: "PATCH", body: JSON.stringify({ path, new_name: newName }),
  }),
  adminRemove: (userId: string, path: string) => request<void>(`/api/admin/users/${userId}/files?path=${encodeURIComponent(path)}`, { method: "DELETE" }),
  adminSetAccess: (userId: string, path: string, noUserAccess: boolean) => request<{ path: string; no_user_access: boolean }>(`/api/admin/users/${userId}/files/access`, {
    method: "PUT", body: JSON.stringify({ path, no_user_access: noUserAccess }),
  }),
  adminPreview: (userId: string, path: string, sheet?: string) => request<DocumentPreview>(`/api/admin/users/${userId}/files/preview?path=${encodeURIComponent(path)}${sheet ? `&sheet=${encodeURIComponent(sheet)}` : ""}`),
  adminPdfPageUrl: (userId: string, path: string, page: number) => `/api/admin/users/${userId}/files/preview/pdf-page?path=${encodeURIComponent(path)}&page=${page}`,
  adminImagePreviewUrl: (userId: string, path: string) => `/api/admin/users/${userId}/files/preview/image?path=${encodeURIComponent(path)}`,
  adminDownloadUrl: (userId: string, path: string) => `/api/admin/users/${userId}/files/download?path=${encodeURIComponent(path)}`,
}
