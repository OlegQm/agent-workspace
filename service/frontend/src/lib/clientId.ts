/** Create a collision-resistant client-side identifier without requiring a secure context. */
export function createClientId(): string {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID()
  }

  const randomPart = Math.random().toString(36).slice(2)
  return `client-${Date.now().toString(36)}-${randomPart}`
}
