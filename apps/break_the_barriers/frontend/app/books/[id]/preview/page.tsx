"use client"

import { useEffect, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import { ArrowLeft, ZoomIn, ZoomOut, Languages } from "lucide-react"
import { fetchAPI, API_URL } from "@/lib/api"
import LayoutFlow from "./LayoutFlow"

interface Doc {
  id: string
  filename: string
  total_pages: number
  status: string
}

interface TranslateEstimate {
  pages: number
  candidate_requests: number
  online: { eta_text: string; cost_note: string }
  batch: { eta_text: string; cost_note: string }
  recommended_mode: "online" | "batch"
  recommendation: string
}

// Tập trung 1 chức năng: Original PDF → HTML (element thật, relative) ở chế độ Flow.
export default function PreviewPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()

  const [doc, setDoc] = useState<Doc | null>(null)
  const [zoom, setZoom] = useState(1)
  const [lang, setLang] = useState<"goc" | "vi">("goc")
  const [transStatus, setTransStatus] = useState<"idle" | "running" | "done" | "error">("idle")
  const [reloadKey, setReloadKey] = useState(0)
  // Chọn chế độ dịch: mở hộp thoại hiện ETA cho khách chọn Nhanh vs Số lượng lớn.
  const [showModeModal, setShowModeModal] = useState(false)
  const [estimate, setEstimate] = useState<TranslateEstimate | null>(null)
  const [batchInfo, setBatchInfo] = useState<{ job: string; eta: string } | null>(null)

  async function openTranslateModal() {
    setShowModeModal(true)
    setEstimate(null)
    try {
      const est = await fetchAPI<TranslateEstimate>(`/api/docs/${id}/translate-estimate?quality=max`)
      setEstimate(est)
    } catch {
      /* vẫn cho chọn dù ước tính lỗi */
    }
  }

  async function runOnline() {
    setShowModeModal(false)
    setTransStatus("running")
    try {
      // Nhanh: dịch nền online qua harness (tier max). htmlflow?lang=vi đọc TM live.
      await fetchAPI(`/api/docs/${id}/translate-flow?lang=vi&quality=max`, { method: "POST" })
    } catch {
      setTransStatus("error")
    }
  }

  async function runBatch() {
    setShowModeModal(false)
    setTransStatus("running")
    try {
      // Số lượng lớn: nộp Gemini Batch (bất đồng bộ, rẻ ~50%). Backend auto-poll
      // tự chốt vào TM khi xong; frontend cũng poll để tự refresh view khi done.
      const r = await fetchAPI<{ job: string; eta: string }>(
        `/api/docs/${id}/translate-batch?lang=vi&quality=max`, { method: "POST" })
      setBatchInfo({ job: r.job, eta: r.eta })
      setTransStatus("done")
      pollBatch(r.job)
    } catch {
      setTransStatus("error")
    }
  }

  function pollBatch(job: string) {
    // poll mỗi 60s tới khi backend báo done → tự refresh bản Dịch (khỏi bấm tay).
    const timer = setInterval(async () => {
      try {
        const s = await fetchAPI<{ status: string; translated_blocks?: number }>(
          `/api/docs/${id}/translate-batch-status?job=${encodeURIComponent(job)}`)
        if (s.status === "done") {
          clearInterval(timer)
          setBatchInfo(null)
          setReloadKey((k) => k + 1)   // tự nạp lại bản dịch mới
        }
      } catch {
        /* tiếp tục poll ở lần sau */
      }
    }, 60000)
  }

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

        {/* Dịch tài liệu (AI) — chỉ hiện ở chế độ Dịch */}
        {lang === "vi" && (
          <div className="flex gap-1.5 flex-shrink-0">
            <button onClick={openTranslateModal} disabled={transStatus === "running"}
                    className="flex items-center gap-1 px-3 py-1 text-xs font-medium rounded-lg border border-indigo-300 text-indigo-700 bg-indigo-50 hover:bg-indigo-100 disabled:opacity-60 disabled:cursor-not-allowed">
              <Languages size={14} />
              {transStatus === "running" ? "Đang dịch nền…" : transStatus === "error" ? "Lỗi dịch" : "Dịch tài liệu (AI)"}
            </button>
            <button onClick={() => setReloadKey((k) => k + 1)} title="Tải lại bản dịch mới nhất"
                    className="px-3 py-1 text-xs font-medium rounded-lg border border-gray-200 text-gray-600 bg-white hover:bg-gray-50">
              Làm mới
            </button>
          </div>
        )}

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

      {batchInfo && (
        <div className="px-4 py-2 bg-amber-50 border-b border-amber-200 text-xs text-amber-800 flex items-center gap-2">
          <span className="font-semibold">Đã nộp dịch số lượng lớn (Batch).</span>
          <span>Bản dịch sẽ sẵn sàng sau {batchInfo.eta} Hệ thống tự cập nhật khi xong — bạn không cần làm gì.</span>
          <span className="text-amber-500 font-mono truncate">{batchInfo.job}</span>
        </div>
      )}

      <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
        <LayoutFlow docId={id} apiUrl={API_URL} zoom={zoom} lang={lang} bust={reloadKey} />
      </div>

      {/* Hộp thoại chọn chế độ dịch — hiện ETA rõ ràng cho khách chọn */}
      {showModeModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
             onClick={() => setShowModeModal(false)}>
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-5"
               onClick={(e) => e.stopPropagation()}>
            <h3 className="text-base font-semibold text-gray-800 mb-1">Chọn chế độ dịch</h3>
            <p className="text-xs text-gray-500 mb-3">
              {estimate ? `${estimate.pages} trang · chất lượng cao (harness max)` : "Đang ước tính…"}
            </p>
            {estimate && (
              <div className="mb-3 rounded-lg bg-indigo-50 border border-indigo-100 px-3 py-2 text-xs text-indigo-800">
                {estimate.recommendation.replace(/\*\*/g, "")}
              </div>
            )}
            <div className="flex flex-col gap-2">
              <button onClick={runOnline}
                      className={`text-left rounded-lg border px-3 py-2.5 hover:bg-gray-50 ${estimate?.recommended_mode === "online" ? "border-indigo-400 ring-1 ring-indigo-200" : "border-gray-200"}`}>
                <div className="text-sm font-medium text-gray-800">Nhanh (Online){estimate?.recommended_mode === "online" ? " · Khuyến nghị" : ""}</div>
                <div className="text-xs text-gray-500">
                  Xem ngay · {estimate ? estimate.online.eta_text : "—"} · {estimate?.online.cost_note ?? "giá đầy đủ"}
                </div>
              </button>
              <button onClick={runBatch}
                      className={`text-left rounded-lg border px-3 py-2.5 hover:bg-gray-50 ${estimate?.recommended_mode === "batch" ? "border-indigo-400 ring-1 ring-indigo-200" : "border-gray-200"}`}>
                <div className="text-sm font-medium text-gray-800">Số lượng lớn (Tiết kiệm){estimate?.recommended_mode === "batch" ? " · Khuyến nghị" : ""}</div>
                <div className="text-xs text-gray-500">
                  {estimate ? estimate.batch.eta_text : "Bất đồng bộ, tối đa 24h"} · {estimate?.batch.cost_note ?? "rẻ ~50%"}
                </div>
              </button>
            </div>
            <button onClick={() => setShowModeModal(false)}
                    className="mt-3 w-full text-xs text-gray-400 hover:text-gray-600 py-1">Huỷ</button>
          </div>
        </div>
      )}
    </div>
  )
}
