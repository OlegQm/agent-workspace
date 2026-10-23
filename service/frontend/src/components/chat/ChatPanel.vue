<script setup lang="ts">
import { BarChart3, Bot, Menu, MessageSquarePlus, Paperclip } from "lucide-vue-next"

import { useWorkspaceContext } from "../../composables/useWorkspace"
import PlanningPanel from "../../features/metabase-planning/components/PlanningPanel.vue"
import MessageBubble from "./MessageBubble.vue"
import MessageComposer from "./MessageComposer.vue"
import RunTimeline from "./RunTimeline.vue"

const {
  error,
  isNewConversation,
  isNewPlanningConversation,
  isRunning,
  messages,
  messagesEl,
  newConversation,
  selectedConversation,
  showFiles,
  showSidebar,
  t,
  user,
} = useWorkspaceContext()

function setMessagesElement(element: unknown) {
  messagesEl.value = element as HTMLElement | null
}
</script>

<template>
  <section class="flex min-h-0 min-w-0 flex-1 flex-col">
    <header class="flex h-16 shrink-0 items-center border-b border-line bg-white px-3 sm:px-5 lg:px-6">
      <button class="icon-button mr-1 lg:hidden" aria-label="Open navigation" @click="showSidebar = true"><Menu :size="20" /></button>
      <h2 class="min-w-0 flex-1 truncate font-semibold">{{ isNewPlanningConversation ? t("planningTitle") : isNewConversation ? t("newChat") : selectedConversation?.title ?? user?.agent_name }}</h2>
      <button class="icon-button lg:hidden" :title="t('files')" @click="showFiles = true"><Paperclip :size="19" /></button>
    </header>

    <div :ref="setMessagesElement" class="min-h-0 flex-1 overflow-y-auto px-3 py-5 sm:px-5 sm:py-6 lg:px-8">
      <p v-if="error && !selectedConversation && !isNewConversation && !isNewPlanningConversation" class="mx-auto mb-4 max-w-3xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
      <div v-if="!selectedConversation && !isNewConversation && !isNewPlanningConversation" class="mx-auto grid h-full max-w-xl place-content-center px-4 text-center">
        <div class="mx-auto mb-5 grid size-14 place-items-center border border-line bg-white"><Bot :size="25" /></div>
        <h3 class="text-lg font-semibold sm:text-xl">{{ t("noConversation") }}</h3>
        <p class="mt-2 text-sm leading-6 text-zinc-500">{{ t("noConversationHint") }}</p>
        <button class="button-primary mx-auto mt-6" @click="newConversation"><MessageSquarePlus :size="17" />{{ t("newChat") }}</button>
      </div>
      <div v-else-if="isNewPlanningConversation" class="mx-auto grid h-full max-w-xl place-content-center px-4 text-center">
        <div class="mx-auto mb-5 grid size-14 place-items-center border border-accent/30 bg-soft-blue"><BarChart3 :size="25" /></div>
        <h3 class="text-lg font-semibold sm:text-xl">{{ t("planningTitle") }}</h3>
        <p class="mt-2 text-sm leading-6 text-zinc-500">{{ t("planningIntro") }}</p>
      </div>
      <div v-else class="mx-auto max-w-3xl space-y-6 sm:space-y-7">
        <MessageBubble v-for="message in messages" :key="message.id" :message="message" />
        <RunTimeline v-if="isRunning" />
        <PlanningPanel v-if="selectedConversation?.kind === 'metabase_planning' && !isRunning" />
        <p v-if="error" class="border border-red-200 bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
      </div>
    </div>

    <MessageComposer v-if="selectedConversation || isNewConversation || isNewPlanningConversation" />
  </section>
</template>
