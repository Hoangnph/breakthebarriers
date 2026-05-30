import { getToken, logout } from "./auth"

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

export async function fetchAPI<T = unknown>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken()
  const isFormData = options.body instanceof FormData
  const headers: Record<string, string> = {
    ...(isFormData ? {} : { "Content-Type": "application/json" }),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers as Record<string, string> ?? {}),
  }

  const res = await fetch(API_URL + path, { ...options, headers })

  if (res.status === 401) {
    logout()
    if (typeof window !== "undefined") window.location.href = "/login"
    throw new ApiError(401, "Not authenticated")
  }
  if (res.status === 402) {
    if (typeof window !== "undefined") window.location.href = "/pricing?reason=quota"
    throw new ApiError(402, "Quota exceeded")
  }
  if (!res.ok) {
    let message = `HTTP ${res.status}`
    try {
      const body = await res.json()
      message = body.detail ?? body.message ?? message
    } catch {
      message = await res.text().catch(() => message)
    }
    throw new ApiError(res.status, message)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}
