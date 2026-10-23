<script setup lang="ts">
import { BarChart3, Bot, Languages, LibraryBig, LogOut, MessageSquarePlus, Trash2, X } from "lucide-vue-next"

import { useWorkspaceContext } from "../../composables/useWorkspace"

const {
  activePage,
  conversations,
  locale,
  logout,
  newConversation,
  newPlanningConversation,
  openToolsPage,
  removeConversation,
  selectedConversation,
  selectConversation,
  showSidebar,
  switchLocale,
  t,
  user,
} = useWorkspaceContext()
</script>

<template>
  <aside
    :class="[
      'fixed inset-y-0 left-0 z-40 flex w-[min(86vw,280px)] flex-col border-r border-line bg-white transition-transform duration-200 lg:static lg:w-[280px] lg:translate-x-0',
      showSidebar ? 'visible translate-x-0' : 'invisible -translate-x-full lg:visible',
    ]"
    aria-label="Conversation navigation"
  >
    <div class="flex h-16 shrink-0 items-center justify-between border-b border-line px-4">
      <div class="flex min-w-0 items-center gap-2.5">
        <div class="grid size-8 shrink-0 place-items-center bg-ink text-white"><Bot :size="17" /></div>
        <div class="min-w-0">
          <strong class="block truncate text-sm">{{ user?.agent_name }}</strong>
          <span class="block truncate text-xs text-zinc-500">{{ user?.username }}</span>
        </div>
      </div>
      <button class="icon-button lg:hidden" aria-label="Close navigation" @click="showSidebar = false"><X :size="18" /></button>
    </div>

    <div class="p-3">
      <button class="button-primary w-full" @click="newConversation">
        <MessageSquarePlus :size="17" />{{ t("newChat") }}
      </button>
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto px-2">
      <p class="section-label">{{ t("conversations") }}</p>
      <div v-if="!conversations.length" class="px-3 py-6 text-center text-xs text-zinc-400">
        {{ t("noConversation") }}
      </div>
      <div
        v-for="item in conversations"
        :key="item.id"
        :class="[
          'group flex w-full items-center gap-2 px-3 py-2.5 text-left text-sm',
          activePage === 'chat' && selectedConversation?.id === item.id ? 'bg-soft-blue' : 'hover:bg-zinc-100',
        ]"
      >
        <button class="min-w-0 flex-1 truncate text-left" @click="selectConversation(item)">
          <span class="flex min-w-0 items-center gap-2">
            <BarChart3 v-if="item.kind === 'metabase_planning'" :size="14" class="shrink-0 text-accent" aria-hidden="true" />
            <span class="truncate">{{ item.title }}</span>
            <span v-if="item.kind === 'metabase_planning'" class="sr-only">{{ t("planningConversationMarker") }}</span>
          </span>
        </button>
        <button
          class="icon-button size-7 opacity-100 md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100"
          :aria-label="`${t('delete')}: ${item.title}`"
          @click="removeConversation(item)"
        ><Trash2 :size="15" /></button>
      </div>
    </div>

    <div class="shrink-0 border-t border-line p-3">
      <button
        class="mb-1 flex min-h-11 w-full items-center gap-2 border border-accent/30 bg-soft-blue px-2 text-left text-sm font-medium text-ink transition hover:border-accent hover:bg-white"
        @click="newPlanningConversation"
      >
        <BarChart3 :size="17" />{{ t("planningEntry") }}
      </button>
      <button
        :class="['mb-2 flex h-10 w-full items-center gap-2 px-2 text-left text-sm transition hover:bg-zinc-100', activePage === 'tools' ? 'bg-soft-blue text-ink' : 'text-zinc-600']"
        @click="openToolsPage"
      >
        <LibraryBig :size="17" />{{ t("tools") }}
      </button>
      <div class="flex gap-1">
        <button class="sidebar-action flex-1" @click="switchLocale"><Languages :size="16" />{{ locale.toUpperCase() }}</button>
        <button class="sidebar-action flex-1" @click="logout"><LogOut :size="16" />{{ t("signOut") }}</button>
      </div>
    </div>
  </aside>
</template>
