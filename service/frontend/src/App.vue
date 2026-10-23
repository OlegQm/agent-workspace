<script setup lang="ts">
import LoginView from "./components/auth/LoginView.vue"
import AdminShell from "./components/admin/AdminShell.vue"
import WorkspaceShell from "./components/layout/WorkspaceShell.vue"
import { provideWorkspace, useWorkspace } from "./composables/useWorkspace"

const workspace = useWorkspace()
provideWorkspace(workspace)
</script>

<template>
  <LoginView v-if="!workspace.user.value" />
  <AdminShell v-else-if="workspace.user.value.is_admin" />
  <WorkspaceShell v-else />
</template>
