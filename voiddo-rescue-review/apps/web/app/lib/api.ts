export function apiBase() {
  return process.env.API_INTERNAL_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || "http://api:8080";
}

export async function fetchJson(path: string, forwardedHeaders: Record<string, string> = {}) {
  const headers: Record<string, string> = { ...forwardedHeaders };
  if (path.startsWith("/admin/") && process.env.ADMIN_AUTH_TOKEN) {
    headers["X-Admin-Token"] = process.env.ADMIN_AUTH_TOKEN;
  }
  const response = await fetch(`${apiBase()}${path}`, { cache: "no-store", headers });
  if (!response.ok) {
    return null;
  }
  return response.json();
}

export async function postJson(path: string, body: Record<string, unknown> = {}, forwardedHeaders: Record<string, string> = {}) {
  const headers: Record<string, string> = { "Content-Type": "application/json", ...forwardedHeaders };
  if (path.startsWith("/admin/") && process.env.ADMIN_AUTH_TOKEN) {
    headers["X-Admin-Token"] = process.env.ADMIN_AUTH_TOKEN;
  }
  const response = await fetch(`${apiBase()}${path}`, {
    method: "POST",
    cache: "no-store",
    headers,
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    return null;
  }
  return response.json();
}
