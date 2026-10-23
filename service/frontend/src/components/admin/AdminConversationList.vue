<script setup lang="ts">
import { BarChart3, MessageSquareText } from "lucide-vue-next"

import type { Conversation } from "../../api"
import { useWorkspaceContext } from "../../composables/useWorkspace"

defineProps<{
  conversations: Conversation[]
  selectedId: string | null
  loading: boolean
}>()

defineEmits<{ select: [conversation: Conversation] }>()

const { locale, t } = useWorkspaceContext()

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(locale.value === "sk" ? "sk-SK" : "en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value))
}
</script>

<template>
  <section class="flex min-h-0 flex-1 flex-col border-line bg-white lg:border-r">
    <header class="flex min-h-14 shrink-0 items-center gap-2 border-b border-line px-4">
      <MessageSquareText :size="18" class="text-accent" />
      <h2 class="font-semibold">{{ t("chatHistory") }}</h2>
      <span v-if="conversations.length" class="ml-auto text-xs tabular-nums text-zinc-500">{{ conversations.length }}</span>
    </header>

    <div class="min-h-0 flex-1 overflow-y-auto p-2">
      <p v-if="loading" class="p-8 text-center text-sm text-zinc-500">{{ t("running") }}</p>
      <div v-else-if="!conversations.length" class="grid min-h-52 place-items-center px-6 text-center">
        <div>
          <MessageSquareText :size="26" class="mx-auto mb-3 text-zinc-300" />
          <p class="text-sm text-zinc-500">{{ t("noUserConversations") }}</p>
        </div>
      </div>
      <button
        v-for="conversation in conversations"
        v-else
        :key="conversation.id"
        type="button"
        :class="[
          'mb-1 w-full border-l-2 px-3 py-3 text-left transition',
          selectedId === conversation.id
            ? 'border-accent bg-soft-blue'
            : 'border-transparent hover:bg-zinc-100',
        ]"
        @click="$emit('select', conversation)"
      >
        <span class="flex min-w-0 items-center gap-2">
          <BarChart3 v-if="conversation.kind === 'metabase_planning'" :size="14" class="shrink-0 text-accent" />
          <strong class="block truncate text-sm font-medium">{{ conversation.title }}</strong>
        </span>
        <span v-if="conversation.kind === 'metabase_planning'" class="mt-1 inline-flex border border-accent/30 bg-soft-blue px-1.5 py-0.5 text-[11px] text-zinc-700">{{ t("planningConversationMarker") }}</span>
        <span class="mt-1 block text-xs text-zinc-500">{{ formatDate(conversation.updated_at) }}</span>
      </button>
    </div>
  </section>
</template>
