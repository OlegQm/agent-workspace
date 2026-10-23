import { describe, expect, it } from "vitest"
import { translator } from "./i18n"

describe("translations", () => {
  it("provides English and Slovak workspace labels", () => {
    expect(translator("en")("files")).toBe("Files")
    expect(translator("sk")("files")).toBe("Súbory")
    expect(translator("en")("model")).toBe("Model")
    expect(translator("sk")("model")).toBe("Model")
  })
})
