/**
 * Recursively converts all object keys from dash-case to snake_case.
 */
export function normalizeKeys(obj: any): any {
  if (Array.isArray(obj)) {
    return obj.map(normalizeKeys);
  } else if (obj && typeof obj === "object") {
    return Object.fromEntries(
      Object.entries(obj).map(([key, value]) => [
        key.replace(/-/g, "_"),
        normalizeKeys(value),
      ])
    );
  }
  return obj;
}
