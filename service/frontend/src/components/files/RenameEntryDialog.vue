<script setup lang="ts">
import { FilePenLine, FolderPen, X } from "lucide-vue-next"
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue"

import type { FileEntry } from "../../api"
import { useWorkspaceContext } from "../../composables/useWorkspace"

const props = defineProps<{ entry: FileEntry }>()
const emit = defineEmits<{ cancel: []; submit: [name: string] }>()
const { t } = useWorkspaceContext()
const name = ref(props.entry.name)
const input = ref<HTMLInputElement | null>(null)
const parentPath = computed(() => props.entry.path.split("/").slice(0, -1).join("/") || "/")

function closeOnEscape(event: KeyboardEvent) {
  if (event.key === "Escape") emit("cancel")
}

onMounted(async () => {
  document.addEventListener("keydown", closeOnEscape)
  await nextTick()
  input.value?.focus()
  const extensionStart = props.entry.type === "file" ? props.entry.name.lastIndexOf(".") : -1
  input.value?.setSelectionRange(0, extensionStart > 0 ? extensionStart : props.entry.name.length)
})

onBeforeUnmount(() => document.removeEventListener("keydown", closeOnEscape))
</script>

<template>
  <Teleport to="body">
    <div
      class="fixed inset-0 z-[70] flex items-end justify-center bg-black/45 sm:items-center sm:p-5"
      @mousedown.self="emit('cancel')"
    >
      <section
        class="w-full border border-line bg-white shadow-2xl sm:max-w-lg sm:rounded-lg"
        role="dialog"
        aria-modal="true"
        :aria-label="t('renameEntry')"
      >
        <header class="flex min-h-16 items-center gap-3 border-b border-line px-4 sm:px-6">
          <span class="grid size-10 shrink-0 place-items-center rounded-md bg-emerald-50 text-accent">
            <FolderPen v-if="entry.type === 'directory'" :size="20" />
            <FilePenLine v-else :size="20" />
          </span>
          <div class="min-w-0 flex-1">
            <h3 class="font-semibold">{{ t("renameEntry") }}</h3>
            <p class="truncate text-xs text-zinc-500" :title="parentPath">{{ parentPath }}</p>
          </div>
          <button class="icon-button" type="button" :aria-label="t('close')" @click="emit('cancel')">
            <X :size="19" />
          </button>
        </header>

        <form class="px-4 py-5 sm:px-6 sm:py-6" @submit.prevent="emit('submit', name.trim())">
          <label class="block text-sm font-medium" for="rename-entry-input">{{ t("newName") }}</label>
          <input
            id="rename-entry-input"
            ref="input"
            v-model="name"
            class="input mt-2 h-12 rounded-md"
            maxlength="255"
            autocomplete="off"
            spellcheck="false"
          />
          <p class="mt-2 break-all text-xs leading-5 text-zinc-500">{{ entry.name }}</p>

          <div class="mt-6 grid grid-cols-2 gap-3 sm:flex sm:justify-end">
            <button class="button-secondary h-11 rounded-md sm:min-w-24" type="button" @click="emit('cancel')">{{ t("cancel") }}</button>
            <button
              class="button-primary h-11 rounded-md sm:min-w-24"
              type="submit"
              :disabled="!name.trim() || name.trim() === entry.name"
            >
              {{ t("save") }}
            </button>
          </div>
        </form>
      </section>
    </div>
  </Teleport>
</template>
