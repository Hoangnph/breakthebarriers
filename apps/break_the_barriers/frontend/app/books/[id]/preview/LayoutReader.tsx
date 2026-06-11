import { ChevronLeft, ChevronRight } from "lucide-react"

export interface PageInfo {
  page_num: number
  status: string
  has_original: boolean
  has_translated: boolean
}

export interface ContentLayoutProps {
  docId: string
  apiUrl: string
  pages: PageInfo[]
  currentPage: number
  lang: "pdf" | "en" | "vi"
  zoom: number
  cleanBust?: number
  onPageChange: (page: number) => void
}

export default function LayoutReader({
  docId, apiUrl, pages, currentPage, lang, zoom, cleanBust, onPageChange,
}: ContentLayoutProps) {
  const idx = pages.findIndex((p) => p.page_num === currentPage)
  const prev = idx > 0 ? pages[idx - 1].page_num : null
  const next = idx < pages.length - 1 ? pages[idx + 1].page_num : null
  // Faithful SVG reader: Gốc (pdf/en) → view=goc (SVG + lớp text vô hình),
  // Dịch (vi) → view=dich (reflow + bản dịch). Cả hai đều là HTML raw cho iframe.
  const view = lang === "vi" ? "dich" : "goc"
  const bustParam = cleanBust ? `&t=${cleanBust}` : ""
  const src = `${apiUrl}/api/docs/${docId}/pages/${currentPage}?view=${view}&raw=true${bustParam}`

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <main className="flex-1 min-h-0 bg-[#525659]">
        <iframe
          key={`${currentPage}-${lang}-${cleanBust ?? 0}`}
          src={src}
          className="w-full h-full border-none block"
          title={`Trang ${currentPage}`}
          sandbox="allow-same-origin allow-scripts"
          onLoad={(e) => e.currentTarget.contentWindow?.postMessage({ type: "btb-zoom", zoom }, "*")}
        />
      </main>

      <nav className="border-t border-gray-200 bg-white px-6 py-3 flex justify-between items-center flex-shrink-0">
        {prev !== null ? (
          <button onClick={() => onPageChange(prev)}
                  className="flex items-center gap-1 text-sm text-indigo-600 hover:underline">
            <ChevronLeft size={16} /> Trang {prev}
          </button>
        ) : <span />}
        {next !== null ? (
          <button onClick={() => onPageChange(next)}
                  className="flex items-center gap-1 text-sm text-indigo-600 hover:underline">
            Trang {next} <ChevronRight size={16} />
          </button>
        ) : <span />}
      </nav>
    </div>
  )
}
