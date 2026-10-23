<script setup lang="ts">
import { Check, ExternalLink, LoaderCircle, RefreshCw, Send, X } from "lucide-vue-next"
import { computed } from "vue"

import { api, type PlanningStatement } from "../../../api"
import { useWorkspaceContext } from "../../../composables/useWorkspace"
import ReviewConfirmationDialog from "./ReviewConfirmationDialog.vue"

const {
  acceptPlanningMatch,
  planning,
  planningAction,
  refreshPlanningStatus,
  rejectPlanningMatch,
  reviewConfirmationOpen,
  selectedConversation,
  t,
} = useWorkspaceContext()

const sections = computed(() => {
  const plan = planning.value?.plan?.content
  if (!plan) return []
  return [
    [t.value("planningMetrics"), plan.metrics],
    [t.value("planningSources"), plan.sources],
    [t.value("planningPeriod"), plan.period],
    [t.value("planningGrouping"), plan.grain],
    [t.value("planningBreakdowns"), plan.dimensions],
    [t.value("planningFilters"), plan.filters],
    [t.value("planningComparisons"), plan.comparisons],
    [t.value("planningExclusions"), plan.exclusions],
    [t.value("planningVisualization"), plan.visualization],
    [t.value("planningInterpretation"), plan.expected_interpretation],
    [t.value("planningAssumptions"), plan.assumptions],
    [t.value("planningAnswers"), plan.explicit_answers],
  ] as [string, PlanningStatement[]][]
})
</script>

<template>
  <section v-if="planning && selectedConversation" class="border border-line bg-white" aria-label="Metabase planning status">
    <div v-if="planning.candidate" class="p-4 sm:p-5">
      <p class="section-label !px-0 !pt-0">{{ t("planningExistingMatch") }}</p>
      <h3 class="mt-2 font-semibold">{{ planning.candidate.title }}</h3>
      <p class="mt-2 text-sm leading-6 text-zinc-600">{{ planning.candidate.summary }}</p>
      <div class="mt-4 flex flex-col gap-2 sm:flex-row">
        <button class="button-primary min-h-11 justify-center" :disabled="!planning.actions.accept_match.enabled || Boolean(planningAction)" :aria-busy="planningAction === 'accept_match'" @click="acceptPlanningMatch">
          <LoaderCircle v-if="planningAction === 'accept_match'" :size="17" class="animate-spin" aria-hidden="true" />
          <Check v-else :size="17" aria-hidden="true" />{{ t("planningUseExisting") }}
        </button>
        <button class="button-secondary min-h-11 justify-center" :disabled="!planning.actions.reject_match.enabled || Boolean(planningAction)" :aria-busy="planningAction === 'reject_match'" @click="rejectPlanningMatch">
          <LoaderCircle v-if="planningAction === 'reject_match'" :size="17" class="animate-spin" aria-hidden="true" />
          <X v-else :size="17" aria-hidden="true" />{{ t("planningNotMatch") }}
        </button>
      </div>
    </div>

    <div v-if="planning.plan" class="p-4 sm:p-5">
      <p class="section-label !px-0 !pt-0">{{ t("planningPlanReady") }}</p>
      <div class="max-w-4xl">
        <h3 class="mt-2 text-base font-semibold">{{ t("planningBusinessQuestion") }}</h3>
        <p class="mt-1 text-sm leading-6">{{ planning.plan.content.business_question.text }}</p>
        <div class="mt-5 space-y-5">
          <div v-for="[title, statements] in sections" :key="title" v-show="statements.length">
            <h4 class="text-xs font-semibold uppercase text-zinc-500">{{ title }}</h4>
            <ul class="mt-1 space-y-1 text-sm leading-6">
              <li v-for="statement in statements" :key="statement.text" class="before:mr-2 before:content-['•']">{{ statement.text }}</li>
            </ul>
          </div>
        </div>
      </div>
      <button
        v-if="planning.actions.send_for_review.visible"
        class="button-primary mt-5 min-h-11 w-full justify-center sm:w-auto"
        :disabled="!planning.actions.send_for_review.enabled || Boolean(planningAction)"
        :aria-busy="planningAction === 'send_for_review'"
        @click="reviewConfirmationOpen = true"
      >
        <LoaderCircle v-if="planningAction === 'send_for_review'" :size="17" class="animate-spin" aria-hidden="true" />
        <Send v-else :size="17" aria-hidden="true" />{{ planning.actions.send_for_review.mode === "update" ? t("planningUpdateReview") : t("planningSendReview") }}
      </button>
    </div>

    <div v-if="planning.actions.open_metabase.visible" class="p-4 sm:p-5">
      <p class="text-sm text-zinc-600">{{ t("planningResolvedHint") }}</p>
      <a class="button-primary mt-4 min-h-11 w-full justify-center sm:w-auto" :href="api.planningMetabaseUrl(selectedConversation.id)" target="_blank" rel="noopener noreferrer">
        <ExternalLink :size="17" />{{ t("planningOpenMetabase") }}
      </a>
    </div>

    <div v-if="planning.review.issue_key" class="border-t border-line p-4 sm:p-5">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p class="text-sm font-semibold">{{ t("planningSubmitted") }}</p>
          <p class="mt-1 text-sm text-zinc-600">
            <a :href="api.planningReviewUrl(selectedConversation.id)" target="_blank" rel="noopener noreferrer" class="font-medium text-accent underline">{{ planning.review.issue_key }}</a>
            <span v-if="planning.review.status"> · {{ planning.review.status }}</span>
          </p>
          <p v-if="planning.review.submitted_at" class="mt-1 text-xs text-zinc-500">{{ t("planningLastSubmitted") }} {{ new Date(planning.review.submitted_at).toLocaleString() }}</p>
          <p v-if="planning.review.status_refresh_error" role="status" class="mt-1 text-xs text-amber-700">{{ t("planningStatusUnavailable") }}</p>
        </div>
        <button
          v-if="planning.actions.refresh_status.visible"
          class="button-secondary min-h-11 justify-center"
          :disabled="!planning.actions.refresh_status.enabled || Boolean(planningAction)"
          :aria-busy="planningAction === 'refresh_status'"
          @click="refreshPlanningStatus"
        >
          <RefreshCw :size="17" :class="planningAction === 'refresh_status' ? 'animate-spin' : ''" aria-hidden="true" />{{ t("planningRefreshStatus") }}
        </button>
      </div>
    </div>
  </section>
  <ReviewConfirmationDialog />
</template>
