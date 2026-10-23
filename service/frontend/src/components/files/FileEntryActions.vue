<script setup lang="ts">
import { Copy, Download, EllipsisVertical, Lock, Pencil, Trash2, Unlock } from "lucide-vue-next"
import { computed, onBeforeUnmount, onMounted, ref } from "vue"

import type { FileEntry } from "../../api"
import { useWorkspaceContext } from "../../composables/useWorkspace"

const props = withDefaults(defineProps<{
  entry: FileEntry
  administrator?: boolean
  downloadHref?: string
}>(), {
  administrator: false,
  downloadHref: undefined,
})
const emit = defineEmits<{
  rename: [entry: FileEntry]
  copy: [entry: FileEntry]
  delete: [entry: FileEntry]
  protect: [entry: FileEntry, restricted: boolean]
}>()
const { t } = useWorkspaceContext()
const root = ref<HTMLElement | null>(null)
const isOpen = ref(false)
const hasActions = computed(() => props.administrator
  || props.entry.can_modify
  || props.entry.can_copy
  || (props.entry.type === "file" && props.entry.can_download))

function closeMenu() {
  isOpen.value = false
}

function handleDocumentClick(event: MouseEvent) {
  if (!root.value?.contains(event.target as Node)) closeMenu()
}

function handleEscape(event: KeyboardEvent) {
  if (event.key === "Escape") closeMenu()
}

onMounted(() => {
  document.addEventListener("click", handleDocumentClick)
  document.addEventListener("keydown", handleEscape)
})

onBeforeUnmount(() => {
  document.removeEventListener("click", handleDocumentClick)
  document.removeEventListener("keydown", handleEscape)
})

function choose(action: "rename" | "copy" | "delete") {
  closeMenu()
  if (action === "rename") emit("rename", props.entry)
  else if (action === "copy") emit("copy", props.entry)
  else emit("delete", props.entry)
}
</script>

<template>
  <div v-if="hasActions" ref="root" class="relative shrink-0">
    <button
      type="button"
      class="icon-button size-8 cursor-pointer list-none [&::-webkit-details-marker]:hidden"
      :aria-label="`${t('actions')}: ${entry.name}`"
      :aria-expanded="isOpen"
      :title="t('actions')"
      @click="isOpen = !isOpen"
    >
      <EllipsisVertical :size="16" />
    </button>
    <div v-if="isOpen" class="absolute right-0 top-9 z-20 w-52 border border-line bg-white py-1 shadow-panel">
      <button v-if="administrator || entry.can_modify" class="file-menu-action" type="button" @click="choose('rename')">
        <Pencil :size="15" />{{ t("rename") }}
      </button>
      <button v-if="administrator || entry.can_copy" class="file-menu-action" type="button" @click="choose('copy')">
        <Copy :size="15" />{{ t("copyPath") }}
      </button>
      <a
        v-if="entry.type === 'file' && (administrator || entry.can_download)"
        class="file-menu-action"
        :href="downloadHref || `/api/files/download?path=${encodeURIComponent(entry.path)}`"
        @click="closeMenu"
      >
        <Download :size="15" />{{ t("download") }}
      </a>
      <button
        v-if="administrator && !entry.no_user_access_inherited"
        class="file-menu-action"
        type="button"
        @click="closeMenu(); emit('protect', entry, !entry.no_user_access)"
      >
        <Unlock v-if="entry.no_user_access" :size="15" />
        <Lock v-else :size="15" />
        {{ entry.no_user_access ? t("allowUserAccess") : t("noUserAccess") }}
      </button>
      <div v-else-if="administrator && entry.no_user_access_inherited" class="file-menu-action cursor-default text-zinc-400">
        <Lock :size="15" />{{ t("protectedByParent") }}
      </div>
      <button v-if="administrator || entry.can_modify" class="file-menu-action text-red-700" type="button" @click="choose('delete')">
        <Trash2 :size="15" />{{ t("delete") }}
      </button>
    </div>
  </div>
</template>
