<script setup lang="ts">
import ChatPanel from "../chat/ChatPanel.vue"
import FilePanel from "../files/FilePanel.vue"
import ToolsPage from "../tools/ToolsPage.vue"
import { useWorkspaceContext } from "../../composables/useWorkspace"
import ConversationSidebar from "./ConversationSidebar.vue"

const { activePage, dragging, showFiles, showSidebar, t, uploadFiles } = useWorkspaceContext()

function dropFiles(event: DragEvent) {
  dragging.value = false
  if (event.dataTransfer?.files.length) void uploadFiles(event.dataTransfer.files)
}
</script>

<template>
  <main
    class="h-[100dvh] overflow-hidden bg-paper text-ink"
    @dragenter.prevent="dragging = true"
    @dragover.prevent
    @dragleave.self="dragging = false"
    @drop.prevent="dropFiles"
  >
    <div v-if="dragging" class="fixed inset-3 z-50 grid place-items-center border-2 border-dashed border-accent bg-white/95 px-6 text-center text-lg font-semibold">
      {{ t("dropFiles") }}
    </div>

    <button v-if="showSidebar" class="fixed inset-0 z-30 bg-black/25 lg:hidden" aria-label="Close navigation" @click="showSidebar = false" />
    <button v-if="showFiles" class="fixed inset-0 z-30 bg-black/25 lg:hidden" aria-label="Close files" @click="showFiles = false" />

    <div class="flex h-full min-w-0">
      <ConversationSidebar />
      <ToolsPage v-if="activePage === 'tools'" />
      <ChatPanel v-else />
      <FilePanel />
    </div>
  </main>
</template>
