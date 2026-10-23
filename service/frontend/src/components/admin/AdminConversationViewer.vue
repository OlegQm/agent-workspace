<script setup lang="ts">
import { ArrowLeft, BarChart3, Bot, Download, LockKeyhole, Paperclip, UserRound } from "lucide-vue-next"

import type { ConversationDetail, Message } from "../../api"
import { useWorkspaceContext } from "../../composables/useWorkspace"
import MarkdownContent from "../common/MarkdownContent.vue"

defineProps<{
  conversation: ConversationDetail | null
  exportHref?: string
  loading: boolean
}>()

defineEmits<{ back: [] }>()

const { locale, t } = useWorkspaceContext()

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(locale.value === "sk" ? "sk-SK" : "en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value))
}

function roleLabel(message: Message): string {
  return message.role === "user" ? t.value("userMessage") : t.value("assistantMessage")
}
</script>

<template>
  <section class="flex min-h-0 flex-1 flex-col bg-[#f7f8f5]">
    <header class="flex min-h-14 shrink-0 items-center gap-3 border-b border-line bg-white px-3 sm:px-5">
      <button class="icon-button lg:hidden" type="button" :title="t('backToChats')" @click="$emit('back')">
        <ArrowLeft :size="18" />
      </button>
      <div class="min-w-0 flex-1">
        <h2 class="truncate text-sm font-semibold sm:text-base">{{ conversation?.title || t("selectConversation") }}</h2>
        <p v-if="conversation" class="flex items-center gap-1.5 truncate text-xs text-zinc-500">
          <BarChart3 v-if="conversation.kind === 'metabase_planning'" :size="12" class="shrink-0 text-accent" />
          <span v-if="conversation.kind === 'metabase_planning'">{{ t("planningConversationMarker") }} · </span>{{ formatDate(conversation.updated_at) }}
        </p>
      </div>
      <a
        v-if="conversation && exportHref"
        class="inline-flex h-9 shrink-0 items-center justify-center gap-2 border border-line bg-white px-2.5 text-sm font-medium text-zinc-700 transition hover:border-zinc-400 hover:bg-zinc-50 sm:px-3"
        :href="exportHref"
        :aria-label="t('exportConversation')"
        :title="t('exportConversation')"
      >
        <Download :size="16" />
        <span class="hidden sm:inline">{{ t("exportConversation") }}</span>
      </a>
      <span class="inline-flex h-9 shrink-0 items-center gap-1.5 border border-line bg-zinc-50 px-2.5 text-xs text-zinc-600" :aria-label="t('readOnlyChat')" :title="t('readOnlyChat')">
        <LockKeyhole :size="13" />
        <span>{{ t("readOnlyChat") }}</span>
      </span>
    </header>

    <div v-if="loading" class="grid min-h-0 flex-1 place-items-center text-sm text-zinc-500">{{ t("running") }}</div>
    <div v-else-if="!conversation" class="grid min-h-0 flex-1 place-items-center px-6 text-center">
      <div class="max-w-sm">
        <LockKeyhole :size="28" class="mx-auto mb-3 text-zinc-300" />
        <p class="font-medium">{{ t("selectConversation") }}</p>
        <p class="mt-1 text-sm text-zinc-500">{{ t("readOnlyChatHint") }}</p>
      </div>
    </div>
    <div v-else-if="!conversation.messages.length" class="grid min-h-0 flex-1 place-items-center px-6 text-center text-sm text-zinc-500">
      {{ t("noMessages") }}
    </div>
    <div v-else class="min-h-0 flex-1 overflow-y-auto px-3 py-4 sm:px-6 sm:py-6">
      <div class="mx-auto max-w-4xl space-y-5">
        <article v-for="message in conversation.messages" :key="message.id" class="min-w-0">
          <div class="mb-1.5 flex items-center gap-2 px-1 text-xs text-zinc-500">
            <component :is="message.role === 'user' ? UserRound : Bot" :size="14" />
            <strong class="font-medium text-zinc-700">{{ roleLabel(message) }}</strong>
            <time class="ml-auto">{{ formatDate(message.created_at) }}</time>
          </div>
          <div
            :class="[
              'min-w-0 px-4 py-3 text-sm leading-6 sm:px-5 sm:py-4',
              message.role === 'user'
                ? 'ml-auto max-w-[94%] whitespace-pre-wrap bg-ink text-white sm:max-w-[85%]'
                : 'border border-line bg-white',
            ]"
          >
            <MarkdownContent v-if="message.role === 'assistant'" :content="message.content" />
            <template v-else>{{ message.content }}</template>
            <div v-if="message.attachments.length" class="mt-3 flex flex-wrap gap-2 border-t border-current/15 pt-3">
              <span
                v-for="attachment in message.attachments"
                :key="attachment"
                class="inline-flex min-w-0 max-w-full items-center gap-1.5 bg-black/5 px-2 py-1 text-xs"
              >
                <Paperclip :size="12" class="shrink-0" />
                <span class="truncate">{{ attachment }}</span>
              </span>
            </div>
          </div>
        </article>
      </div>
    </div>
  </section>
</template>
