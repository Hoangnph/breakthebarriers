"use client"

import { useEffect, useRef, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import { ArrowLeft, Play, RotateCcw, CheckCircle, Circle, Loader, FileText } from "lucide-react"
import { fetchAPI } from "@/lib/api"
import { TRANSLATE_LANG_KEY } from "@/lib/constants"

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

const LANGS = [
  { code: "vi", label: "🇻🇳 Tiếng Việt" },
  { code: "en", label: "🇺🇸 English" },
  { code: "zh", label: "🇨🇳 中文" },
  { code: "ja", label: "🇯🇵 日本語" },
  { code: "ko", label: "🇰🇷 한국어" },
  { code: "fr", label: "🇫🇷 Français" },
  { code: "de", label: "🇩🇪 Deutsch" },
] as const


interface PageRow {
  page_num: number
  status: string
  has_original: boolean
  has_translated: boolean
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
  const [extracting, setExtracting] = useState(false)
  const [error, setError] = useState("")
  const esRef = useRef<EventSource | null>(null)
  const [targetLang, setTargetLang] = useState("vi")
  const [pageRows, setPageRows] = useState<PageRow[]>([])
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollFailRef = useRef(0)

  useEffect(() => {
    loadDoc()
    return () => esRef.current?.close()
  }, [id])

  useEffect(() => {
    const saved = localStorage.getItem(TRANSLATE_LANG_KEY)
    if (saved && LANGS.some((l) => l.code === saved)) setTargetLang(saved)
  }, [])

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
    setExtracting(true)
    try {
      await fetchAPI(`/api/docs/${id}/extract`, { method: "POST" })
      await loadDoc()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Extract thất bại")
    } finally {
      setExtracting(false)
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
        body: JSON.stringify({ target_lang: targetLang }),
      })
      startSSE()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Translate thất bại")
    }
  }

  async function loadPages() {
    try {
      const rows = await fetchAPI<PageRow[]>(`/api/docs/${id}/pages`)
      pollFailRef.current = 0
      setPageRows(rows)
      const anyTranslating = rows.some((r) => r.status === "translating")
      if (anyTranslating && !pollRef.current) {
        pollRef.current = setInterval(loadPages, 3000)
      } else if (!anyTranslating && pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    } catch (e) {
      console.warn("loadPages failed", e)  // best-effort
      pollFailRef.current += 1
      if (pollFailRef.current >= 5 && pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
  }

  async function translateOnePage(pageNum: number) {
    setPageRows((rows) => rows.map((r) =>
      r.page_num === pageNum ? { ...r, status: "translating" } : r))
    try {
      await fetchAPI(`/api/docs/${id}/translate?async_mode=true`, {
        method: "POST",
        body: JSON.stringify({ page_num: pageNum, target_lang: targetLang, use_v2: true }),
      })
    } catch {
      setPageRows((rows) => rows.map((r) =>
        r.page_num === pageNum ? { ...r, status: "failed" } : r))
      return
    }
    if (!pollRef.current) pollRef.current = setInterval(loadPages, 3000)
  }

  function changeTargetLang(code: string) {
    setTargetLang(code)
    localStorage.setItem(TRANSLATE_LANG_KEY, code)
  }

  useEffect(() => {
    if (doc && doc.status !== "raw") loadPages()
    return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null } }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doc?.status, id])

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
              // current step (and below) = done; spinner only when genuinely in-flight
              const done = i <= currentStep
              const isExtractStep = i === 1
              const isTranslateStep = i === 2
              const spinning = (isExtractStep && extracting) || (isTranslateStep && streaming)
              return (
                <div key={step} className="flex items-center flex-1 last:flex-none">
                  <div className={`flex flex-col items-center gap-1 ${spinning ? "text-indigo-600" : done ? "text-green-600" : "text-gray-300"}`}>
                    {spinning
                      ? <Loader size={20} className="animate-spin" />
                      : done
                        ? <CheckCircle size={20} />
                        : <Circle size={20} />}
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
          {doc.status !== "raw" && (
            <button
              onClick={() => router.push(`/books/${id}/preview`)}
              className="flex items-center gap-2 border border-gray-300 text-gray-600 px-4 py-2 rounded text-sm hover:bg-gray-50"
            >
              <FileText size={14} /> Xem nội dung
            </button>
          )}
        </div>

        {doc.status !== "raw" && (
          <div className="mt-6">
            <div className="flex items-center gap-3 mb-3">
              <label className="text-xs text-gray-500">Ngôn ngữ dịch</label>
              <select value={targetLang} onChange={(e) => changeTargetLang(e.target.value)}
                      className="text-sm border border-gray-200 rounded-md px-2 py-1 bg-white">
                {LANGS.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
              </select>
            </div>
            <div className="border border-gray-200 rounded-lg overflow-hidden">
              {pageRows.map((r) => {
                const translating = r.status === "translating"
                const done = r.has_translated || r.status === "translated" || r.status === "compiled"
                const failed = r.status === "failed"
                const label = translating ? "—" : done ? "Dịch lại" : failed ? "Thử lại" : "Dịch trang này"
                return (
                  <div key={r.page_num}
                       className="flex items-center justify-between px-4 py-2 border-b border-gray-100 last:border-b-0 text-sm">
                    <span className="text-gray-700">Trang {r.page_num}</span>
                    <span className={translating ? "text-blue-600" : done ? "text-green-600" : failed ? "text-red-600" : "text-gray-400"}>
                      {translating ? "● Đang dịch..." : done ? "✓ Đã dịch" : failed ? "✗ Lỗi" : "○ Chưa dịch"}
                    </span>
                    <button onClick={() => translateOnePage(r.page_num)} disabled={translating}
                            className="text-xs px-2 py-1 rounded border border-indigo-200 text-indigo-600 hover:bg-indigo-50 disabled:opacity-40 disabled:cursor-not-allowed">
                      {label}
                    </button>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
