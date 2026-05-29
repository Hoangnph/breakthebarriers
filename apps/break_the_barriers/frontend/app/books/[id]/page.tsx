"use client"

import { useEffect, useRef, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import { ArrowLeft, Play, RotateCcw, CheckCircle, Circle, Loader } from "lucide-react"
import { fetchAPI } from "@/lib/api"

interface Doc {
  id: string
  filename: string
  total_pages: number
  status: string
  created_at: string
  volume_tier?: string
  quality_tier?: string
  estimated_cost_usd?: number
}

interface ProgressEvent {
  page: number
  total: number
  status: string
  percent: number
  eta_min: number
}

const PIPELINE_STEPS = ["raw", "extracted", "translated", "compiled"]
const STEP_LABEL: Record<string, string> = {
  raw: "Upload",
  extracted: "Extract",
  translated: "Dịch",
  compiled: "Hoàn tất",
}

function stepIndex(status: string): number {
  const idx = PIPELINE_STEPS.indexOf(status)
  return idx === -1 ? 0 : idx
}

export default function BookDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const [doc, setDoc] = useState<Doc | null>(null)
  const [progress, setProgress] = useState<ProgressEvent | null>(null)
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState("")
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    loadDoc()
    return () => esRef.current?.close()
  }, [id])

  async function loadDoc() {
    try {
      const docs = await fetchAPI<Doc[]>("/api/docs")
      setDoc(docs.find((d) => d.id === id) ?? null)
    } catch {
      // handled by fetchAPI
    }
  }

  async function handleExtract() {
    setError("")
    try {
      await fetchAPI(`/api/docs/${id}/extract`, { method: "POST" })
      await loadDoc()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Extract thất bại")
    }
  }

  async function handleResume() {
    setError("")
    try {
      await fetchAPI(`/api/docs/${id}/resume`, { method: "POST" })
      startSSE()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Resume thất bại")
    }
  }

  function startSSE() {
    esRef.current?.close()
    setStreaming(true)
    setProgress(null)
    const token = typeof window !== "undefined" ? localStorage.getItem("btb_token") : null
    const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
    const url = `${base}/api/docs/${id}/progress` + (token ? `?token=${token}` : "")
    const es = new EventSource(url)
    esRef.current = es
    es.onmessage = (e) => {
      const evt: ProgressEvent = JSON.parse(e.data)
      setProgress(evt)
      if (evt.percent >= 100) {
        setStreaming(false)
        es.close()
        loadDoc()
      }
    }
    es.onerror = () => { setStreaming(false); es.close() }
  }

  async function handleTranslateAll() {
    setError("")
    try {
      await fetchAPI(`/api/docs/${id}/translate-all`, {
        method: "POST",
        body: JSON.stringify({ target_lang: "vi" }),
      })
      startSSE()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Translate thất bại")
    }
  }

  if (!doc) return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <p className="text-gray-400">Đang tải...</p>
    </div>
  )

  const currentStep = stepIndex(doc.status)

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center gap-3">
        <button onClick={() => router.push("/dashboard")} className="text-gray-500 hover:text-gray-700">
          <ArrowLeft size={18} />
        </button>
        <span className="font-semibold text-gray-800 truncate">{doc.filename}</span>
      </header>

      <div className="max-w-2xl mx-auto px-6 py-8 space-y-6">
        <div className="bg-white border border-gray-200 rounded-lg p-4 grid grid-cols-3 gap-4 text-sm">
          <div><span className="text-gray-400 block text-xs">Số trang</span>{doc.total_pages}</div>
          <div><span className="text-gray-400 block text-xs">Volume tier</span>{doc.volume_tier ?? "—"}</div>
          <div>
            <span className="text-gray-400 block text-xs">Chi phí ước tính</span>
            {doc.estimated_cost_usd != null ? `$${doc.estimated_cost_usd.toFixed(3)}` : "—"}
          </div>
        </div>

        <div className="bg-white border border-gray-200 rounded-lg p-6">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">Pipeline</h2>
          <div className="flex items-center">
            {PIPELINE_STEPS.map((step, i) => {
              const done = i < currentStep
              const active = i === currentStep
              return (
                <div key={step} className="flex items-center flex-1 last:flex-none">
                  <div className={`flex flex-col items-center gap-1 ${active ? "text-indigo-600" : done ? "text-green-600" : "text-gray-300"}`}>
                    {done ? <CheckCircle size={20} /> : active ? <Loader size={20} className="animate-spin" /> : <Circle size={20} />}
                    <span className="text-xs font-medium">{STEP_LABEL[step]}</span>
                  </div>
                  {i < PIPELINE_STEPS.length - 1 && (
                    <div className={`h-0.5 flex-1 mx-1 ${i < currentStep ? "bg-green-400" : "bg-gray-200"}`} />
                  )}
                </div>
              )
            })}
          </div>
        </div>

        {streaming && progress && (
          <div className="bg-white border border-gray-200 rounded-lg p-4">
            <div className="flex justify-between text-sm text-gray-600 mb-2">
              <span>Trang {progress.page}/{progress.total}</span>
              <span>{progress.percent}% — còn {progress.eta_min} phút</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div className="bg-indigo-500 h-2 rounded-full transition-all" style={{ width: `${progress.percent}%` }} />
            </div>
          </div>
        )}

        {error && <p className="text-red-500 text-sm">{error}</p>}

        <div className="flex gap-3 flex-wrap">
          {doc.status === "raw" && (
            <button onClick={handleExtract}
              className="flex items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded text-sm hover:bg-indigo-700">
              <Play size={14} /> Extract
            </button>
          )}
          {doc.status === "extracted" && (
            <button onClick={handleTranslateAll}
              className="flex items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded text-sm hover:bg-indigo-700">
              <Play size={14} /> Dịch tất cả
            </button>
          )}
          {(doc.status === "translating" || doc.status === "failed") && (
            <button onClick={handleResume}
              className="flex items-center gap-2 border border-indigo-600 text-indigo-600 px-4 py-2 rounded text-sm hover:bg-indigo-50">
              <RotateCcw size={14} /> Resume
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
