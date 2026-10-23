<script setup lang="ts">
import { CircleStop, File, Paperclip, Send, X } from "lucide-vue-next"

import { useWorkspaceContext } from "../../composables/useWorkspace"
import ModelModeSelector from "./ModelModeSelector.vue"

const {
  attachments,
  draft,
  isNewConversation,
  isNewPlanningConversation,
  isRunning,
  removeAttachment,
  selectedConversation,
  sendMessage,
  stopRun,
  t,
  uploadFiles,
} = useWorkspaceContext()

function uploadSelected(event: Event) {
  const input = event.target as HTMLInputElement
  if (input.files?.length) void uploadFiles(input.files)
  input.value = ""
}
</script>

<template>
  <footer class="shrink-0 border-t border-line bg-white px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 sm:px-5 sm:pt-4">
    <div class="mx-auto max-w-3xl">
      <ModelModeSelector />
      <div v-if="attachments.length" class="mb-2 flex max-h-24 flex-wrap gap-2 overflow-y-auto">
        <span v-for="path in attachments" :key="path" class="flex min-w-0 max-w-full items-center gap-1 border border-line bg-paper px-2 py-1 text-xs">
          <File :size="13" class="shrink-0" /><span class="truncate">{{ path }}</span>
          <button class="shrink-0" :aria-label="`${t('delete')}: ${path}`" @click="removeAttachment(path)"><X :size="13" /></button>
        </span>
      </div>
      <div class="flex items-end gap-1.5 border border-zinc-300 bg-white p-2 focus-within:border-accent sm:gap-2">
        <label class="icon-button cursor-pointer disabled:opacity-40" :title="t('upload')">
          <Paperclip :size="19" />
          <input class="hidden" type="file" multiple @change="uploadSelected" />
        </label>
        <textarea
          v-model="draft"
          :disabled="(!selectedConversation && !isNewConversation && !isNewPlanningConversation) || isRunning"
          rows="1"
          :placeholder="isNewPlanningConversation || selectedConversation?.kind === 'metabase_planning' ? t('planningMessagePlaceholder') : t('messagePlaceholder')"
          class="max-h-40 min-h-10 min-w-0 flex-1 resize-none bg-transparent px-1 py-2 text-base outline-none sm:text-sm"
          @keydown.enter.exact.prevent="sendMessage"
        />
        <button v-if="isRunning" class="icon-button bg-red-50 text-red-700" :title="t('stop')" @click="stopRun"><CircleStop :size="20" /></button>
        <button v-else class="icon-button bg-accent text-white hover:bg-accent-dark disabled:opacity-40" :disabled="(!selectedConversation && !isNewConversation && !isNewPlanningConversation) || !draft.trim()" :title="t('send')" @click="sendMessage"><Send :size="19" /></button>
      </div>
    </div>
  </footer>
</template>
