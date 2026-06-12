"use client"

import { useEffect, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import { ArrowLeft, ZoomIn, ZoomOut } from "lucide-react"
import { fetchAPI, API_URL } from "@/lib/api"
import LayoutFlow from "./LayoutFlow"

interface Doc {
  id: string
  filename: string
  total_pages: number
  status: string
}

// Tập trung 1 chức năng: Original PDF → HTML (element thật, relative) ở chế độ Flow.
export default function PreviewPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()

  const [doc, setDoc] = useState<Doc | null>(null)
  const [zoom, setZoom] = useState(1)
  const [lang, setLang] = useState<"goc" | "vi">("goc")

  useEffect(() => {
    async function init() {
      try {
        const docs = await fetchAPI<Doc[]>("/api/docs")
        const found = docs.find((d) => d.id === id)
        if (!found) { router.push("/dashboard"); return }
        setDoc(found)
      } catch {
        router.push("/dashboard")
      }
    }
    init()
  }, [id, router])

  // Broadcast zoom to the flow iframe whenever it changes.
  useEffect(() => {
    document.querySelectorAll("iframe").forEach((f) =>
      f.contentWindow?.postMessage({ type: "btb-zoom", zoom }, "*")
    )
  }, [zoom])

  // Keyboard zoom: +/-/0
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "+" || e.key === "=") setZoom((z) => Math.min(5, +(z + 0.25).toFixed(2)))
      else if (e.key === "-" || e.key === "_") setZoom((z) => Math.max(0.25, +(z - 0.25).toFixed(2)))
      else if (e.key === "0") setZoom(1)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  const zoomIn = () => setZoom((z) => Math.min(5, +(z + 0.25).toFixed(2)))
  const zoomOut = () => setZoom((z) => Math.max(0.25, +(z - 0.25).toFixed(2)))
  const zoomFit = () => setZoom(1)

  if (!doc) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-gray-400 text-sm">Đang tải...</p>
      </div>
    )
  }

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-4 py-2.5 flex items-center gap-3 flex-shrink-0 z-10">
        <button onClick={() => router.push(`/books/${id}`)}
                className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 flex-shrink-0">
          <ArrowLeft size={16} /> Pipeline
        </button>

        <span className="text-sm font-semibold text-gray-800 truncate flex-1 min-w-0">
          {doc.filename}
        </span>

        {/* Gốc / Dịch toggle */}
        <div className="flex rounded-lg border border-gray-200 overflow-hidden flex-shrink-0">
          <button onClick={() => setLang("goc")}
                  className={`px-3 py-1 text-xs font-medium ${lang === "goc" ? "bg-indigo-600 text-white" : "bg-white text-gray-500 hover:bg-gray-50"}`}>
            Gốc
          </button>
          <button onClick={() => setLang("vi")}
                  className={`px-3 py-1 text-xs font-medium ${lang === "vi" ? "bg-indigo-600 text-white" : "bg-white text-gray-500 hover:bg-gray-50"}`}>
            Dịch
          </button>
        </div>

        {/* Zoom controls */}
        <div className="flex items-center rounded-lg border border-gray-200 overflow-hidden flex-shrink-0">
          <button onClick={zoomOut} title="Thu nhỏ (-)"
                  className="px-2 py-1.5 text-gray-500 hover:bg-gray-50">
            <ZoomOut size={15} />
          </button>
          <button onClick={zoomFit} title="Vừa màn hình (0)"
                  className="px-2 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50 border-x border-gray-200 min-w-[3.25rem]">
            {Math.round(zoom * 100)}%
          </button>
          <button onClick={zoomIn} title="Phóng to (+)"
                  className="px-2 py-1.5 text-gray-500 hover:bg-gray-50">
            <ZoomIn size={15} />
          </button>
        </div>

        <span className="text-xs text-gray-400 flex-shrink-0">{doc.total_pages} trang</span>
      </header>

      <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
        <LayoutFlow docId={id} apiUrl={API_URL} zoom={zoom} lang={lang} />
      </div>
    </div>
  )
}
