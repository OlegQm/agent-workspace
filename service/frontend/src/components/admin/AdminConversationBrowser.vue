<script setup lang="ts">
import { ref, watch } from "vue"

import { api, type AdminManagedUser, type Conversation, type ConversationDetail } from "../../api"
import AdminConversationList from "./AdminConversationList.vue"
import AdminConversationViewer from "./AdminConversationViewer.vue"

const props = defineProps<{ managedUser: AdminManagedUser }>()

const conversations = ref<Conversation[]>([])
const selectedId = ref<string | null>(null)
const detail = ref<ConversationDetail | null>(null)
const listLoading = ref(false)
const detailLoading = ref(false)
const error = ref("")
let requestVersion = 0

async function loadConversations(): Promise<void> {
  const version = ++requestVersion
  listLoading.value = true
  error.value = ""
  selectedId.value = null
  detail.value = null
  try {
    const response = await api.adminConversations(props.managedUser.id)
    if (version === requestVersion) conversations.value = response
  } catch (cause) {
    if (version === requestVersion) error.value = cause instanceof Error ? cause.message : String(cause)
  } finally {
    if (version === requestVersion) listLoading.value = false
  }
}

async function selectConversation(conversation: Conversation): Promise<void> {
  const version = ++requestVersion
  selectedId.value = conversation.id
  detail.value = null
  detailLoading.value = true
  error.value = ""
  try {
    const response = await api.adminConversation(props.managedUser.id, conversation.id)
    if (version === requestVersion) detail.value = response
  } catch (cause) {
    if (version === requestVersion) error.value = cause instanceof Error ? cause.message : String(cause)
  } finally {
    if (version === requestVersion) detailLoading.value = false
  }
}

function closeConversation(): void {
  requestVersion += 1
  selectedId.value = null
  detail.value = null
  detailLoading.value = false
}

watch(() => props.managedUser.id, () => {
  conversations.value = []
  void loadConversations()
}, { immediate: true })
</script>

<template>
  <section class="relative flex min-h-0 flex-1 overflow-hidden">
    <p v-if="error" class="absolute inset-x-3 top-3 z-10 border border-red-200 bg-red-50 p-3 text-sm text-red-800" role="alert">{{ error }}</p>
    <AdminConversationList
      :class="[selectedId ? 'hidden' : 'flex', 'lg:flex lg:w-[min(21rem,34%)] lg:flex-none']"
      :conversations="conversations"
      :selected-id="selectedId"
      :loading="listLoading"
      @select="selectConversation"
    />
    <AdminConversationViewer
      :class="[selectedId ? 'flex' : 'hidden', 'lg:flex']"
      :conversation="detail"
      :export-href="selectedId ? api.adminConversationExportUrl(managedUser.id, selectedId) : undefined"
      :loading="detailLoading"
      @back="closeConversation"
    />
  </section>
</template>
