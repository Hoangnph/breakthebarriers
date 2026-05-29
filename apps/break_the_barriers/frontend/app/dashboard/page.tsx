"use client"

import { useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { Upload, Trash2, Eye, LogOut } from "lucide-react"
import { fetchAPI, ApiError } from "@/lib/api"
import { getUser, logout, UserInfo } from "@/lib/auth"

interface Doc {
  id: string
  filename: string
  total_pages: number
  status: string
  created_at: string
}

const STATUS_LABEL: Record<string, string> = {
  raw: "Chưa xử lý",
  extracting: "Đang extract",
  extracted: "Đã extract",
  translating: "Đang dịch",
  translated: "Đã dịch",
  compiled: "Hoàn tất",
  failed: "Lỗi",
}

const STATUS_COLOR: Record<string, string> = {
  raw: "bg-gray-100 text-gray-600",
  extracting: "bg-blue-100 text-blue-700",
  extracted: "bg-blue-100 text-blue-700",
  translating: "bg-yellow-100 text-yellow-700",
  translated: "bg-green-100 text-green-700",
  compiled: "bg-purple-100 text-purple-700",
  failed: "bg-red-100 text-red-600",
}

export default function DashboardPage() {
  const router = useRouter()
  const [user, setUser] = useState<UserInfo | null>(null)
  const [docs, setDocs] = useState<Doc[]>([])
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState("")
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    setUser(getUser())
    loadDocs()
  }, [])

  async function loadDocs() {
    try {
      const data = await fetchAPI<Doc[]>("/api/docs")
      setDocs(data)
    } catch {
      // fetchAPI handles 401 redirect
    }
  }

  async function handleUpload(file: File) {
    setError("")
    setUploading(true)
    const form = new FormData()
    form.append("file", file)
    try {
      await fetchAPI("/api/docs/upload", { method: "POST", body: form })
      await loadDocs()
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 402) return
      setError(err instanceof Error ? err.message : "Upload thất bại")
    } finally {
      setUploading(false)
    }
  }

  async function handleDelete(id: string) {
    if (!confirm(`Xoá "${id}"?`)) return
    await fetchAPI(`/api/docs/${id}`, { method: "DELETE" })
    setDocs((prev) => prev.filter((d) => d.id !== id))
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file) handleUpload(file)
  }

  function handleLogout() {
    logout()
    router.push("/login")
  }

  const quotaPercent = user
    ? Math.min(100, Math.round((user.pages_used_this_month / user.pages_limit) * 100))
    : 0

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between">
        <span className="text-indigo-600 font-bold">Break The Barriers</span>
        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-500">{user?.email}</span>
          <button
            onClick={handleLogout}
            className="text-sm text-gray-500 hover:text-gray-700 flex items-center gap-1"
          >
            <LogOut size={14} /> Đăng xuất
          </button>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-6 py-8 space-y-6">
        {user && (
          <div className="bg-white border border-gray-200 rounded-lg p-4">
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm text-gray-600">
                Quota tháng này: <strong>{user.pages_used_this_month}</strong>/{user.pages_limit} trang
              </span>
              <span className="text-xs text-gray-400 capitalize">{user.plan} plan</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div
                className={`h-2 rounded-full transition-all ${quotaPercent >= 90 ? "bg-red-500" : "bg-indigo-500"}`}
                style={{ width: `${quotaPercent}%` }}
              />
            </div>
            {quotaPercent >= 90 && (
              <p className="text-xs text-red-500 mt-1">
                Gần hết quota —{" "}
                <a href="/pricing" className="underline">Nâng cấp Pro</a>
              </p>
            )}
          </div>
        )}

        <div
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
          onClick={() => fileRef.current?.click()}
          className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center cursor-pointer hover:border-indigo-400 hover:bg-indigo-50 transition-colors"
        >
          <Upload className="mx-auto mb-2 text-gray-400" size={28} />
          <p className="text-sm text-gray-500">
            {uploading ? "Đang tải lên..." : "Kéo thả hoặc click để upload PDF/EPUB"}
          </p>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.epub"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && handleUpload(e.target.files[0])}
          />
        </div>

        {error && <p className="text-red-500 text-sm">{error}</p>}

        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-100 flex justify-between items-center">
            <h2 className="font-semibold text-gray-800">Thư viện của tôi</h2>
            <span className="text-xs text-gray-400">{docs.length} cuốn</span>
          </div>
          {docs.length === 0 ? (
            <p className="text-sm text-gray-400 text-center py-10">
              Chưa có sách. Upload PDF hoặc EPUB để bắt đầu.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
                <tr>
                  <th className="text-left px-4 py-2">Tên file</th>
                  <th className="text-left px-4 py-2">Trạng thái</th>
                  <th className="text-left px-4 py-2">Trang</th>
                  <th className="text-left px-4 py-2">Ngày tạo</th>
                  <th className="px-4 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {docs.map((doc) => (
                  <tr key={doc.id} className="border-t border-gray-100 hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium text-gray-800 truncate max-w-[200px]">
                      {doc.filename}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-xs px-2 py-1 rounded-full font-medium ${STATUS_COLOR[doc.status] ?? "bg-gray-100 text-gray-600"}`}>
                        {STATUS_LABEL[doc.status] ?? doc.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-500">{doc.total_pages}</td>
                    <td className="px-4 py-3 text-gray-400 text-xs">
                      {new Date(doc.created_at).toLocaleDateString("vi-VN")}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2 justify-end">
                        <button
                          onClick={() => router.push(`/books/${doc.id}`)}
                          className="text-indigo-600 hover:text-indigo-800"
                          title="Xem chi tiết"
                        >
                          <Eye size={15} />
                        </button>
                        <button
                          onClick={() => handleDelete(doc.id)}
                          className="text-red-400 hover:text-red-600"
                          title="Xoá"
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}
