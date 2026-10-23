import { describe, expect, it } from "vitest"

import { ApiError } from "../api"
import { translator } from "../i18n"
import {
  fileOperationError,
  hasBuiltInPreview,
  uploadResultNotice,
} from "./fileUpload"

describe("file upload feedback", () => {
  const t = translator("en")

  it("recognizes formats with a built-in preview case-insensitively", () => {
    expect(hasBuiltInPreview("report.PDF")).toBe(true)
    expect(hasBuiltInPreview("report.docx")).toBe(true)
    expect(hasBuiltInPreview("report.xlsx")).toBe(true)
    expect(hasBuiltInPreview("report.csv")).toBe(false)
  })

  it("explains when an uploaded format has no built-in preview", () => {
    expect(uploadResultNotice([{ name: "data.csv" }], t)).toContain(
      "built-in preview is unavailable",
    )
    expect(uploadResultNotice([{ name: "report.xlsx" }], t)).toBe("File uploaded.")
  })

  it("turns protected destination responses into an actionable message", () => {
    expect(fileOperationError(new ApiError("Forbidden", 403), t)).toContain(
      "destination is protected",
    )
  })
})
