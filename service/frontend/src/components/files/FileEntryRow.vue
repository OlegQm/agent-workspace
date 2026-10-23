<script setup lang="ts">
import { ChevronRight, File, Folder, ShieldAlert } from "lucide-vue-next"

import type { FileEntry } from "../../api"
import { useWorkspaceContext } from "../../composables/useWorkspace"
import FileEntryActions from "./FileEntryActions.vue"

withDefaults(defineProps<{
  entry: FileEntry
  administrator?: boolean
  downloadHref?: string
}>(), {
  administrator: false,
  downloadHref: undefined,
})
const emit = defineEmits<{
  open: [entry: FileEntry]
  rename: [entry: FileEntry]
  copy: [entry: FileEntry]
  delete: [entry: FileEntry]
  protect: [entry: FileEntry, restricted: boolean]
}>()
const { formatBytes } = useWorkspaceContext()
</script>

<template>
  <div class="group flex min-h-11 items-center gap-1 px-2 py-1.5 hover:bg-zinc-100 focus-within:bg-zinc-100">
    <button class="flex min-w-0 flex-1 items-center gap-2 py-1 text-left" @click="emit('open', entry)">
      <Folder v-if="entry.type === 'directory'" :size="18" class="shrink-0 text-accent" />
      <File v-else :size="18" class="shrink-0 text-zinc-500" />
      <span class="min-w-0 flex-1 truncate text-sm">{{ entry.name }}</span>
      <span v-if="entry.size !== null" class="shrink-0 text-[11px] text-zinc-400">{{ formatBytes(entry.size) }}</span>
      <ShieldAlert v-if="entry.no_user_access" :size="15" class="shrink-0 text-amber-700" />
      <ChevronRight v-if="entry.type === 'directory'" :size="15" class="shrink-0" />
    </button>
    <FileEntryActions
      :entry="entry"
      :administrator="administrator"
      :download-href="downloadHref"
      @rename="emit('rename', $event)"
      @copy="emit('copy', $event)"
      @delete="emit('delete', $event)"
      @protect="(item, value) => emit('protect', item, value)"
    />
  </div>
</template>
