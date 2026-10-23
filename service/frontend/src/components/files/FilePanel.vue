<script setup lang="ts">
import {
  ArrowLeft,
  FolderPlus,
  Upload,
  X,
} from "lucide-vue-next"
import { ref } from "vue"

import type { FileEntry } from "../../api"
import { useWorkspaceContext } from "../../composables/useWorkspace"
import FileEntryRow from "./FileEntryRow.vue"
import DocumentPreviewDialog from "./DocumentPreviewDialog.vue"
import RenameEntryDialog from "./RenameEntryDialog.vue"

const {
  createFolder,
  copyEntryPath,
  deleteEntry,
  error,
  filePath,
  fileNotice,
  files,
  formatBytes,
  openEntry,
  parentPath,
  previewEntry,
  quota,
  renameEntry,
  showFiles,
  t,
  uploadFiles,
} = useWorkspaceContext()
const renamingEntry = ref<FileEntry | null>(null)

function uploadSelected(event: Event) {
  const input = event.target as HTMLInputElement
  if (input.files?.length) void uploadFiles(input.files)
  input.value = ""
}

async function submitRename(name: string) {
  if (!renamingEntry.value) return
  if (await renameEntry(renamingEntry.value, name)) renamingEntry.value = null
}
</script>

<template>
  <aside
    :class="[
      'fixed inset-y-0 right-0 z-40 flex w-full max-w-[420px] flex-col border-l border-line bg-white transition-transform duration-200 lg:static lg:w-[340px] lg:translate-x-0',
      showFiles ? 'translate-x-0' : 'translate-x-full',
    ]"
    aria-label="Workspace files"
  >
    <div class="flex h-16 shrink-0 items-center border-b border-line px-4">
      <button v-if="filePath" class="icon-button mr-1" :title="t('back')" @click="parentPath"><ArrowLeft :size="18" /></button>
      <h2 class="min-w-0 flex-1 truncate font-semibold">{{ filePath || t("files") }}</h2>
      <button class="icon-button lg:hidden" aria-label="Close files" @click="showFiles = false"><X :size="18" /></button>
    </div>

    <div class="flex shrink-0 gap-2 border-b border-line p-3">
      <label class="button-secondary flex-1 cursor-pointer">
        <Upload :size="16" />{{ t("upload") }}
        <input class="hidden" type="file" multiple @change="uploadSelected" />
      </label>
      <button class="icon-button border border-line" :title="t('newFolder')" @click="createFolder"><FolderPlus :size="18" /></button>
    </div>

    <p v-if="fileNotice" class="border-b border-emerald-200 bg-emerald-50 px-3 py-2 text-xs leading-5 text-emerald-800" role="status">
      {{ fileNotice }}
    </p>
    <p v-if="error" class="border-b border-red-200 bg-red-50 px-3 py-2 text-xs leading-5 text-red-800" role="alert">
      {{ error }}
    </p>

    <div class="min-h-0 flex-1 overflow-y-auto p-2">
      <p v-if="!files.length" class="p-6 text-center text-sm text-zinc-500">{{ t("emptyFolder") }}</p>
      <FileEntryRow
        v-for="entry in files"
        :key="entry.path"
        :entry="entry"
        @open="openEntry"
        @rename="renamingEntry = $event"
        @copy="copyEntryPath"
        @delete="deleteEntry"
      />
    </div>

    <div class="shrink-0 border-t border-line p-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
      <div class="mb-1 flex justify-between text-xs text-zinc-500">
        <span>Workspace</span><span>{{ formatBytes(quota.used) }} / {{ formatBytes(quota.limit) }}</span>
      </div>
      <div class="h-1.5 bg-zinc-100"><div class="h-full bg-accent" :style="{ width: `${Math.min(100, quota.used / quota.limit * 100)}%` }" /></div>
    </div>

    <RenameEntryDialog
      v-if="renamingEntry"
      :entry="renamingEntry"
      @cancel="renamingEntry = null"
      @submit="submitRename"
    />
    <DocumentPreviewDialog
      v-if="previewEntry"
      :entry="previewEntry"
      @close="previewEntry = null"
    />
  </aside>
</template>
