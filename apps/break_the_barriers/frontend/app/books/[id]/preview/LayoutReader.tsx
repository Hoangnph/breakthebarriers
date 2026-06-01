import { ChevronLeft, ChevronRight } from "lucide-react"

export interface PageInfo {
  page_num: number
  status: string
  has_original: boolean
  has_translated: boolean
}

export interface ContentLayoutProps {
  pages: PageInfo[]
  currentPage: number
  html: string
  loading: boolean
  onPageChange: (page: number) => void
}

export default function LayoutReader({
  pages, currentPage, html, loading, onPageChange,
}: ContentLayoutProps) {
  const idx = pages.findIndex((p) => p.page_num === currentPage)
  const prev = idx > 0 ? pages[idx - 1].page_num : null
  const next = idx < pages.length - 1 ? pages[idx + 1].page_num : null

  return (
    <div className="flex flex-col min-h-0">
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-6 py-8">
          {loading ? (
            <div className="space-y-3 animate-pulse">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="h-4 bg-gray-200 rounded" style={{ width: `${70 + (i % 3) * 10}%` }} />
              ))}
            </div>
          ) : html ? (
            <article className="prose max-w-none text-sm"
                     dangerouslySetInnerHTML={{ __html: html }} />
          ) : (
            <p className="text-gray-400 text-sm text-center py-20">Không có nội dung.</p>
          )}
        </div>
      </main>

      <nav className="border-t border-gray-200 bg-white px-6 py-3 flex justify-between items-center">
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
