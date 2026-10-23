<script setup lang="ts">
import { Files, Languages, LogOut, MessageSquareText, ShieldCheck, Users } from "lucide-vue-next"
import { onMounted, ref } from "vue"

import { api, type AdminManagedUser } from "../../api"
import { useWorkspaceContext } from "../../composables/useWorkspace"
import AdminConversationBrowser from "./AdminConversationBrowser.vue"
import AdminFileBrowser from "./AdminFileBrowser.vue"

const { locale, logout, switchLocale, t } = useWorkspaceContext()
const users = ref<AdminManagedUser[]>([])
const selected = ref<AdminManagedUser | null>(null)
const section = ref<"files" | "chats">("files")
const error = ref("")

function selectById(userId: string) {
  selected.value = users.value.find((user) => user.id === userId) ?? null
}

onMounted(async () => {
  try {
    users.value = await api.adminUsers()
    selected.value = users.value[0] ?? null
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause)
  }
})
</script>

<template>
  <main class="flex h-[100dvh] flex-col overflow-hidden bg-paper text-ink">
    <header class="flex min-h-16 shrink-0 items-center gap-3 border-b border-line bg-white px-4 sm:px-6">
      <div class="grid size-9 shrink-0 place-items-center bg-ink text-white"><ShieldCheck :size="19" /></div>
      <div class="min-w-0 flex-1">
        <h1 class="truncate font-semibold">{{ t("adminTitle") }}</h1>
        <p class="hidden truncate text-xs text-zinc-500 sm:block">{{ t("adminWorkspaceHint") }}</p>
      </div>
      <button class="sidebar-action" @click="switchLocale"><Languages :size="17" />{{ locale.toUpperCase() }}</button>
      <button class="sidebar-action" @click="logout"><LogOut :size="17" /><span class="hidden sm:inline">{{ t("signOut") }}</span></button>
    </header>

    <div class="min-h-0 flex flex-1 flex-col md:flex-row">
      <aside class="shrink-0 border-b border-line bg-white p-3 md:w-72 md:border-b-0 md:border-r">
        <div class="mb-3 flex items-center gap-2 text-sm font-semibold"><Users :size="17" />{{ t("managedUsers") }}</div>
        <select
          class="input md:hidden"
          :value="selected?.id ?? ''"
          :aria-label="t('selectWorkspace')"
          @change="selectById(($event.target as HTMLSelectElement).value)"
        >
          <option v-for="item in users" :key="item.id" :value="item.id">{{ item.agent_name }} · {{ item.username }}</option>
        </select>
        <nav class="hidden space-y-1 md:block" :aria-label="t('managedUsers')">
          <button
            v-for="item in users"
            :key="item.id"
            :class="['w-full px-3 py-2.5 text-left text-sm transition', selected?.id === item.id ? 'bg-soft-blue' : 'hover:bg-zinc-100']"
            @click="selected = item"
          >
            <strong class="block truncate">{{ item.agent_name }}</strong>
            <span class="block truncate text-xs text-zinc-500">{{ item.username }} · {{ item.agent_id }}</span>
          </button>
        </nav>
      </aside>

      <p v-if="error" class="m-4 border border-red-200 bg-red-50 p-4 text-sm text-red-800">{{ error }}</p>
      <section v-else-if="selected" class="flex min-h-0 flex-1 flex-col overflow-hidden">
        <nav class="flex h-12 shrink-0 items-stretch border-b border-line bg-white px-3 sm:px-5" :aria-label="t('adminSections')">
          <button
            type="button"
            :class="['flex items-center gap-2 border-b-2 px-3 text-sm font-medium transition', section === 'files' ? 'border-accent text-ink' : 'border-transparent text-zinc-500 hover:text-ink']"
            @click="section = 'files'"
          >
            <Files :size="16" />{{ t("files") }}
          </button>
          <button
            type="button"
            :class="['flex items-center gap-2 border-b-2 px-3 text-sm font-medium transition', section === 'chats' ? 'border-accent text-ink' : 'border-transparent text-zinc-500 hover:text-ink']"
            @click="section = 'chats'"
          >
            <MessageSquareText :size="16" />{{ t("conversations") }}
          </button>
        </nav>
        <AdminFileBrowser v-if="section === 'files'" :managed-user="selected" />
        <AdminConversationBrowser v-else :managed-user="selected" />
      </section>
      <div v-else class="grid flex-1 place-items-center p-6 text-center text-sm text-zinc-500">{{ t("noManagedUsers") }}</div>
    </div>
  </main>
</template>
