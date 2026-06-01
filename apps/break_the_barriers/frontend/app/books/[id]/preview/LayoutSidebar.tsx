import { useEffect, useRef } from "react"
import type { ContentLayoutProps } from "./LayoutReader"

export default function LayoutSidebar({
  pages, currentPage, html, loading, onPageChange,
}: ContentLayoutProps) {
  const activeRef = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" })
  }, [currentPage])

  function statusIcon(p: typeof pages[0]) {
    if (p.has_translated) return "✓"
    if (p.has_original) return "○"
    return "—"
  }

  return (
    <div className="flex flex-1 min-h-0 overflow-hidden">
      {/* Sidebar */}
      <aside className="w-56 flex-shrink-0 border-r border-gray-200 bg-white overflow-y-auto">
        {pages.map((p) => {
          const active = p.page_num === currentPage
          return (
            <button
              key={p.page_num}
              ref={active ? activeRef : null}
              onClick={() => onPageChange(p.page_num)}
              className={`w-full text-left px-4 py-2.5 text-sm flex justify-between items-center hover:bg-gray-50 border-b border-gray-100 ${
                active ? "bg-indigo-50 text-indigo-700 font-semibold border-l-2 border-l-indigo-500" : "text-gray-700"
              }`}
            >
              <span>Trang {p.page_num}</span>
              <span className={`text-xs ${p.has_translated ? "text-green-600" : "text-gray-400"}`}>
                {statusIcon(p)}
              </span>
            </button>
          )
        })}
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-8 py-8">
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
    </div>
  )
}
