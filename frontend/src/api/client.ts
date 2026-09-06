export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

function csrfToken(): string | undefined {
  return document.cookie
    .split("; ")
    .find((cookie) => cookie.startsWith("music_rounds_session_csrf="))
    ?.split("=", 2)[1];
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const token = csrfToken();
  if (token) headers.set("X-CSRF-Token", decodeURIComponent(token));
  if (init?.method && init.method !== "GET") {
    if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    credentials: "include",
    headers,
  });
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => undefined);
    const detail = typeof body === "object" && body !== null && "detail" in body
      ? String(body.detail)
      : `Request failed (${response.status})`;
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function post<T>(path: string, payload: unknown): Promise<T> {
  return api<T>(path, { method: "POST", body: JSON.stringify(payload) });
}

export function patch<T>(path: string, payload: unknown): Promise<T> {
  return api<T>(path, { method: "PATCH", body: JSON.stringify(payload) });
}

export function put(path: string, payload: unknown): Promise<void> {
  return api<void>(path, { method: "PUT", body: JSON.stringify(payload) });
}

export function del(path: string): Promise<void> {
  return api<void>(path, { method: "DELETE" });
}

/** End the server-side session, then let the identity provider finish logout. */
export async function logout(): Promise<string> {
  const headers = new Headers();
  const token = csrfToken();
  if (token) headers.set("X-CSRF-Token", decodeURIComponent(token));
  const response = await fetch("/api/v1/auth/logout", {
    method: "POST",
    credentials: "include",
    headers,
  });
  if (!response.ok) throw new ApiError(response.status, "Could not sign out");
  return response.headers.get("X-Logout-Redirect") ?? "/signed-out";
}
