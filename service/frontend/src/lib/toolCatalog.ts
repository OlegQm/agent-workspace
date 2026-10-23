import type { Locale } from "../i18n"

export type ToolDescription = {
  id: string
  name: string
  description: string
  examples: string
  category: "reporting" | "marketing" | "operations"
}

type LocalizedTool = Omit<ToolDescription, "id"> & {
  sk: Pick<ToolDescription, "name" | "description" | "examples">
}

const catalog: Record<string, LocalizedTool> = {
  metabase: {
    name: "Metabase",
    description: "Approved dashboards, questions, aggregate analytics, and reports from configured sources.",
    examples: "Explain a chart, check a total, export a report",
    category: "reporting",
    sk: {
      name: "Metabase",
      description: "Schválené dashboardy, otázky, súhrnné analýzy a reporty z nakonfigurovaných zdrojov.",
      examples: "Vysvetlenie grafu, kontrola sumy, export reportu",
    },
  },
  bigquery: {
    name: "BigQuery",
    description: "Run bounded read-only queries against explicitly allowed datasets and export results.",
    examples: "Explore an allowed dataset, compare aggregate results",
    category: "reporting",
    sk: {
      name: "BigQuery",
      description: "Spúšťanie obmedzených dotazov iba na čítanie v povolených dátových súboroch.",
      examples: "Preskúmanie povoleného zdroja, porovnanie súhrnných výsledkov",
    },
  },
  superfaktura: {
    name: "SuperFaktúra",
    description: "Invoices, credit notes, document totals, and recorded payment information in explicitly allowed accounts.",
    examples: "Reconcile invoices, VAT, credit notes, payment records",
    category: "operations",
    sk: {
      name: "SuperFaktúra",
      description: "Faktúry, dobropisy, sumy dokladov a evidované platobné informácie schválených spoločností Open Agent Workspace.",
      examples: "Kontrola faktúr, DPH, dobropisov a platieb",
    },
  },
  clickup: {
    name: "ClickUp",
    description: "Approved projects, tasks, fields, comments, and attachments.",
    examples: "Find a task, review project status, inspect an attachment",
    category: "operations",
    sk: {
      name: "ClickUp",
      description: "Schválené projekty, úlohy, polia, komentáre a prílohy.",
      examples: "Vyhľadanie úlohy, stav projektu, kontrola prílohy",
    },
  },
  code: {
    name: "Open Agent Workspace source code",
    description: "Read-only snapshots of explicitly configured code repositories.",
    examples: "Check a calculation, field, event, or data flow",
    category: "operations",
    sk: {
      name: "Zdrojový kód Open Agent Workspace",
      description: "Kópie nakonfigurovaných repozitárov iba na čítanie.",
      examples: "Kontrola výpočtu, poľa, udalosti alebo toku dát",
    },
  },
  google_ads: {
    name: "Google Ads",
    description: "Approved advertising accounts, campaign settings, spend, clicks, impressions, conversions, and recent change history.",
    examples: "Compare campaigns, spend, conversions, recent changes",
    category: "marketing",
    sk: {
      name: "Google Ads",
      description: "Schválené reklamné účty, nastavenia kampaní, náklady, kliknutia, zobrazenia, konverzie a posledné zmeny.",
      examples: "Porovnanie kampaní, nákladov, konverzií a zmien",
    },
  },
  meta_ads: {
    name: "Meta Ads",
    description: "Approved Meta campaigns, ad sets, ads, creatives, delivery settings, spend, and attributed actions.",
    examples: "Review campaigns, creatives, audiences, and results",
    category: "marketing",
    sk: {
      name: "Meta Ads",
      description: "Schválené Meta kampane, reklamné skupiny, reklamy, kreatívy, nastavenia, náklady a pripísané akcie.",
      examples: "Kontrola kampaní, kreatív, publík a výsledkov",
    },
  },
  google_analytics: {
    name: "Google Analytics",
    description: "Read authorized property analytics, including users, sessions, channels, events, and aggregate reports.",
    examples: "Traffic, users, acquisition channels, event funnels",
    category: "marketing",
    sk: {
      name: "Google Analytics",
      description: "Analýza povolených vlastníctiev vrátane používateľov, relácií, kanálov, udalostí a súhrnných reportov.",
      examples: "Návštevnosť, používatelia, akvizičné kanály a funnely",
    },
  },
}

export function describeTools(toolIds: string[], locale: Locale): ToolDescription[] {
  return toolIds.map((id) => {
    const item = catalog[id]
    if (!item) {
      return {
        id,
        name: id.replace(/_/g, " "),
        description: locale === "sk" ? "Schválený zdroj dát iba na čítanie." : "An approved read-only data source.",
        examples: locale === "sk" ? "Dostupnosť závisí od roly používateľa" : "Availability depends on the user role",
        category: "operations" as const,
      }
    }
    const localized = locale === "sk" ? item.sk : item
    return { id, category: item.category, ...localized }
  })
}
