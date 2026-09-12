const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/+$/, "");

export const API_PREFIX = API_BASE.endsWith("/api/v1") ? API_BASE : `${API_BASE}/api/v1`;

export function apiUrl(path: string): string {
  return `${API_PREFIX}/${path.replace(/^\/+/, "")}`;
}

export function responseError(response: Response, fallback = "Yêu cầu thất bại") {
  return response.text().then((body) => {
    let detail = "";
    try {
      const payload = JSON.parse(body) as { detail?: unknown; message?: unknown };
      detail =
        typeof payload.detail === "string"
          ? payload.detail
          : typeof payload.message === "string"
            ? payload.message
            : "";
    } catch {
      detail = body.trim();
    }
    throw new Error(
      detail ? `${fallback} (${response.status}): ${detail}` : `${fallback} (${response.status})`,
    );
  });
}
