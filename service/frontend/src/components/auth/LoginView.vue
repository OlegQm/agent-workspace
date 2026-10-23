<script setup lang="ts">
import { Bot, Languages } from "lucide-vue-next"

import { useWorkspaceContext } from "../../composables/useWorkspace"

const { locale, login, loginError, loginForm, switchLocale, t } = useWorkspaceContext()
</script>

<template>
  <main class="grid min-h-[100dvh] place-items-center bg-paper p-4 sm:p-8 lg:p-12">
    <section class="w-full max-w-lg border border-line bg-white p-6 shadow-panel sm:p-9 lg:p-10">
      <div class="mb-8 flex items-center gap-3.5 sm:mb-9">
        <div class="grid size-11 place-items-center bg-ink text-white sm:size-12"><Bot :size="23" /></div>
        <div><h1 class="text-xl font-semibold">Open Agent</h1><p class="text-sm text-zinc-500">Workspace</p></div>
      </div>
      <form class="space-y-4" @submit.prevent="login">
        <label class="block text-sm font-medium">
          {{ t("username") }}
          <input v-model="loginForm.username" autocomplete="username" class="input mt-2 h-12" />
        </label>
        <label class="block text-sm font-medium">
          {{ t("password") }}
          <input v-model="loginForm.password" type="password" autocomplete="current-password" class="input mt-2 h-12" />
        </label>
        <p v-if="loginError" class="text-sm text-red-700">{{ loginError }}</p>
        <button class="button-primary w-full" type="submit">{{ t("signIn") }}</button>
      </form>
      <button class="mt-5 flex items-center gap-2 text-sm text-zinc-500 hover:text-ink" @click="switchLocale">
        <Languages :size="16" /> {{ locale === "en" ? "Slovenčina" : "English" }}
      </button>
    </section>
  </main>
</template>
