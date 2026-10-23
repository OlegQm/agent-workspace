import type { ExcelCell } from "../api"

export type ExcelRowWindow = {
  start: number
  end: number
  top: number
  bottom: number
}

export type ExcelMergedRange = {
  start: number
  end: number
}

/** Build cumulative row offsets from the worksheet's declared row heights. */
export function excelRowOffsets(rowHeights: number[]): number[] {
  const offsets = [0]
  for (const height of rowHeights) offsets.push(offsets[offsets.length - 1] + height)
  return offsets
}

/** Extract vertical merged-cell ranges that must remain in one render window. */
export function excelMergedRanges(rows: (ExcelCell | null)[][]): ExcelMergedRange[] {
  const ranges: ExcelMergedRange[] = []
  rows.forEach((row, rowIndex) => {
    for (const cell of row) {
      if (cell && cell.row_span > 1) {
        ranges.push({ start: rowIndex, end: Math.min(rows.length, rowIndex + cell.row_span) })
      }
    }
  })
  return ranges
}

/** Find the row containing a vertical pixel offset using cumulative heights. */
function rowAtOffset(offsets: number[], value: number): number {
  let low = 0
  let high = Math.max(0, offsets.length - 2)
  while (low < high) {
    const middle = Math.floor((low + high + 1) / 2)
    if (offsets[middle] <= value) low = middle
    else high = middle - 1
  }
  return low
}

/** Calculate a bounded render window while retaining intersecting merged rows. */
export function excelVisibleWindow(
  offsets: number[],
  mergedRanges: ExcelMergedRange[],
  scrollTop: number,
  viewportHeight: number,
  overscanPixels = 320,
): ExcelRowWindow {
  const rowCount = Math.max(0, offsets.length - 1)
  if (!rowCount) return { start: 0, end: 0, top: 0, bottom: 0 }
  const total = offsets[rowCount]
  let start = rowAtOffset(offsets, Math.max(0, scrollTop - overscanPixels))
  let end = Math.min(
    rowCount,
    rowAtOffset(offsets, Math.min(total, scrollTop + viewportHeight + overscanPixels)) + 1,
  )

  let changed = true
  while (changed) {
    changed = false
    for (const range of mergedRanges) {
      if (range.start < end && range.end > start) {
        const expandedStart = Math.min(start, range.start)
        const expandedEnd = Math.max(end, range.end)
        if (expandedStart !== start || expandedEnd !== end) {
          start = expandedStart
          end = Math.min(rowCount, expandedEnd)
          changed = true
        }
      }
    }
  }
  return {
    start,
    end,
    top: offsets[start],
    bottom: Math.max(0, total - offsets[end]),
  }
}
