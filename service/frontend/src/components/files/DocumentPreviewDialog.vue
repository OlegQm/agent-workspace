<script setup lang="ts">
import { ArrowLeft, ArrowRight, FileImage, FileText, Maximize2, Minimize2, Minus, Plus, ShieldAlert, X } from "lucide-vue-next"
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import type { CSSProperties } from "vue"

import { api, type DocumentPreview, type DocxParagraphBlock, type ExcelBorder, type ExcelCell, type ExcelCellStyle, type FileEntry } from "../../api"
import { useWorkspaceContext } from "../../composables/useWorkspace"
import { excelMergedRanges, excelRowOffsets, excelVisibleWindow } from "../../lib/excelVirtualization"
import DocxParagraph from "./DocxParagraph.vue"

const props = defineProps<{
  entry: FileEntry
  adminUserId?: string
}>()
const emit = defineEmits<{ close: [] }>()
const { t } = useWorkspaceContext()
const preview = ref<DocumentPreview | null>(null)
const loading = ref(true)
const error = ref("")
const pdfPage = ref(1)
const pdfZoom = ref(100)
const dialogElement = ref<HTMLElement | null>(null)
const fullscreenSupported = ref(false)
const isFullscreen = ref(false)
const excelViewport = ref<HTMLElement | null>(null)
const excelScrollTop = ref(0)
const excelViewportHeight = ref(600)
const prefetchedPdfPages = new Map<number, HTMLImageElement>()

function pdfPageUrlFor(page: number) {
  return props.adminUserId
    ? api.adminPdfPageUrl(props.adminUserId, props.entry.path, page)
    : api.pdfPageUrl(props.entry.path, page)
}

const pdfPageUrl = computed(() => preview.value?.kind === "pdf" ? pdfPageUrlFor(pdfPage.value) : "")
const imagePreviewUrl = computed(() => props.adminUserId
  ? api.adminImagePreviewUrl(props.adminUserId, props.entry.path)
  : api.imagePreviewUrl(props.entry.path))
const pdfPageSize = computed(() => preview.value?.kind === "pdf" ? preview.value.pages[pdfPage.value - 1] : null)
const pdfPageStyle = computed<CSSProperties>(() => {
  const size = pdfPageSize.value
  if (!size) return {}
  const width = size.width * 96 / 72 * pdfZoom.value / 100
  return { width: `${width}px`, maxWidth: pdfZoom.value <= 100 ? "100%" : "none" }
})
const docxPageStyle = computed<CSSProperties>(() => {
  if (preview.value?.kind !== "docx") return {}
  const page = preview.value.page
  return {
    width: page.width ? `${page.width}px` : undefined,
    minHeight: page.height ? `${page.height}px` : undefined,
    "--doc-margin-top": `${page.margin_top ?? 64}px`,
    "--doc-margin-right": `${page.margin_right ?? 72}px`,
    "--doc-margin-bottom": `${page.margin_bottom ?? 64}px`,
    "--doc-margin-left": `${page.margin_left ?? 72}px`,
  } as CSSProperties
})
const excelOffsets = computed(() => preview.value?.kind === "xlsx"
  ? excelRowOffsets(preview.value.row_heights)
  : [0])
const excelMerges = computed(() => preview.value?.kind === "xlsx"
  ? excelMergedRanges(preview.value.rows)
  : [])
const excelWindow = computed(() => excelVisibleWindow(
  excelOffsets.value,
  excelMerges.value,
  excelScrollTop.value,
  excelViewportHeight.value,
))
const excelVisibleRows = computed(() => preview.value?.kind === "xlsx"
  ? preview.value.rows
    .slice(excelWindow.value.start, excelWindow.value.end)
    .map((row, offset) => ({ row, rowIndex: excelWindow.value.start + offset }))
  : [])

function changePdfZoom(delta: number) {
  pdfZoom.value = Math.min(200, Math.max(50, pdfZoom.value + delta))
}

function prefetchPdfPage(page: number) {
  if (preview.value?.kind !== "pdf" || page < 1 || page > preview.value.page_count) return
  if (prefetchedPdfPages.has(page)) return
  const image = new Image()
  image.src = pdfPageUrlFor(page)
  prefetchedPdfPages.set(page, image)
}

function syncExcelViewport() {
  if (!excelViewport.value) return
  excelScrollTop.value = excelViewport.value.scrollTop
  excelViewportHeight.value = excelViewport.value.clientHeight || 600
}

function handleExcelScroll(event: Event) {
  const target = event.currentTarget as HTMLElement
  excelScrollTop.value = target.scrollTop
  excelViewportHeight.value = target.clientHeight || 600
}

function docxListMarker(index: number, block: DocxParagraphBlock) {
  if (block.list_kind === "bullet") return "•"
  if (block.list_kind !== "number" || preview.value?.kind !== "docx") return ""
  let number = 1
  for (let current = index - 1; current >= 0; current--) {
    const previous = preview.value.blocks[current]
    if (previous.type !== "paragraph" || previous.list_kind !== "number" || previous.list_level !== block.list_level) break
    number++
  }
  return `${number}.`
}

function blockProtectedNavigation(event: MouseEvent) {
  if (!props.entry.no_user_access || props.adminUserId) return
  const target = event.target
  if (target instanceof Element && target.closest("a")) event.preventDefault()
}

async function loadPreview(sheet?: string) {
  loading.value = true
  error.value = ""
  try {
    preview.value = props.adminUserId
      ? await api.adminPreview(props.adminUserId, props.entry.path, sheet)
      : await api.preview(props.entry.path, sheet)
    excelScrollTop.value = 0
    await nextTick()
    if (excelViewport.value) excelViewport.value.scrollTop = 0
    syncExcelViewport()
    if (preview.value.kind === "pdf") prefetchPdfPage(2)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause)
  } finally {
    loading.value = false
  }
}

function blockProtectedCopy(event: Event) {
  if (props.entry.no_user_access && !props.adminUserId) event.preventDefault()
}

function handleImageError() {
  error.value = t.value("previewUnavailable")
}

function syncFullscreenState() {
  isFullscreen.value = document.fullscreenElement === dialogElement.value
}

async function toggleFullscreen() {
  if (!dialogElement.value || !fullscreenSupported.value) return
  try {
    if (document.fullscreenElement === dialogElement.value) {
      await document.exitFullscreen()
    } else {
      await dialogElement.value.requestFullscreen()
    }
  } catch {
    fullscreenSupported.value = false
  }
}

async function closePreview() {
  if (document.fullscreenElement === dialogElement.value) await document.exitFullscreen()
  emit("close")
}

function excelColumnLabel(index: number) {
  let value = index + 1
  let label = ""
  while (value > 0) {
    value--
    label = String.fromCharCode(65 + (value % 26)) + label
    value = Math.floor(value / 26)
  }
  return label
}

function excelBorder(border?: ExcelBorder | null) {
  if (!border) return undefined
  const width = ["medium", "mediumDashed", "mediumDashDot", "mediumDashDotDot"].includes(border.style)
    ? 2
    : ["thick", "double"].includes(border.style) ? 3 : 1
  const lineStyle = border.style === "double"
    ? "double"
    : border.style.toLowerCase().includes("dash") ? "dashed"
      : border.style.toLowerCase().includes("dot") || border.style === "dotted" ? "dotted" : "solid"
  return `${width}px ${lineStyle} ${border.color}`
}

function excelCellStyle(cell: ExcelCell, styles: ExcelCellStyle[]): CSSProperties {
  const style = styles[cell.style_id] ?? {}
  const numeric = typeof cell.value === "number"
  const horizontal = style.horizontal === "centerContinuous" ? "center" : style.horizontal
  const textAlign = horizontal && ["left", "right", "center", "justify"].includes(horizontal)
    ? horizontal as CSSProperties["textAlign"]
    : numeric ? "right" : "left"
  return {
    backgroundColor: style.fill_color ?? "#ffffff",
    color: style.font_color ?? "#1f1f1f",
    fontSize: style.font_size ? `${style.font_size * 4 / 3}px` : undefined,
    fontWeight: style.bold ? "700" : "400",
    fontStyle: style.italic ? "italic" : "normal",
    textDecoration: style.underline ? "underline" : undefined,
    textAlign,
    verticalAlign: style.vertical === "top" ? "top" : style.vertical === "bottom" ? "bottom" : "middle",
    whiteSpace: style.wrap_text ? "pre-wrap" : "nowrap",
    paddingLeft: `${8 + (style.indent ?? 0) * 12}px`,
    borderLeft: excelBorder(style.border_left),
    borderRight: excelBorder(style.border_right),
    borderTop: excelBorder(style.border_top),
    borderBottom: excelBorder(style.border_bottom),
  }
}

watch(() => props.entry.path, () => {
  pdfPage.value = 1
  pdfZoom.value = 100
  prefetchedPdfPages.clear()
  void loadPreview()
})

watch(pdfPage, (page) => prefetchPdfPage(page + 1))

onMounted(() => {
  fullscreenSupported.value = Boolean(document.fullscreenEnabled && dialogElement.value?.requestFullscreen)
  document.addEventListener("fullscreenchange", syncFullscreenState)
  void loadPreview()
})

onBeforeUnmount(() => document.removeEventListener("fullscreenchange", syncFullscreenState))
</script>

<template>
  <Teleport to="body">
    <div
      ref="dialogElement"
      class="fixed inset-0 z-50 flex flex-col bg-paper"
      role="dialog"
      aria-modal="true"
      :aria-label="`${t('readOnlyPreview')}: ${entry.name}`"
      @copy="blockProtectedCopy"
      @cut="blockProtectedCopy"
      @contextmenu="blockProtectedCopy"
      @click="blockProtectedNavigation"
    >
    <header class="flex min-h-16 shrink-0 items-center gap-3 border-b border-line bg-white px-4 sm:px-6">
      <FileImage v-if="entry.preview_kind === 'image'" :size="20" class="shrink-0 text-accent" />
      <FileText v-else :size="20" class="shrink-0 text-accent" />
      <div class="min-w-0 flex-1">
        <h2 class="truncate font-semibold">{{ entry.name }}</h2>
        <p class="text-xs text-zinc-500">{{ t("readOnlyPreview") }}</p>
      </div>
      <button
        class="icon-button"
        :disabled="!fullscreenSupported"
        :aria-label="isFullscreen ? t('exitFullScreen') : t('fullScreen')"
        :title="isFullscreen ? t('exitFullScreen') : t('fullScreen')"
        @click="toggleFullscreen"
      >
        <Minimize2 v-if="isFullscreen" :size="20" />
        <Maximize2 v-else :size="20" />
      </button>
      <button class="icon-button" :aria-label="t('close')" @click="closePreview"><X :size="20" /></button>
    </header>

    <div
      v-if="entry.no_user_access && !adminUserId"
      class="flex shrink-0 items-start gap-3 border-b border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950 sm:px-6"
    >
      <ShieldAlert :size="19" class="mt-0.5 shrink-0" />
      <span>{{ t("protectedPreview") }}</span>
    </div>

    <main
      :class="[
        'min-h-0 min-w-0 w-full max-w-full flex-1',
        ['pdf', 'docx', 'txt', 'image'].includes(preview?.kind ?? '') ? 'bg-[#e7e9e6] p-0' : 'p-3 sm:p-5',
        preview?.kind === 'xlsx' && !loading && !error ? 'overflow-hidden' : 'overflow-auto',
        entry.no_user_access && !adminUserId ? 'select-none' : '',
      ]"
    >
      <div v-if="loading" class="grid min-h-64 place-items-center text-sm text-zinc-500">{{ t("running") }}</div>
      <div v-else-if="error" class="mx-auto max-w-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{{ error }}</div>

      <section v-else-if="preview?.kind === 'pdf'" class="min-h-full">
        <div class="sticky top-0 z-10 flex min-h-14 items-center justify-center gap-1 border-b border-line bg-white/95 px-2 shadow-sm backdrop-blur sm:gap-2">
          <button class="icon-button rounded-md border border-line" :disabled="pdfPage <= 1" :aria-label="t('previous')" @click="pdfPage--">
            <ArrowLeft :size="17" />
          </button>
          <span class="min-w-20 px-1 text-center text-sm tabular-nums">{{ pdfPage }} / {{ preview.page_count }}</span>
          <button class="icon-button rounded-md border border-line" :disabled="pdfPage >= preview.page_count" :aria-label="t('next')" @click="pdfPage++">
            <ArrowRight :size="17" />
          </button>
          <span class="mx-1 h-6 w-px bg-line sm:mx-2" />
          <button class="icon-button rounded-md" :disabled="pdfZoom <= 50" :aria-label="t('zoomOut')" @click="changePdfZoom(-10)">
            <Minus :size="18" />
          </button>
          <button class="min-w-14 px-1 text-center text-xs tabular-nums text-zinc-600" :title="t('resetZoom')" @click="pdfZoom = 100">
            {{ pdfZoom }}%
          </button>
          <button class="icon-button rounded-md" :disabled="pdfZoom >= 200" :aria-label="t('zoomIn')" @click="changePdfZoom(10)">
            <Plus :size="18" />
          </button>
        </div>
        <div class="flex min-h-[calc(100vh-7.5rem)] min-w-max items-start justify-center p-4 sm:p-8">
          <img
            :src="pdfPageUrl"
            :alt="`${entry.name}, ${t('page')} ${pdfPage}`"
            :style="pdfPageStyle"
            class="block h-auto bg-white shadow-[0_3px_18px_rgba(0,0,0,0.2)]"
            draggable="false"
          />
        </div>
      </section>

      <section v-else-if="preview?.kind === 'xlsx'" class="flex h-full min-h-0 flex-col border border-[#b7b7b7] bg-white shadow-panel">
        <div
          ref="excelViewport"
          data-testid="excel-scroll-region"
          class="min-h-0 flex-1 overflow-auto bg-[#f3f3f3]"
          @scroll.passive="handleExcelScroll"
        >
          <table class="border-separate border-spacing-0 font-[Calibri,Aptos,Arial,sans-serif] text-[14px] leading-normal">
            <colgroup>
              <col class="w-12" />
              <col
                v-for="(width, columnIndex) in preview.column_widths"
                :key="columnIndex"
                :style="{ width: `${width}px`, minWidth: `${width}px`, maxWidth: `${width}px` }"
              />
            </colgroup>
            <thead>
              <tr class="h-7">
                <th class="sticky left-0 top-0 z-30 min-w-12 border-b border-r border-[#b7b7b7] bg-[#e6e6e6]" />
                <th
                  v-for="(_, columnIndex) in preview.column_widths"
                  :key="columnIndex"
                  class="sticky top-0 z-20 border-b border-r border-[#b7b7b7] bg-[#e6e6e6] px-1 text-center text-xs font-normal text-[#555]"
                >
                  {{ excelColumnLabel(columnIndex) }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="excelWindow.top > 0" aria-hidden="true">
                <td :colspan="preview.column_widths.length + 1" class="border-0 p-0" :style="{ height: `${excelWindow.top}px` }" />
              </tr>
              <tr
                v-for="({ row, rowIndex }) in excelVisibleRows"
                :key="rowIndex"
                :style="{ height: `${preview.row_heights[rowIndex] ?? 20}px` }"
              >
                <th class="sticky left-0 z-10 min-w-12 border-b border-r border-[#b7b7b7] bg-[#e6e6e6] px-2 text-right text-xs font-normal text-[#666]">
                  {{ rowIndex + 1 }}
                </th>
                <template v-for="(cell, columnIndex) in row" :key="columnIndex">
                  <td
                    v-if="cell"
                    :colspan="cell.column_span"
                    :rowspan="cell.row_span"
                    :style="excelCellStyle(cell, preview.styles)"
                    :class="[
                      'overflow-hidden px-2 py-0.5',
                      preview.show_gridlines ? 'border-b border-r border-[#d9d9d9]' : '',
                    ]"
                  >
                    {{ cell.display }}
                  </td>
                </template>
              </tr>
              <tr v-if="excelWindow.bottom > 0" aria-hidden="true">
                <td :colspan="preview.column_widths.length + 1" class="border-0 p-0" :style="{ height: `${excelWindow.bottom}px` }" />
              </tr>
            </tbody>
          </table>
        </div>
        <div class="flex min-h-10 shrink-0 items-end gap-0 overflow-x-auto border-t border-[#b7b7b7] bg-[#f3f3f3] px-2 pt-1">
          <button
            v-for="sheetName in preview.sheets"
            :key="sheetName"
            class="h-9 shrink-0 border-x border-t px-4 text-sm transition"
            :class="sheetName === preview.sheet
              ? 'border-[#b7b7b7] border-b-white bg-white font-medium text-accent'
              : 'border-transparent text-zinc-600 hover:bg-white'"
            @click="sheetName !== preview.sheet && loadPreview(sheetName)"
          >
            {{ sheetName }}
          </button>
        </div>
        <p v-if="preview.truncated" class="shrink-0 border-t border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">{{ t("previewTruncated") }}</p>
      </section>

      <section v-else-if="preview?.kind === 'docx'" class="min-h-full overflow-x-auto p-3 sm:p-8">
        <article
          :style="docxPageStyle"
          class="docx-page mx-auto max-w-full border border-zinc-300 bg-white font-[Calibri,Aptos,Arial,sans-serif] text-[11pt] leading-[1.45] text-[#202020] shadow-[0_3px_18px_rgba(0,0,0,0.18)]"
        >
          <template v-for="(block, index) in preview.blocks" :key="index">
            <table v-if="block.type === 'table'" class="docx-block docx-block-table my-4 w-full table-fixed border-collapse text-[10.5pt]">
              <colgroup>
                <col
                  v-for="(width, columnIndex) in block.column_widths"
                  :key="columnIndex"
                  :style="width ? { width: `${width}px` } : undefined"
                />
              </colgroup>
              <tbody>
              <tr v-for="(row, rowIndex) in block.rows" :key="rowIndex">
                  <component
                    :is="block.header_row && rowIndex === 0 ? 'th' : 'td'"
                    v-for="(cell, cellIndex) in row"
                    :key="cellIndex"
                    class="border border-zinc-400 p-2 text-left align-top whitespace-pre-wrap"
                    :class="block.header_row && rowIndex === 0 ? 'bg-zinc-100 font-semibold' : 'font-normal'"
                    :style="{
                      backgroundColor: cell.fill_color ?? undefined,
                      verticalAlign: cell.vertical_alignment ?? undefined,
                    }"
                  >
                    <DocxParagraph
                      v-for="(paragraph, paragraphIndex) in cell.paragraphs"
                      :key="paragraphIndex"
                      :block="paragraph"
                      compact
                    />
                  </component>
                </tr>
              </tbody>
            </table>
            <DocxParagraph
              v-else
              class="docx-block"
              :block="block"
              :marker="docxListMarker(index, block)"
            />
          </template>
          <p v-if="preview.truncated" class="mt-6 border-t border-line pt-4 text-sm text-amber-800">{{ t("previewTruncated") }}</p>
        </article>
      </section>

      <section v-else-if="preview?.kind === 'txt'" class="min-h-full p-3 sm:p-8">
        <article class="mx-auto min-h-[calc(100vh-8rem)] w-full max-w-5xl border border-zinc-300 bg-white p-4 shadow-[0_3px_18px_rgba(0,0,0,0.14)] sm:p-8">
          <pre
            data-testid="text-preview"
            class="m-0 whitespace-pre-wrap break-words font-mono text-[13px] leading-6 text-zinc-800 [overflow-wrap:anywhere] sm:text-sm"
          >{{ preview.content }}</pre>
          <p v-if="preview.truncated" class="mt-6 border-t border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">{{ t("previewTruncated") }}</p>
        </article>
      </section>

      <section v-else-if="preview?.kind === 'image'" class="flex min-h-full items-center justify-center p-3 sm:p-8">
        <img
          :src="imagePreviewUrl"
          :alt="entry.name"
          :width="preview.width"
          :height="preview.height"
          class="block h-auto max-h-[calc(100vh-8rem)] max-w-full object-contain bg-white shadow-[0_3px_18px_rgba(0,0,0,0.2)]"
          draggable="false"
          @error="handleImageError"
        />
      </section>
    </main>
    </div>
  </Teleport>
</template>

<style scoped>
.docx-page {
  padding-top: min(var(--doc-margin-top), 10vw);
  padding-right: min(var(--doc-margin-right), 10vw);
  padding-bottom: min(var(--doc-margin-bottom), 10vw);
  padding-left: min(var(--doc-margin-left), 10vw);
}

.docx-block {
  content-visibility: auto;
  contain-intrinsic-size: auto 32px;
}

.docx-block-table {
  contain-intrinsic-size: auto 160px;
}

@media (max-width: 639px) {
  .docx-page {
    min-height: auto !important;
    padding-top: min(var(--doc-margin-top), 7vw);
    padding-right: min(var(--doc-margin-right), 7vw);
    padding-bottom: min(var(--doc-margin-bottom), 7vw);
    padding-left: min(var(--doc-margin-left), 7vw);
  }
}
</style>
