import { describe, expect, it } from "vitest"

import type { ExcelCell } from "../api"
import { excelMergedRanges, excelRowOffsets, excelVisibleWindow } from "./excelVirtualization"

function cell(rowSpan = 1): ExcelCell {
  return { value: "x", display: "x", style_id: 0, row_span: rowSpan, column_span: 1 }
}

describe("Excel row virtualization", () => {
  it("renders only rows near the viewport", () => {
    const offsets = excelRowOffsets(Array.from({ length: 1_000 }, () => 20))
    const window = excelVisibleWindow(offsets, [], 10_000, 600, 200)

    expect(window.start).toBeGreaterThan(400)
    expect(window.end - window.start).toBeLessThan(60)
    expect(window.top + window.bottom).toBeLessThan(20_000)
  })

  it("includes merged row anchors that overlap the viewport", () => {
    const rows: (ExcelCell | null)[][] = Array.from({ length: 20 }, () => [cell()])
    rows[3] = [cell(5)]
    const offsets = excelRowOffsets(Array.from({ length: 20 }, () => 20))
    const ranges = excelMergedRanges(rows)
    const window = excelVisibleWindow(offsets, ranges, 120, 20, 0)

    expect(window.start).toBe(3)
    expect(window.end).toBeGreaterThanOrEqual(8)
  })
})
