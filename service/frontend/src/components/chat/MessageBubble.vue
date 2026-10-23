<script setup lang="ts">
import type { Message } from "../../api"
import MarkdownContent from "../common/MarkdownContent.vue"

defineProps<{ message: Message }>()
</script>

<template>
  <article :class="['flex', message.role === 'user' ? 'justify-end' : 'justify-start']">
    <div
      :class="[
        'min-w-0 max-w-[92%] px-4 py-3 text-sm leading-6 sm:max-w-[86%]',
        message.role === 'user' ? 'whitespace-pre-wrap bg-ink text-white' : 'border border-line bg-white',
      ]"
    >
      <MarkdownContent v-if="message.role === 'assistant'" :content="message.content" />
      <template v-else>{{ message.content }}</template>
    </div>
  </article>
</template>
