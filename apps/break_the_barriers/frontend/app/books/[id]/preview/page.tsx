"use client"

import { useEffect, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import { ArrowLeft, AlignJustify, LayoutTemplate, Columns2, type LucideIcon } from "lucide-react"
import { fetchAPI, API_URL } from "@/lib/api"
import LayoutReader, { type PageInfo } from "./LayoutReader"
import LayoutSidebar from "./LayoutSidebar"
import LayoutSplit from "./LayoutSplit"

type Layout = "reader" | "sidebar" | "split"
type Lang = "en" | "vi"

interface Doc {
  id: string
  filename: string
  total_pages: number
  status: string
}

const LAYOUT_KEY = "btb_preview_layout"
const LANG_KEY = "btb_preview_lang"

const LAYOUT_ICONS: Record<Layout, { icon: LucideIcon; label: string }> = {
  reader:  { icon: AlignJustify,   label: "Reader" },
  sidebar: { icon: LayoutTemplate, label: "Sidebar" },
  split:   { icon: Columns2,       label: "Split" },
}

export default function PreviewPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()

  const [doc, setDoc] = useState<Doc | null>(null)
  const [pages, setPages] = useState<PageInfo[]>([])
  const [currentPage, setCurrentPage] = useState(1)
  const [layout, setLayout] = useState<Layout>("reader")
  const [lang, setLang] = useState<Lang>("en")

  // Restore preferences from localStorage
  useEffect(() => {
    const savedLayout = localStorage.getItem(LAYOUT_KEY) as Layout | null
    const savedLang = localStorage.getItem(LANG_KEY) as Lang | null
    if (savedLayout && ["reader", "sidebar", "split"].includes(savedLayout)) setLayout(savedLayout)
    if (savedLang && ["en", "vi"].includes(savedLang)) setLang(savedLang)
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

  const currentPageInfo = pages.find((p) => p.page_num === currentPage)
  const canTranslated = currentPageInfo?.has_translated ?? false

  if (!doc) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-gray-400 text-sm">Đang tải...</p>
      </div>
    )
  }

  const contentProps = { docId: id, apiUrl: API_URL, pages, currentPage, lang, onPageChange: setCurrentPage }
  const splitProps = { docId: id, pages, currentPage, apiUrl: API_URL, onPageChange: setCurrentPage }

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
            <button onClick={() => changeLang("en")}
                    className={`px-3 py-1 text-xs font-medium ${lang === "en" ? "bg-indigo-600 text-white" : "bg-white text-gray-500 hover:bg-gray-50"}`}>
              Original
            </button>
            <button onClick={() => changeLang("vi")}
                    disabled={!canTranslated}
                    className={`px-3 py-1 text-xs font-medium disabled:opacity-40 disabled:cursor-not-allowed ${lang === "vi" ? "bg-indigo-600 text-white" : "bg-white text-gray-500 hover:bg-gray-50"}`}>
              Translated
            </button>
          </div>
        )}

        {/* Layout switcher */}
        <div className="flex rounded-lg border border-gray-200 overflow-hidden flex-shrink-0">
          {(["reader", "sidebar", "split"] as Layout[]).map((key) => {
            const { icon: Icon, label } = LAYOUT_ICONS[key]
            return (
              <button key={key} onClick={() => changeLayout(key)} title={label}
                      className={`px-2.5 py-1.5 ${layout === key ? "bg-indigo-600 text-white" : "bg-white text-gray-500 hover:bg-gray-50"}`}>
                <Icon size={15} />
              </button>
            )
          })}
        </div>

        <span className="text-xs text-gray-400 flex-shrink-0">
          {currentPage}/{doc.total_pages}
        </span>
      </header>

      <div className="flex-1 min-h-0 overflow-hidden">
        {layout === "reader"  && <LayoutReader  {...contentProps} />}
        {layout === "sidebar" && <LayoutSidebar {...contentProps} />}
        {layout === "split"   && <LayoutSplit   {...splitProps} />}
      </div>
    </div>
  )
}
