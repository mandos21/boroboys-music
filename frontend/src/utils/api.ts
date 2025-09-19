export type FetchOptions<T> = RequestInit & { parse?: (value: unknown) => T };

export async function fetchJson<T>(input: RequestInfo | URL, init?: FetchOptions<T>): Promise<T> {
  const response = await fetch(input, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    ...init,
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || response.statusText);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const data = await response.json();
  return init?.parse ? init.parse(data) : (data as T);
}
