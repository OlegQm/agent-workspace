<script setup lang="ts">
import { computed } from "vue"
import type { CSSProperties } from "vue"

import type { DocxParagraphBlock, DocxRun } from "../../api"

const props = withDefaults(defineProps<{
  block: DocxParagraphBlock
  marker?: string
  compact?: boolean
}>(), {
  marker: "",
  compact: false,
})

const paragraphStyle = computed<CSSProperties>(() => ({
  textAlign: props.block.alignment ?? undefined,
  marginTop: props.block.space_before ? `${props.block.space_before}px` : undefined,
  marginBottom: props.block.space_after ? `${props.block.space_after}px` : undefined,
  marginLeft: props.block.left_indent ? `${props.block.left_indent}px` : undefined,
  marginRight: props.block.right_indent ? `${props.block.right_indent}px` : undefined,
  textIndent: props.block.first_line_indent ? `${props.block.first_line_indent}px` : undefined,
  lineHeight: props.block.line_spacing_pixels
    ? `${props.block.line_spacing_pixels}px`
    : props.block.line_spacing_multiple ?? undefined,
  paddingLeft: props.block.list_level ? `${props.block.list_level * 20}px` : undefined,
}))

const paragraphClasses = computed(() => [
  "docx-paragraph relative min-h-[1.45em] whitespace-pre-wrap break-words",
  props.block.style?.startsWith("Title") ? "mb-5 text-[24pt] font-semibold leading-tight" : "",
  props.block.style?.startsWith("Subtitle") ? "mb-4 text-[15pt] text-zinc-600" : "",
  props.block.style?.startsWith("Heading 1") ? "mb-3 mt-6 text-[18pt] font-semibold leading-tight" : "",
  props.block.style?.startsWith("Heading 2") ? "mb-2 mt-5 text-[15pt] font-semibold leading-tight" : "",
  props.block.style?.startsWith("Heading 3") ? "mb-2 mt-4 text-[12pt] font-semibold" : "",
  !props.block.style?.startsWith("Heading")
    && !props.block.style?.startsWith("Title")
    && !props.block.style?.startsWith("Subtitle")
    ? props.compact ? "my-0.5" : "my-1.5"
    : "",
  props.block.list_kind ? "pl-6" : "",
])

function runStyle(run: DocxRun): CSSProperties {
  const decorations = [run.underline ? "underline" : "", run.strike ? "line-through" : ""]
    .filter(Boolean)
    .join(" ")
  return {
    fontWeight: run.bold ? "700" : undefined,
    fontStyle: run.italic ? "italic" : undefined,
    textDecoration: decorations || undefined,
    fontSize: run.font_size ? `${run.font_size}pt` : undefined,
    color: run.font_color ?? undefined,
    fontFamily: run.font_name ? `"${run.font_name}", inherit` : undefined,
    backgroundColor: run.highlight_color ?? undefined,
    verticalAlign: run.superscript ? "super" : run.subscript ? "sub" : undefined,
  }
}
</script>

<template>
  <div :style="paragraphStyle" :class="paragraphClasses">
    <span v-if="block.list_kind" class="absolute left-0 w-5 text-right">{{ marker || (block.list_kind === "bullet" ? "•" : "1.") }}</span>
    <template v-if="block.runs.length">
      <template v-for="(run, index) in block.runs" :key="index">
        <a
          v-if="run.href"
          :href="run.href"
          :style="runStyle(run)"
          class="text-[#0563c1] underline decoration-[#0563c1] underline-offset-2 hover:text-[#034f9b]"
          target="_blank"
          rel="noopener noreferrer"
        >{{ run.text }}</a>
        <span v-else :style="runStyle(run)">{{ run.text }}</span>
      </template>
    </template>
    <template v-else>{{ block.text || "\u00a0" }}</template>
  </div>
</template>
