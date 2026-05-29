const TOKEN_KEY = "btb_token"
const COOKIE_MAX_AGE = 7 * 24 * 60 * 60

export interface UserInfo {
  id: string
  email: string
  full_name: string
  plan: string
  pages_limit: number
  pages_used_this_month: number
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return
  localStorage.setItem(TOKEN_KEY, token)
  document.cookie = `${TOKEN_KEY}=${token}; path=/; max-age=${COOKIE_MAX_AGE}; SameSite=Lax`
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null
  return localStorage.getItem(TOKEN_KEY)
}

export function logout(): void {
  if (typeof window === "undefined") return
  localStorage.removeItem(TOKEN_KEY)
  document.cookie = `${TOKEN_KEY}=; path=/; max-age=0`
}

export function isLoggedIn(): boolean {
  return !!getToken()
}

export function saveUser(user: UserInfo): void {
  if (typeof window === "undefined") return
  localStorage.setItem("btb_user", JSON.stringify(user))
}

export function getUser(): UserInfo | null {
  if (typeof window === "undefined") return null
  const raw = localStorage.getItem("btb_user")
  return raw ? JSON.parse(raw) : null
}
