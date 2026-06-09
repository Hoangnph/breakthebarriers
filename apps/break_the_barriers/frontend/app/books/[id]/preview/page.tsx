"use client"

import { useEffect, useState, useRef } from "react"
import { useParams, useRouter } from "next/navigation"
import { ArrowLeft, AlignJustify, LayoutTemplate, Columns2, ScrollText, ZoomIn, ZoomOut, type LucideIcon } from "lucide-react"
import { fetchAPI, API_URL } from "@/lib/api"
import { TRANSLATE_LANG_KEY } from "@/lib/constants"
import LayoutReader, { type PageInfo } from "./LayoutReader"
import LayoutSidebar from "./LayoutSidebar"
import LayoutSplit from "./LayoutSplit"
import LayoutFlow from "./LayoutFlow"

type Layout = "flow" | "reader" | "sidebar" | "split"
type Lang = "pdf" | "vi"

interface PageMeta {
  page_class?: string
  cover?: string
  policy_override?: string | null
  has_clean_image?: boolean
}

interface Doc {
  id: string
  filename: string
  total_pages: number
  status: string
}

const LAYOUT_KEY = "btb_preview_layout"
const LANG_KEY = "btb_preview_lang"

const LAYOUT_ICONS: Record<Layout, { icon: LucideIcon; label: string }> = {
  flow:    { icon: ScrollText,     label: "Liền mạch" },
  reader:  { icon: AlignJustify,   label: "Reader" },
  sidebar: { icon: LayoutTemplate, label: "Sidebar" },
  split:   { icon: Columns2,       label: "Split" },
}

// Flow has no whole-document PDF, so "Gốc" in flow = the faithful original render
// (raster + original-text overlay = lang "en"); "Dịch" = "vi".
function flowLang(l: Lang): "en" | "vi" {
  return l === "pdf" ? "en" : "vi"
}

export default function PreviewPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()

  const [doc, setDoc] = useState<Doc | null>(null)
  const [pages, setPages] = useState<PageInfo[]>([])
  const [currentPage, setCurrentPage] = useState(1)
  const [layout, setLayout] = useState<Layout>("flow")
  const [lang, setLang] = useState<Lang>("vi")
  const [zoom, setZoom] = useState(1)
  const [pageMeta, setPageMeta] = useState<PageMeta>({})
  const [cleanStatus, setCleanStatus] = useState<Record<"full" | "inpaint", "idle" | "running" | "error">>({ full: "idle", inpaint: "idle" })
  const [cleanBust, setCleanBust] = useState<number>(0)
  const [revertStatus, setRevertStatus] = useState<"idle" | "running" | "error">("idle")
  const [retranslateStatus, setRetranslateStatus] = useState<"idle" | "running" | "done" | "error">("idle")
  const [editMode, setEditMode] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollFailRef = useRef(0)

  async function reloadPages() {
    try {
      const rows = await fetchAPI<PageInfo[]>(`/api/docs/${id}/pages`)
      pollFailRef.current = 0
      setPages(rows)
      const anyTranslating = rows.some((r) => r.status === "translating")
      if (anyTranslating && !pollRef.current) pollRef.current = setInterval(reloadPages, 3000)
      else if (!anyTranslating && pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
    } catch (e) {
      console.warn("reloadPages failed", e)
      pollFailRef.current += 1
      if (pollFailRef.current >= 5 && pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
    }
  }

  async function translatePage(pageNum: number) {
    const target = localStorage.getItem(TRANSLATE_LANG_KEY) || "vi"
    setPages((rows) => rows.map((r) => r.page_num === pageNum ? { ...r, status: "translating" } : r))
    try {
      await fetchAPI(`/api/docs/${id}/translate?async_mode=true`, {
        method: "POST",
        body: JSON.stringify({ page_num: pageNum, target_lang: target, use_v2: true }),
      })
    } catch {
      setPages((rows) => rows.map((r) => r.page_num === pageNum ? { ...r, status: "failed" } : r))
      return
    }
    if (!pollRef.current) pollRef.current = setInterval(reloadPages, 3000)
  }

  // Fetch non-raw page metadata to determine page_class / cover / policy_override / has_clean_image
  async function reloadPageMeta() {
    try {
      const m = await fetchAPI<PageMeta>(`/api/docs/${id}/pages/${currentPage}`)
      setPageMeta(m)
    } catch {
      setPageMeta({})
    }
  }

  useEffect(() => {
    setPageMeta({})
    setCleanStatus({ full: "idle", inpaint: "idle" })
    setRevertStatus("idle")
    setRetranslateStatus("idle")
    reloadPageMeta()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, currentPage])

  async function runClean(method: "full" | "inpaint") {
    setCleanStatus((s) => ({ ...s, [method]: "running" }))
    try {
      await fetchAPI(`/api/docs/${id}/pages/${currentPage}/clean-bg?method=${method}`, { method: "POST" })
      setCleanStatus((s) => ({ ...s, [method]: "idle" }))
      setCleanBust(Date.now())
      reloadPageMeta()
    } catch {
      setCleanStatus((s) => ({ ...s, [method]: "error" }))
    }
  }

  async function runRevert() {
    setRevertStatus("running")
    try {
      await fetchAPI(`/api/docs/${id}/pages/${currentPage}/clean-bg/revert`, { method: "POST" })
      setRevertStatus("idle")
      setCleanBust(Date.now())
      reloadPageMeta()
    } catch {
      setRevertStatus("error")
    }
  }

  async function runRetranslate() {
    setRetranslateStatus("running")
    try {
      await fetchAPI(`/api/docs/${id}/translate`, {
        method: "POST",
        body: JSON.stringify({ page_num: currentPage, target_lang: "vi", quality_tier: "high", use_v2: true }),
      })
      setRetranslateStatus("done")
      setCleanBust(Date.now())
    } catch {
      setRetranslateStatus("error")
    }
  }

  async function setPolicy(value: string) {
    try {
      await fetchAPI(`/api/docs/${id}/pages/${currentPage}/policy`, {
        method: "POST",
        body: JSON.stringify({ value }),
      })
      setCleanBust(Date.now())
      reloadPageMeta()
    } catch {
      // ignore — user can retry
    }
  }

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  // Restore preferences from localStorage
  useEffect(() => {
    const savedLayout = localStorage.getItem(LAYOUT_KEY) as Layout | null
    const savedLang = localStorage.getItem(LANG_KEY)   // raw string (may be legacy "en")
    if (savedLayout && ["flow", "reader", "sidebar", "split"].includes(savedLayout)) setLayout(savedLayout)
    if (savedLang === "en") setLang("pdf")           // legacy HTML mode → Gốc
    else if (savedLang && ["pdf", "vi"].includes(savedLang)) setLang(savedLang as Lang)
  }, [])

  // Load document + page list on mount
  useEffect(() => {
    async function init() {
      try {
        const [docs, pageList] = await Promise.all([
          fetchAPI<Doc[]>("/api/docs"),
          fetchAPI<PageInfo[]>(`/api/docs/${id}/pages`),
        ])
        const found = docs.find((d) => d.id === id)
        if (!found) { router.push("/dashboard"); return }
        setDoc(found)
        setPages(pageList)
        if (pageList.length > 0) setCurrentPage(pageList[0].page_num)
      } catch {
        router.push("/dashboard")
      }
    }
    init()
  }, [id, router])

  function changeLayout(l: Layout) {
    setLayout(l)
    localStorage.setItem(LAYOUT_KEY, l)
  }

  function changeLang(l: Lang) {
    setLang(l)
    localStorage.setItem(LANG_KEY, l)
  }

  // Broadcast the current zoom to every page iframe whenever it changes.
  useEffect(() => {
    document.querySelectorAll("iframe").forEach((f) =>
      f.contentWindow?.postMessage({ type: "btb-zoom", zoom }, "*")
    )
  }, [zoom])

  const zoomIn = () => setZoom((z) => Math.min(5, +(z + 0.25).toFixed(2)))
  const zoomOut = () => setZoom((z) => Math.max(0.25, +(z - 0.25).toFixed(2)))
  const zoomFit = () => setZoom(1)

  // Keyboard: +/-/0 zoom, ←/→ page nav. Also handles keys forwarded from the
  // page iframes (via postMessage) so shortcuts work even when the iframe is focused.
  useEffect(() => {
    function handle(key: string) {
      if (key === "+" || key === "=") setZoom((z) => Math.min(5, +(z + 0.25).toFixed(2)))
      else if (key === "-" || key === "_") setZoom((z) => Math.max(0.25, +(z - 0.25).toFixed(2)))
      else if (key === "0") setZoom(1)
      else if (key === "ArrowRight" || key === "ArrowLeft") {
        const i = pages.findIndex((p) => p.page_num === currentPage)
        if (key === "ArrowRight" && i >= 0 && i < pages.length - 1) setCurrentPage(pages[i + 1].page_num)
        if (key === "ArrowLeft" && i > 0) setCurrentPage(pages[i - 1].page_num)
      }
    }
    function onKey(e: KeyboardEvent) { handle(e.key) }
    function onMsg(e: MessageEvent) {
      if (e.data?.type === "btb-key" && typeof e.data.key === "string") handle(e.data.key)
    }
    window.addEventListener("keydown", onKey)
    window.addEventListener("message", onMsg)
    return () => {
      window.removeEventListener("keydown", onKey)
      window.removeEventListener("message", onMsg)
    }
  }, [pages, currentPage])

  // Click-to-edit: listen for btb-edit postMessages from page iframes when editMode is ON
  useEffect(() => {
    if (!editMode) return
    async function onEditMsg(e: MessageEvent) {
      if (e.data?.type !== "btb-edit") return
      const { span_id, text } = e.data as { span_id: string; text: string }
      const newValue = window.prompt(`Sửa chữ (span ${span_id}):`, text)
      if (newValue === null || newValue === text) return
      try {
        await fetchAPI(`/api/docs/${id}/translations/${span_id}`, {
          method: "PUT",
          body: JSON.stringify({ translated_text: newValue }),
        })
        setCleanBust(Date.now())
      } catch {
        alert("Lỗi khi lưu bản dịch")
      }
    }
    window.addEventListener("message", onEditMsg)
    return () => window.removeEventListener("message", onEditMsg)
  }, [editMode, id])

  const currentPageInfo = pages.find((p) => p.page_num === currentPage)
  const canTranslated = currentPageInfo?.has_translated ?? false

  if (!doc) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-gray-400 text-sm">Đang tải...</p>
      </div>
    )
  }

  const contentProps = { docId: id, apiUrl: API_URL, pages, currentPage, lang, zoom, cleanBust, onPageChange: setCurrentPage }
  const splitProps = { docId: id, pages, currentPage, apiUrl: API_URL, zoom, onPageChange: setCurrentPage }

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      {/* Sticky header */}
      <header className="bg-white border-b border-gray-200 px-4 py-2.5 flex items-center gap-3 flex-shrink-0 z-10">
        <button onClick={() => router.push(`/books/${id}`)}
                className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 flex-shrink-0">
          <ArrowLeft size={16} /> Pipeline
        </button>

        <span className="text-sm font-semibold text-gray-800 truncate flex-1 min-w-0">
          {doc.filename}
        </span>

        {/* Lang toggle — hidden in split */}
        {layout !== "split" && (
          <div className="flex rounded-lg border border-gray-200 overflow-hidden flex-shrink-0">
            <button onClick={() => changeLang("pdf")}
                    className={`px-3 py-1 text-xs font-medium ${lang === "pdf" ? "bg-indigo-600 text-white" : "bg-white text-gray-500 hover:bg-gray-50"}`}>
              Gốc
            </button>
            <button onClick={() => changeLang("vi")}
                    disabled={!canTranslated}
                    className={`px-3 py-1 text-xs font-medium disabled:opacity-40 disabled:cursor-not-allowed ${lang === "vi" ? "bg-indigo-600 text-white" : "bg-white text-gray-500 hover:bg-gray-50"}`}>
              Dịch
            </button>
          </div>
        )}

        {/* Clean-bg buttons — visible when effective policy is clean-photo */}
        {layout !== "flow" && (pageMeta.policy_override === "clean-photo" || (pageMeta.policy_override == null && (pageMeta.cover === "front" || pageMeta.cover === "back"))) && (
          <div className="flex gap-1.5 flex-shrink-0">
            {(["full", "inpaint"] as const).map((method) => (
              <button
                key={method}
                onClick={() => runClean(method)}
                disabled={cleanStatus[method] === "running"}
                className="px-3 py-1 text-xs font-medium rounded-lg border border-amber-300 text-amber-700 bg-amber-50 hover:bg-amber-100 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {cleanStatus[method] === "running"
                  ? "Đang làm sạch…"
                  : cleanStatus[method] === "error"
                  ? "Lỗi làm sạch"
                  : method === "full" ? "Làm sạch (Full)" : "Làm sạch (Inpaint)"}
              </button>
            ))}
            {pageMeta.has_clean_image && (
              <button
                onClick={runRevert}
                disabled={revertStatus === "running"}
                className="px-3 py-1 text-xs font-medium rounded-lg border border-red-300 text-red-700 bg-red-50 hover:bg-red-100 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {revertStatus === "running" ? "Đang hoàn tác…" : revertStatus === "error" ? "Lỗi hoàn tác" : "Revert"}
              </button>
            )}
          </div>
        )}

        {/* Layout switcher */}
        <div className="flex rounded-lg border border-gray-200 overflow-hidden flex-shrink-0">
          {(["flow", "reader", "sidebar", "split"] as Layout[]).map((key) => {
            const { icon: Icon, label } = LAYOUT_ICONS[key]
            return (
              <button key={key} onClick={() => changeLayout(key)} title={label}
                      className={`px-2.5 py-1.5 ${layout === key ? "bg-indigo-600 text-white" : "bg-white text-gray-500 hover:bg-gray-50"}`}>
                <Icon size={15} />
              </button>
            )
          })}
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

        <span className="text-xs text-gray-400 flex-shrink-0">
          {layout === "flow" ? `${doc.total_pages} trang` : `${currentPage}/${doc.total_pages}`}
        </span>
      </header>

      {/* Per-page control panel — per-page editing tools, hidden in flow */}
      {layout !== "flow" && (
      <div className="bg-white border-b border-gray-100 px-4 py-2 flex flex-wrap items-center gap-x-6 gap-y-2 flex-shrink-0">
        <span className="text-xs font-semibold text-gray-500 flex-shrink-0">Tùy chỉnh trang {currentPage}</span>

        {/* Background policy radios */}
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-gray-400 mr-1">Nền:</span>
          {([
            { value: "auto",        label: "Auto" },
            { value: "base-color",  label: "Trắng" },
            { value: "keep-raster", label: "Giữ ảnh" },
            { value: "clean-photo", label: "Làm sạch" },
          ] as const).map(({ value, label }) => (
            <label key={value} className="flex items-center gap-1 cursor-pointer">
              <input
                type="radio"
                name={`policy-${currentPage}`}
                value={value}
                checked={(pageMeta.policy_override ?? "auto") === value}
                onChange={() => setPolicy(value)}
                className="accent-indigo-600"
              />
              <span className="text-xs text-gray-600">{label}</span>
            </label>
          ))}
        </div>

        {/* Re-translate button */}
        <button
          onClick={runRetranslate}
          disabled={retranslateStatus === "running"}
          className="px-3 py-1 text-xs font-medium rounded-lg border border-indigo-300 text-indigo-700 bg-indigo-50 hover:bg-indigo-100 disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
        >
          {retranslateStatus === "running" ? "Đang dịch…" : retranslateStatus === "done" ? "Đã dịch lại ✓" : retranslateStatus === "error" ? "Lỗi dịch" : "Dịch lại trang"}
        </button>

        {/* Click-to-edit toggle */}
        <label className="flex items-center gap-1.5 cursor-pointer flex-shrink-0">
          <input
            type="checkbox"
            checked={editMode}
            onChange={(e) => setEditMode(e.target.checked)}
            className="accent-indigo-600"
          />
          <span className="text-xs text-gray-600">Bật sửa chữ</span>
        </label>
      </div>
      )}

      <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
        {layout === "flow"    && <LayoutFlow docId={id} apiUrl={API_URL} lang={flowLang(lang)} zoom={zoom} />}
        {layout === "reader"  && <LayoutReader  {...contentProps} />}
        {layout === "sidebar" && <LayoutSidebar {...contentProps} onTranslate={translatePage} />}
        {layout === "split"   && <LayoutSplit   {...splitProps} />}
      </div>
    </div>
  )
}
