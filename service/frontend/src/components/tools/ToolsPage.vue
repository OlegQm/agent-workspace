<script setup lang="ts">
import { BookOpenCheck, Database, Menu, Paperclip, ShieldCheck } from "lucide-vue-next"
import { computed } from "vue"

import { useWorkspaceContext } from "../../composables/useWorkspace"
import { describeTools } from "../../lib/toolCatalog"

const { locale, showFiles, showSidebar, t, user } = useWorkspaceContext()
const tools = computed(() => describeTools(user.value?.tools ?? [], locale.value))
</script>

<template>
  <section class="flex min-h-0 min-w-0 flex-1 flex-col bg-paper">
    <header class="flex h-16 shrink-0 items-center border-b border-line bg-white px-3 sm:px-5 lg:px-6">
      <button class="icon-button mr-1 lg:hidden" aria-label="Open navigation" @click="showSidebar = true"><Menu :size="20" /></button>
      <h2 class="min-w-0 flex-1 truncate font-semibold">{{ t("tools") }}</h2>
      <button class="icon-button lg:hidden" :title="t('files')" @click="showFiles = true"><Paperclip :size="19" /></button>
    </header>

    <div class="min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-6 sm:py-8 lg:px-10">
      <div class="mx-auto max-w-5xl">
        <div class="flex max-w-3xl items-start gap-4">
          <div class="grid size-11 shrink-0 place-items-center border border-line bg-white text-accent"><BookOpenCheck :size="22" /></div>
          <div>
            <h1 class="text-xl font-semibold sm:text-2xl">{{ t("tools") }}</h1>
            <p class="mt-2 text-sm leading-6 text-zinc-600 sm:text-base">{{ t("toolsIntro") }}</p>
          </div>
        </div>

        <div class="mt-6 flex items-start gap-3 border border-emerald-200 bg-emerald-50 p-4 text-emerald-950 sm:mt-8">
          <ShieldCheck :size="20" class="mt-0.5 shrink-0" />
          <div>
            <strong class="block text-sm">{{ t("readOnlyAccess") }}</strong>
            <p class="mt-1 text-sm leading-5 text-emerald-900/80">{{ t("toolsHint") }}</p>
          </div>
        </div>

        <p v-if="!tools.length" class="mt-10 text-sm text-zinc-500">{{ t("noTools") }}</p>
        <div v-else class="mt-8 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <article v-for="tool in tools" :key="tool.id" class="min-w-0 border border-line bg-white p-4 sm:p-5">
            <div class="flex items-center gap-3">
              <div class="grid size-9 shrink-0 place-items-center bg-zinc-100 text-zinc-700"><Database :size="18" /></div>
              <h2 class="min-w-0 text-sm font-semibold sm:text-base">{{ tool.name }}</h2>
            </div>
            <p class="mt-3 text-sm leading-6 text-zinc-600">{{ tool.description }}</p>
            <p class="mt-3 border-t border-line pt-3 text-xs leading-5 text-zinc-500">{{ tool.examples }}</p>
          </article>
        </div>
      </div>
    </div>
  </section>
</template>
