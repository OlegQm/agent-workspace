<script setup lang="ts">
import { LoaderCircle, Send, X } from "lucide-vue-next"
import { nextTick, ref, watch } from "vue"

import { useWorkspaceContext } from "../../../composables/useWorkspace"

const {
  confirmPlanningReview,
  error,
  planningAction,
  reviewConfirmationOpen,
  t,
} = useWorkspaceContext()

const dialogElement = ref<HTMLElement | null>(null)

function closeDialog() {
  if (!planningAction.value) reviewConfirmationOpen.value = false
}

watch(reviewConfirmationOpen, async (open) => {
  if (!open) return
  await nextTick()
  dialogElement.value?.focus()
})
</script>

<template>
  <div v-if="reviewConfirmationOpen" class="fixed inset-0 z-50 flex items-end bg-black/35 p-0 sm:items-center sm:justify-center sm:p-5" @click.self="closeDialog">
    <section ref="dialogElement" class="max-h-[90dvh] w-full overflow-y-auto border border-line bg-white p-5 shadow-xl sm:max-w-md" role="dialog" aria-modal="true" :aria-label="t('planningReviewConfirmTitle')" :aria-busy="planningAction === 'send_for_review'" tabindex="-1" @keydown.esc.stop.prevent="closeDialog">
      <div class="flex items-start justify-between gap-4">
        <div>
          <h3 class="text-base font-semibold">{{ t("planningReviewConfirmTitle") }}</h3>
          <p class="mt-2 text-sm leading-6 text-zinc-600">{{ t("planningReviewConfirmHint") }}</p>
        </div>
        <button class="icon-button shrink-0" :aria-label="t('close')" :disabled="Boolean(planningAction)" @click="closeDialog"><X :size="18" /></button>
      </div>
      <p v-if="error" class="mt-4 border border-red-200 bg-red-50 p-3 text-sm text-red-800" role="alert">
        {{ error }}
      </p>
      <div class="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <button class="button-secondary min-h-11 justify-center" :disabled="Boolean(planningAction)" @click="closeDialog">{{ t("cancel") }}</button>
        <button class="button-primary min-h-11 justify-center" :disabled="Boolean(planningAction)" @click="confirmPlanningReview">
          <LoaderCircle v-if="planningAction === 'send_for_review'" :size="17" class="animate-spin" aria-hidden="true" />
          <Send v-else :size="17" aria-hidden="true" />{{ t("planningSendReview") }}
        </button>
      </div>
    </section>
  </div>
</template>
