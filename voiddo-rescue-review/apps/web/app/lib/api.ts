export function apiBase() {
  return process.env.API_INTERNAL_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || "http://api:8080";
}

export async function fetchJson(path: string) {
  const response = await fetch(`${apiBase()}${path}`, { cache: "no-store" });
  if (!response.ok) {
    return null;
  }
  return response.json();
}
