import { describe, expect, it } from "vitest"
import { describeTools } from "./toolCatalog"

describe("tool catalog copy", () => {
  it("uses generic descriptions for configured business sources", () => {
    const english = describeTools(
      ["metabase", "bigquery", "superfaktura", "clickup", "code", "google_analytics"],
      "en",
    )
    const slovak = describeTools(
      ["metabase", "bigquery", "superfaktura", "clickup", "code", "google_analytics"],
      "sk",
    )

    expect(english[0].description).toContain("configured sources")
    expect(english[1].description).toContain("explicitly allowed datasets")
    expect(english[2].description).toContain("explicitly allowed accounts")
    expect(english[3].description).toBe("Approved projects, tasks, fields, comments, and attachments.")
    expect(english[4].description).toBe("Read-only snapshots of explicitly configured code repositories.")
    expect(english[5].description).toContain("authorized property analytics")
    expect(slovak[0].description).toContain("nakonfigurovaných zdrojov")
    expect(slovak[3].description).toBe("Schválené projekty, úlohy, polia, komentáre a prílohy.")
    expect(slovak[4].description).toBe("Kópie nakonfigurovaných repozitárov iba na čítanie.")
  })
})
