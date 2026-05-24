export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(path, {
    headers: { Accept: "application/json" },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const message =
      typeof data?.error === "string" ? data.error : `HTTP ${res.status}`;
    throw new Error(message);
  }
  return data as T;
}

export async function apiPost<T>(
  path: string,
  body: Record<string, unknown> = {}
): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const message =
      typeof data?.error === "string" ? data.error : `HTTP ${res.status}`;
    throw new Error(message);
  }
  return data as T;
}
