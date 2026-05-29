"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { fetchAPI } from "@/lib/api"
import { setToken, saveUser, UserInfo } from "@/lib/auth"

interface LoginResponse {
  access_token: string
  token_type: string
  user: UserInfo
}

export default function LoginPage() {
  const router = useRouter()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError("")
    setLoading(true)
    try {
      const data = await fetchAPI<LoginResponse>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      })
      setToken(data.access_token)
      saveUser(data.user)
      router.push("/dashboard")
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Đăng nhập thất bại")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="w-full max-w-sm bg-white rounded-lg shadow p-8">
      <div className="text-center mb-6">
        <h1 className="text-xl font-bold text-indigo-600">Break The Barriers</h1>
        <p className="text-sm text-gray-500 mt-1">Đăng nhập tài khoản</p>
      </div>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="user@example.com"
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Mật khẩu</label>
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        {error && <p className="text-red-500 text-sm">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-indigo-600 text-white py-2 rounded text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
        >
          {loading ? "Đang đăng nhập..." : "Đăng nhập"}
        </button>
      </form>
      <p className="text-center text-sm text-gray-500 mt-4">
        Chưa có tài khoản?{" "}
        <Link href="/register" className="text-indigo-600 hover:underline">
          Đăng ký miễn phí
        </Link>
      </p>
    </div>
  )
}
