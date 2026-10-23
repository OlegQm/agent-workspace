<script setup lang="ts">
import { computed } from "vue"
import { Earth, Moon, Sun } from "lucide-vue-next"

import type { ModelMode } from "../../api"
import { useWorkspaceContext } from "../../composables/useWorkspace"

const {
  isNewConversation,
  isRunning,
  modelMode,
  selectedConversation,
  setModelMode,
  t,
  user,
} = useWorkspaceContext()

const icons: Record<ModelMode, typeof Moon> = { small: Moon, medium: Earth, high: Sun }
const modes = computed(() => user.value?.model_modes ?? [])
</script>

<template>
  <div class="mb-2 flex min-w-0 flex-col gap-1.5 sm:flex-row sm:items-center sm:justify-between">
    <span class="text-xs font-medium text-zinc-500">{{ t("model") }}</span>
    <div
      class="grid w-full grid-cols-3 border border-zinc-300 bg-paper p-0.5 sm:w-auto"
      role="radiogroup"
      :aria-label="t('model')"
    >
      <button
        v-for="mode in modes"
        :key="mode.value"
        type="button"
        role="radio"
        :aria-checked="modelMode === mode.value"
        :aria-label="`${t(mode.value)} - ${mode.description}`"
        :title="mode.description"
        :disabled="(!selectedConversation && !isNewConversation) || isRunning"
        class="flex h-8 min-w-0 items-center justify-center gap-1.5 px-2 text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-40 sm:min-w-28"
        :class="modelMode === mode.value ? 'bg-ink text-white' : 'text-zinc-600 hover:bg-white'"
        @click="setModelMode(mode.value)"
      >
        <component :is="icons[mode.value]" :size="14" class="shrink-0" />
        <span class="truncate font-medium">{{ mode.label }}</span>
        <span class="hidden text-[10px] opacity-70 sm:inline">{{ t(mode.value) }}</span>
      </button>
    </div>
  </div>
</template>
