import { ApiError } from "../api"
import type { Translate } from "../i18n"

const previewableExtensions = new Set(["docx", "pdf", "xlsx"])

export function hasBuiltInPreview(filename: string): boolean {
  const extension = filename.split(".").pop()?.toLowerCase() ?? ""
  return previewableExtensions.has(extension)
}

export function uploadResultNotice(files: Array<Pick<File, "name">>, t: Translate): string {
  const withoutPreview = files.filter((file) => !hasBuiltInPreview(file.name))
  if (!withoutPreview.length) return t("uploadComplete")
  return `${t("uploadNoPreview")} ${withoutPreview.map((file) => file.name).join(", ")}`
}

export function fileOperationError(cause: unknown, t: Translate): string {
  if (cause instanceof ApiError) {
    if (cause.status === 403) return t("uploadProtected")
    if (cause.status === 409) return t("fileAlreadyExists")
    if (cause.status === 413) return t("uploadTooLarge")
    if (cause.status === 400 || cause.status === 422) {
      return `${t("uploadInvalid")}: ${cause.message}`
    }
    return cause.message || t("uploadFailed")
  }
  return cause instanceof Error ? cause.message : t("uploadFailed")
}
