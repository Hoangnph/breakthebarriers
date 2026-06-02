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
  lang: "en" | "vi"
  onPageChange: (page: number) => void
}

export default function LayoutReader({
  docId, apiUrl, pages, currentPage, lang, onPageChange,
}: ContentLayoutProps) {
  const idx = pages.findIndex((p) => p.page_num === currentPage)
  const prev = idx > 0 ? pages[idx - 1].page_num : null
  const next = idx < pages.length - 1 ? pages[idx + 1].page_num : null
  const src = `${apiUrl}/api/docs/${docId}/pages/${currentPage}?lang=${lang}&raw=true`

  return (
    <div className="flex flex-col h-full min-h-0">
      <main className="flex-1 min-h-0 bg-[#525659]">
        <iframe
          key={`${currentPage}-${lang}`}
          src={src}
          className="w-full h-full border-none block"
          title={`Trang ${currentPage}`}
          sandbox="allow-same-origin allow-scripts"
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
