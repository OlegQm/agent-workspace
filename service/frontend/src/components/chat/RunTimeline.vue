<script setup lang="ts">
import { CheckCircle2, LoaderCircle, XCircle } from "lucide-vue-next"

import { useWorkspaceContext } from "../../composables/useWorkspace"
import MarkdownContent from "../common/MarkdownContent.vue"

const { activeRun, approve, displayPayload, streamText, t, visibleEvents } = useWorkspaceContext()

function eventState(type: string): "pending" | "complete" | "failed" {
  if (/(failed|error|cancelled|denied)/i.test(type)) return "failed"
  if (/(completed|complete|result|response|ready)/i.test(type)) return "complete"
  return "pending"
}
</script>

<template>
  <article class="space-y-3">
    <div
      v-for="event in visibleEvents"
      :key="event.sequence"
      class="flex items-start gap-3 border-l-2 border-zinc-300 py-1 pl-3 text-xs text-zinc-600"
    >
      <LoaderCircle v-if="eventState(event.type) === 'pending'" class="mt-0.5 shrink-0 animate-spin" :size="14" />
      <CheckCircle2 v-else-if="eventState(event.type) === 'complete'" class="mt-0.5 shrink-0 text-emerald-700" :size="14" />
      <XCircle v-else class="mt-0.5 shrink-0 text-red-700" :size="14" />
      <div class="min-w-0 break-words">
        <strong class="block font-medium text-zinc-800">{{ event.type }}</strong>
        {{ displayPayload(event) }}
      </div>
    </div>
    <div v-if="streamText" class="max-w-[92%] border border-line bg-white px-4 py-3 text-sm leading-6 sm:max-w-[86%]">
      <MarkdownContent :content="streamText" />
    </div>
    <div v-if="activeRun?.status === 'waiting_approval'" class="flex flex-wrap items-center gap-2 border border-amber-300 bg-amber-50 p-3 text-sm">
      <span class="min-w-[12rem] flex-1">{{ t("waitingApproval") }}</span>
      <button class="button-secondary" @click="approve('deny')">{{ t("deny") }}</button>
      <button class="button-primary" @click="approve('once')">{{ t("approveOnce") }}</button>
    </div>
  </article>
</template>
