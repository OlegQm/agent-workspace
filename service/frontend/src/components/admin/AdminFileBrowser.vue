<script setup lang="ts">
import { ArrowLeft, FolderPlus, Upload } from "lucide-vue-next"
import { computed, ref, watch } from "vue"

import { api, type AdminManagedUser, type FileEntry } from "../../api"
import { useWorkspaceContext } from "../../composables/useWorkspace"
import { fileOperationError, uploadResultNotice } from "../../lib/fileUpload"
import DocumentPreviewDialog from "../files/DocumentPreviewDialog.vue"
import FileEntryRow from "../files/FileEntryRow.vue"
import RenameEntryDialog from "../files/RenameEntryDialog.vue"

const props = defineProps<{ managedUser: AdminManagedUser }>()
const { formatBytes, t } = useWorkspaceContext()
const path = ref("")
const files = ref<FileEntry[]>([])
const quota = ref({ used: 0, limit: 1 })
const error = ref("")
const notice = ref("")
const previewEntry = ref<FileEntry | null>(null)
const renamingEntry = ref<FileEntry | null>(null)
const loading = ref(false)
const parent = computed(() => path.value.split("/").slice(0, -1).join("/"))

async function loadFiles(nextPath = path.value) {
  loading.value = true
  error.value = ""
  try {
    const response = await api.adminFiles(props.managedUser.id, nextPath)
    path.value = nextPath
    files.value = response.entries
    quota.value = { used: response.used_bytes, limit: response.limit_bytes }
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause)
  } finally {
    loading.value = false
  }
}

async function uploadFiles(items: FileList | File[]) {
  error.value = ""
  const selected = Array.from(items)
  try {
    for (const file of selected) await api.adminUpload(props.managedUser.id, file, path.value)
    await loadFiles()
    notice.value = uploadResultNotice(selected, t.value)
  } catch (cause) {
    error.value = fileOperationError(cause, t.value)
  }
}

function uploadSelected(event: Event) {
  const input = event.target as HTMLInputElement
  if (input.files?.length) void uploadFiles(input.files)
  input.value = ""
}

async function createFolder() {
  const name = prompt(t.value("folderName"))?.trim()
  if (!name) return
  try {
    await api.adminMkdir(props.managedUser.id, [path.value, name].filter(Boolean).join("/"))
    await loadFiles()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause)
  }
}

function openEntry(entry: FileEntry) {
  if (entry.type === "directory") void loadFiles(entry.path)
  else if (entry.preview_kind) previewEntry.value = entry
  else window.location.href = api.adminDownloadUrl(props.managedUser.id, entry.path)
}

async function submitRename(name: string) {
  if (!renamingEntry.value) return
  try {
    await api.adminRename(props.managedUser.id, renamingEntry.value.path, name.trim())
    renamingEntry.value = null
    await loadFiles()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause)
  }
}

async function deleteEntry(entry: FileEntry) {
  if (!confirm(`${t.value("delete")}: ${entry.name}?`)) return
  try {
    await api.adminRemove(props.managedUser.id, entry.path)
    await loadFiles()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause)
  }
}

async function copyPath(entry: FileEntry) {
  try {
    await navigator.clipboard.writeText(entry.path)
    notice.value = `${t.value("pathCopied")}: ${entry.path}`
    window.setTimeout(() => { notice.value = "" }, 2400)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause)
  }
}

async function setProtection(entry: FileEntry, restricted: boolean) {
  try {
    await api.adminSetAccess(props.managedUser.id, entry.path, restricted)
    notice.value = restricted ? t.value("protectedHint") : t.value("userAccessAllowed")
    await loadFiles()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause)
  }
}

function dropFiles(event: DragEvent) {
  if (event.dataTransfer?.files.length) void uploadFiles(event.dataTransfer.files)
}

watch(() => props.managedUser.id, () => {
  path.value = ""
  previewEntry.value = null
  void loadFiles("")
}, { immediate: true })
</script>

<template>
  <section class="flex min-h-0 flex-1 flex-col bg-white" @dragover.prevent @drop.prevent="dropFiles">
    <div class="flex min-h-16 shrink-0 flex-wrap items-center gap-2 border-b border-line px-3 py-2 sm:px-5">
      <button v-if="path" class="icon-button" :title="t('back')" @click="loadFiles(parent)"><ArrowLeft :size="18" /></button>
      <div class="min-w-0 flex-1">
        <h2 class="truncate font-semibold">{{ path || managedUser.agent_name }}</h2>
        <p class="truncate text-xs text-zinc-500">{{ managedUser.username }} · {{ managedUser.agent_id }}</p>
      </div>
      <label class="button-secondary cursor-pointer">
        <Upload :size="16" />{{ t("upload") }}
        <input class="hidden" type="file" multiple @change="uploadSelected" />
      </label>
      <button class="icon-button border border-line" :title="t('newFolder')" @click="createFolder"><FolderPlus :size="18" /></button>
    </div>

    <p v-if="notice" class="border-b border-emerald-200 bg-emerald-50 px-4 py-2 text-xs text-emerald-800" role="status">{{ notice }}</p>
    <p v-if="error" class="border-b border-red-200 bg-red-50 px-4 py-2 text-xs text-red-800" role="alert">{{ error }}</p>

    <div class="min-h-0 flex-1 overflow-y-auto p-2 sm:p-4">
      <p v-if="loading" class="p-8 text-center text-sm text-zinc-500">{{ t("running") }}</p>
      <p v-else-if="!files.length" class="p-8 text-center text-sm text-zinc-500">{{ t("emptyFolder") }}</p>
      <FileEntryRow
        v-for="entry in files"
        v-else
        :key="entry.path"
        :entry="entry"
        administrator
        :download-href="entry.type === 'file' ? api.adminDownloadUrl(managedUser.id, entry.path) : undefined"
        @open="openEntry"
        @rename="renamingEntry = $event"
        @copy="copyPath"
        @delete="deleteEntry"
        @protect="setProtection"
      />
    </div>

    <footer class="shrink-0 border-t border-line p-4">
      <div class="mb-1 flex justify-between text-xs text-zinc-500">
        <span>Workspace</span><span>{{ formatBytes(quota.used) }} / {{ formatBytes(quota.limit) }}</span>
      </div>
      <div class="h-1.5 bg-zinc-100"><div class="h-full bg-accent" :style="{ width: `${Math.min(100, quota.used / quota.limit * 100)}%` }" /></div>
    </footer>

    <RenameEntryDialog v-if="renamingEntry" :entry="renamingEntry" @cancel="renamingEntry = null" @submit="submitRename" />
    <DocumentPreviewDialog v-if="previewEntry" :entry="previewEntry" :admin-user-id="managedUser.id" @close="previewEntry = null" />
  </section>
</template>
