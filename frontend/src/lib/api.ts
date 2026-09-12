const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/+$/, "");

export const API_PREFIX = API_BASE.endsWith("/api/v1") ? API_BASE : `${API_BASE}/api/v1`;

export function apiUrl(path: string): string {
  return `${API_PREFIX}/${path.replace(/^\/+/, "")}`;
}
