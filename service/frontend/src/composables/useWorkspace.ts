import {
  computed,
  inject,
  nextTick,
  onBeforeUnmount,
  onMounted,
  provide,
  ref,
  type InjectionKey,
} from "vue"

import {
  AUTH_EXPIRED_EVENT,
  api,
  type Conversation,
  type FileEntry,
  type Message,
  type ModelMode,
  type PlanningSnapshot,
  type Run,
  type User,
} from "../api"
import { translator, type Locale } from "../i18n"
import { createClientId } from "../lib/clientId"
import { fileOperationError, uploadResultNotice } from "../lib/fileUpload"

export type TimelineEvent = {
  sequence: number
  type: string
  payload: Record<string, unknown>
}

export type WorkspacePage = "chat" | "tools"

const activeStatuses = ["queued", "running", "waiting_approval", "stopping"]
const deltaEvents = ["message.delta", "assistant.delta", "content.delta", "text.delta"]
const modelModes: ModelMode[] = ["small", "medium", "high"]
const modelModeStorageKey = "open-agent-workspace-model-mode-v2"
const locales: Locale[] = ["en", "sk"]

function storedModelMode(): ModelMode {
  const value = localStorage.getItem(modelModeStorageKey)
  return modelModes.includes(value as ModelMode) ? value as ModelMode : "medium"
}

export function useWorkspace() {
  const user = ref<User | null>(null)
  const loginForm = ref({ username: "", password: "" })
  const loginError = ref("")
  const storedLocale = localStorage.getItem("open-agent-workspace-locale")
  const locale = ref<Locale>(locales.includes(storedLocale as Locale) ? storedLocale as Locale : "en")
  const modelMode = ref<ModelMode>(storedModelMode())
  const t = computed(() => translator(locale.value))
  const conversations = ref<Conversation[]>([])
  const selectedConversation = ref<Conversation | null>(null)
  const isNewConversation = ref(false)
  const isNewPlanningConversation = ref(false)
  const planning = ref<PlanningSnapshot | null>(null)
  const planningAction = ref<string | null>(null)
  const reviewConfirmationOpen = ref(false)
  const messages = ref<Message[]>([])
  const activeRun = ref<Run | null>(null)
  const events = ref<TimelineEvent[]>([])
  const draft = ref("")
  const attachments = ref<string[]>([])
  const filePath = ref("")
  const files = ref<FileEntry[]>([])
  const quota = ref({ used: 0, limit: 1 })
  const activePage = ref<WorkspacePage>("chat")
  const fileNotice = ref("")
  const previewEntry = ref<FileEntry | null>(null)
  const showFiles = ref(false)
  const showSidebar = ref(false)
  const dragging = ref(false)
  const error = ref("")
  const messagesEl = ref<HTMLElement | null>(null)
  let eventSource: EventSource | null = null
  let lastActivityRefresh = 0
  let sessionRefreshPending = false
  let selectionVersion = 0
  let fileNoticeTimer: ReturnType<typeof setTimeout> | null = null

  const isRunning = computed(() => Boolean(
    activeRun.value && activeStatuses.includes(activeRun.value.status),
  ))
  const streamText = computed(() => events.value
    .filter((event) => deltaEvents.includes(event.type))
    .map((event) => String(
      event.payload.delta ?? event.payload.text ?? event.payload.content ?? "",
    ))
    .join(""))
  const visibleEvents = computed(() => events.value.filter((event) =>
    ![...deltaEvents, "run.started", "run.completed"].includes(event.type),
  ))

  function setError(cause: unknown) {
    error.value = cause instanceof Error ? cause.message : String(cause)
  }

  function switchLocale() {
    locale.value = locale.value === "en" ? "sk" : "en"
    localStorage.setItem("open-agent-workspace-locale", locale.value)
  }

  function setModelMode(value: ModelMode) {
    modelMode.value = value
    localStorage.setItem(modelModeStorageKey, value)
  }

  function syncModelMode() {
    const configured = user.value?.model_modes ?? []
    const stored = localStorage.getItem(modelModeStorageKey)
    const preferred = configured.find((mode) => mode.value === stored)
    modelMode.value = preferred?.value ?? user.value?.default_model_mode ?? "medium"
  }

  async function loadConversations() {
    conversations.value = await api.conversations()
  }

  async function loadFiles(path = filePath.value) {
    const response = await api.files(path)
    filePath.value = path
    files.value = response.entries
    quota.value = { used: response.used_bytes, limit: response.limit_bytes }
  }

  async function scrollBottom() {
    await nextTick()
    messagesEl.value?.scrollTo({
      top: messagesEl.value.scrollHeight,
      behavior: "smooth",
    })
  }

  function closeRunStream() {
    eventSource?.close()
    eventSource = null
  }

  async function selectConversation(conversation: Conversation, refreshReview = true) {
    const version = ++selectionVersion
    closeRunStream()
    isNewConversation.value = false
    isNewPlanningConversation.value = false
    selectedConversation.value = conversation
    messages.value = []
    events.value = []
    activeRun.value = null
    planning.value = null
    showSidebar.value = false
    error.value = ""
    activePage.value = "chat"
    try {
      const detail = await api.conversation(conversation.id)
      if (version !== selectionVersion || selectedConversation.value?.id !== conversation.id) return
      selectedConversation.value = detail
      conversations.value = conversations.value.map((item) =>
        item.id === detail.id ? detail : item,
      )
      messages.value = detail.messages
      planning.value = detail.planning ?? null
      activeRun.value = detail.runs.find((run) => activeStatuses.includes(run.status)) ?? null
      const latestRun = detail.runs[0]
      if (!activeRun.value && latestRun?.status === "failed" && latestRun.error) {
        error.value = latestRun.error
      }
      if (activeRun.value) connectRun(activeRun.value)
      if (refreshReview && planning.value?.review.issue_key) {
        await refreshPlanningStatus()
      }
      await scrollBottom()
    } catch (cause) {
      if (version === selectionVersion) setError(cause)
    }
  }

  function newConversation() {
    if (isNewConversation.value) {
      activePage.value = "chat"
      showSidebar.value = false
      return
    }
    if (isRunning.value) return
    selectionVersion += 1
    error.value = ""
    activePage.value = "chat"
    closeRunStream()
    selectedConversation.value = null
    isNewConversation.value = true
    isNewPlanningConversation.value = false
    planning.value = null
    messages.value = []
    events.value = []
    activeRun.value = null
    showSidebar.value = false
  }

  function newPlanningConversation() {
    if (isNewPlanningConversation.value) {
      activePage.value = "chat"
      showSidebar.value = false
      return
    }
    if (isRunning.value) return
    selectionVersion += 1
    error.value = ""
    activePage.value = "chat"
    closeRunStream()
    selectedConversation.value = null
    isNewConversation.value = false
    isNewPlanningConversation.value = true
    planning.value = null
    messages.value = []
    events.value = []
    activeRun.value = null
    showSidebar.value = false
  }

  async function removeConversation(conversation: Conversation) {
    if (!confirm(`${t.value("delete")}: ${conversation.title}?`)) return
    error.value = ""
    try {
      await api.deleteConversation(conversation.id)
      conversations.value = conversations.value.filter((item) => item.id !== conversation.id)
      if (selectedConversation.value?.id === conversation.id) {
        selectionVersion += 1
        closeRunStream()
        selectedConversation.value = null
        messages.value = []
        events.value = []
        activeRun.value = null
        isNewConversation.value = false
        isNewPlanningConversation.value = false
        planning.value = null
      }
    } catch (cause) {
      setError(cause)
    }
  }

  async function sendMessage() {
    if (
      (!selectedConversation.value && !isNewConversation.value && !isNewPlanningConversation.value)
      || !draft.value.trim()
      || isRunning.value
    ) return
    error.value = ""
    const content = draft.value.trim()
    const attached = [...attachments.value]
    const optimisticMessage: Message = {
      id: createClientId(),
      role: "user",
      content,
      attachments: attached,
      created_at: new Date().toISOString(),
    }
    try {
      messages.value.push(optimisticMessage)
      draft.value = ""
      attachments.value = []
      events.value = []
      if (isNewPlanningConversation.value) {
        const result = await api.startPlanningConversation(content, attached, modelMode.value)
        selectedConversation.value = result.conversation
        planning.value = result.conversation.planning
        conversations.value = [result.conversation, ...conversations.value]
        activeRun.value = result.run
        isNewPlanningConversation.value = false
      } else if (isNewConversation.value) {
        const result = await api.startConversation(content, attached, modelMode.value)
        selectedConversation.value = result.conversation
        conversations.value = [result.conversation, ...conversations.value]
        activeRun.value = result.run
        isNewConversation.value = false
      } else if (selectedConversation.value?.kind === "metabase_planning" && planning.value) {
        const result = await api.continuePlanningConversation(
          selectedConversation.value.id,
          content,
          attached,
          modelMode.value,
          planning.value.workflow_version,
        )
        activeRun.value = result.run
        planning.value = result.planning
      } else {
        activeRun.value = await api.startRun(
          selectedConversation.value!.id,
          content,
          attached,
          modelMode.value,
        )
      }
      connectRun(activeRun.value)
      await loadConversations()
      await scrollBottom()
    } catch (cause) {
      if (!draft.value) draft.value = content
      attachments.value = [...new Set([...attachments.value, ...attached])]
      messages.value = messages.value.filter((message) => message.id !== optimisticMessage.id)
      setError(cause)
    }
  }

  function connectRun(run: Run) {
    closeRunStream()
    const source = new EventSource(`/api/runs/${run.id}/events`)
    eventSource = source
    source.addEventListener("run-event", async (raw) => {
      if (eventSource !== source) return
      let event: TimelineEvent
      try {
        event = JSON.parse((raw as MessageEvent).data) as TimelineEvent
      } catch {
        setError("The agent returned an invalid stream event.")
        return
      }
      if (events.value.some((item) => item.sequence === event.sequence)) return
      events.value.push(event)
      if (event.type.includes("approval")) {
        activeRun.value = { ...run, status: "waiting_approval" }
      }
      await scrollBottom()
    })
    source.addEventListener("stream-end", async () => {
      if (eventSource !== source) return
      source.close()
      eventSource = null
      activeRun.value = null
      if (selectedConversation.value) await selectConversation(selectedConversation.value, false)
      try {
        await loadFiles()
      } catch (cause) {
        setError(cause)
      }
    })
    source.onerror = () => {
      if (eventSource !== source) return
      // EventSource reconnects automatically and sends Last-Event-ID. Only probe auth here.
      void api.me().catch(() => undefined)
    }
  }

  async function stopRun() {
    if (!activeRun.value) return
    try {
      await api.stopRun(activeRun.value.id)
    } catch (cause) {
      setError(cause)
    }
  }

  async function approve(decision: "once" | "deny") {
    if (!activeRun.value) return
    try {
      await api.approveRun(activeRun.value.id, decision)
    } catch (cause) {
      setError(cause)
    }
  }

  async function uploadFiles(items: FileList | File[]) {
    error.value = ""
    const selected = Array.from(items)
    try {
      for (const file of selected) {
        const result = await api.upload(file, filePath.value)
        if (!attachments.value.includes(result.path)) attachments.value.push(result.path)
      }
      await loadFiles()
      showFileNotice(uploadResultNotice(selected, t.value))
    } catch (cause) {
      error.value = fileOperationError(cause, t.value)
    }
  }

  async function createFolder() {
    const name = prompt(t.value("folderName"))?.trim()
    if (!name) return
    try {
      await api.mkdir([filePath.value, name].filter(Boolean).join("/"))
      await loadFiles()
    } catch (cause) {
      setError(cause)
    }
  }

  function showFileNotice(message: string) {
    fileNotice.value = message
    if (fileNoticeTimer) clearTimeout(fileNoticeTimer)
    fileNoticeTimer = setTimeout(() => { fileNotice.value = "" }, 2400)
  }

  async function renameEntry(entry: FileEntry, newName: string): Promise<boolean> {
    const name = newName.trim()
    if (!name || name === entry.name) return false
    try {
      const result = await api.rename(entry.path, name)
      const oldPath = entry.path
      attachments.value = attachments.value.map((path) => {
        if (path === oldPath) return result.path
        return path.startsWith(`${oldPath}/`)
          ? `${result.path}${path.slice(oldPath.length)}`
          : path
      })
      await loadFiles()
      return true
    } catch (cause) {
      setError(cause)
      return false
    }
  }

  async function copyEntryPath(entry: FileEntry) {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(entry.path)
      } else {
        const field = document.createElement("textarea")
        field.value = entry.path
        field.style.position = "fixed"
        field.style.opacity = "0"
        document.body.appendChild(field)
        field.select()
        document.execCommand("copy")
        field.remove()
      }
      showFileNotice(`${t.value("pathCopied")}: ${entry.path}`)
    } catch (cause) {
      setError(cause)
    }
  }

  function openToolsPage() {
    selectionVersion += 1
    activePage.value = "tools"
    showSidebar.value = false
  }

  async function runPlanningAction(
    name: string,
    operation: () => Promise<PlanningSnapshot>,
  ): Promise<boolean> {
    if (!selectedConversation.value || planningAction.value) return false
    planningAction.value = name
    error.value = ""
    try {
      planning.value = await operation()
      return true
    } catch (cause) {
      setError(cause)
      const actionError = error.value
      const conversationId = selectedConversation.value.id
      try {
        const detail = await api.conversation(conversationId)
        if (selectedConversation.value?.id === conversationId) {
          selectedConversation.value = detail
          conversations.value = conversations.value.map((item) =>
            item.id === detail.id ? detail : item,
          )
          messages.value = detail.messages
          planning.value = detail.planning ?? null
        }
      } catch {
        // Keep the actionable operation failure when reconciliation is unavailable.
      }
      error.value = actionError
      return false
    } finally {
      planningAction.value = null
    }
  }

  async function acceptPlanningMatch() {
    if (!selectedConversation.value || !planning.value) return
    const { id } = selectedConversation.value
    const version = planning.value.workflow_version
    await runPlanningAction("accept_match", () => api.acceptPlanningMatch(id, version))
  }

  async function rejectPlanningMatch() {
    if (!selectedConversation.value || !planning.value) return
    const { id } = selectedConversation.value
    const version = planning.value.workflow_version
    await runPlanningAction("reject_match", () => api.rejectPlanningMatch(id, version))
  }

  async function confirmPlanningReview() {
    if (!selectedConversation.value || !planning.value?.plan) return
    const { id } = selectedConversation.value
    const version = planning.value.workflow_version
    const revision = planning.value.plan.revision
    const succeeded = await runPlanningAction("send_for_review", () => api.sendPlanningReview(
      id,
      version,
      revision,
      createClientId(),
    ))
    if (succeeded) {
      reviewConfirmationOpen.value = false
      return
    }

  }

  async function refreshPlanningStatus() {
    if (!selectedConversation.value || !planning.value?.review.issue_key) return
    const id = selectedConversation.value.id
    await runPlanningAction("refresh_status", () => api.refreshPlanningStatus(id))
  }

  async function deleteEntry(entry: FileEntry) {
    if (!confirm(`${t.value("delete")}: ${entry.name}?`)) return
    try {
      await api.remove(entry.path)
      attachments.value = attachments.value.filter((path) => path !== entry.path)
      await loadFiles()
    } catch (cause) {
      setError(cause)
    }
  }

  async function openEntry(entry: FileEntry) {
    if (entry.type === "directory") {
      try {
        await loadFiles(entry.path)
      } catch (cause) {
        setError(cause)
      }
    } else if (entry.preview_kind) {
      previewEntry.value = entry
    } else if (entry.no_user_access) {
      error.value = t.value("previewUnavailable")
    } else if (!attachments.value.includes(entry.path)) {
      attachments.value.push(entry.path)
    }
  }

  async function parentPath() {
    try {
      await loadFiles(filePath.value.split("/").slice(0, -1).join("/"))
    } catch (cause) {
      setError(cause)
    }
  }

  function removeAttachment(path: string) {
    attachments.value = attachments.value.filter((item) => item !== path)
  }

  function displayPayload(event: TimelineEvent) {
    const payload = event.payload
    return String(
      payload.command ?? payload.tool ?? payload.tool_name ?? payload.name
      ?? payload.message ?? payload.error ?? event.type,
    )
  }

  function formatBytes(value: number) {
    return value < 1_000_000
      ? `${Math.round(value / 1000)} kB`
      : `${(value / 1_000_000).toFixed(1)} MB`
  }

  async function login() {
    loginError.value = ""
    try {
      user.value = (await api.login(loginForm.value.username, loginForm.value.password)).user
      syncModelMode()
      lastActivityRefresh = Date.now()
      loginForm.value.password = ""
    } catch {
      loginError.value = t.value("invalidLogin")
      return
    }
    if (user.value.is_admin) return
    try {
      await Promise.all([loadConversations(), loadFiles()])
    } catch (cause) {
      setError(cause)
    }
  }

  async function logout() {
    if (!confirm(t.value("confirmSignOut"))) return
    try {
      await api.logout()
    } finally {
      resetAuthenticatedState()
    }
  }

  function resetAuthenticatedState() {
    selectionVersion += 1
    closeRunStream()
    user.value = null
    selectedConversation.value = null
    isNewConversation.value = false
    isNewPlanningConversation.value = false
    conversations.value = []
    messages.value = []
    activeRun.value = null
    events.value = []
    planning.value = null
    planningAction.value = null
    reviewConfirmationOpen.value = false
    attachments.value = []
    activePage.value = "chat"
    previewEntry.value = null
  }

  function handleAuthenticationExpired() {
    const wasAuthenticated = Boolean(user.value)
    resetAuthenticatedState()
    if (wasAuthenticated) loginError.value = t.value("sessionExpired")
  }

  function refreshSessionFromActivity() {
    if (
      !user.value
      || sessionRefreshPending
      || Date.now() - lastActivityRefresh < 300_000
    ) return
    sessionRefreshPending = true
    lastActivityRefresh = Date.now()
    void api.refreshSession()
      .catch(() => undefined)
      .finally(() => { sessionRefreshPending = false })
  }

  function handleVisibilityChange() {
    if (document.visibilityState === "visible") refreshSessionFromActivity()
  }

  function handlePaste(event: ClipboardEvent) {
    const image = Array.from(event.clipboardData?.files ?? [])
      .find((file) => file.type.startsWith("image/"))
    if (image && user.value && !user.value.is_admin) void uploadFiles([image])
  }

  onMounted(async () => {
    window.addEventListener("paste", handlePaste)
    window.addEventListener(AUTH_EXPIRED_EVENT, handleAuthenticationExpired)
    window.addEventListener("pointerdown", refreshSessionFromActivity)
    window.addEventListener("keydown", refreshSessionFromActivity)
    document.addEventListener("visibilitychange", handleVisibilityChange)
    try {
      user.value = await api.me()
      syncModelMode()
      lastActivityRefresh = Date.now()
    } catch {
      user.value = null
      return
    }
    if (user.value.is_admin) return
    try {
      await Promise.all([loadConversations(), loadFiles()])
    } catch (cause) {
      setError(cause)
    }
  })

  onBeforeUnmount(() => {
    window.removeEventListener("paste", handlePaste)
    window.removeEventListener(AUTH_EXPIRED_EVENT, handleAuthenticationExpired)
    window.removeEventListener("pointerdown", refreshSessionFromActivity)
    window.removeEventListener("keydown", refreshSessionFromActivity)
    document.removeEventListener("visibilitychange", handleVisibilityChange)
    closeRunStream()
    if (fileNoticeTimer) clearTimeout(fileNoticeTimer)
  })

  return {
    activePage,
    activeRun,
    approve,
    attachments,
    conversations,
    createFolder,
    copyEntryPath,
    deleteEntry,
    displayPayload,
    draft,
    dragging,
    error,
    filePath,
    fileNotice,
    files,
    formatBytes,
    isRunning,
    isNewConversation,
    isNewPlanningConversation,
    loadFiles,
    locale,
    login,
    loginError,
    loginForm,
    logout,
    messages,
    messagesEl,
    modelMode,
    newConversation,
    newPlanningConversation,
    openEntry,
    openToolsPage,
    parentPath,
    previewEntry,
    planning,
    planningAction,
    quota,
    removeAttachment,
    removeConversation,
    renameEntry,
    selectedConversation,
    acceptPlanningMatch,
    rejectPlanningMatch,
    confirmPlanningReview,
    refreshPlanningStatus,
    reviewConfirmationOpen,
    setModelMode,
    selectConversation,
    sendMessage,
    showFiles,
    showSidebar,
    stopRun,
    streamText,
    switchLocale,
    t,
    uploadFiles,
    user,
    visibleEvents,
  }
}

export type WorkspaceController = ReturnType<typeof useWorkspace>

const workspaceKey: InjectionKey<WorkspaceController> = Symbol("workspace")

export function provideWorkspace(workspace: WorkspaceController) {
  provide(workspaceKey, workspace)
}

export function useWorkspaceContext(): WorkspaceController {
  const workspace = inject(workspaceKey)
  if (!workspace) throw new Error("Workspace context is not available")
  return workspace
}
