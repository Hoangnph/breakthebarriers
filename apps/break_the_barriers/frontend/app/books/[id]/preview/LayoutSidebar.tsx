import { useEffect, useRef } from "react"
import type { ContentLayoutProps } from "./LayoutReader"

export default function LayoutSidebar({
  docId, apiUrl, pages, currentPage, lang, onPageChange,
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

  const src = `${apiUrl}/api/docs/${docId}/pages/${currentPage}?lang=${lang}&raw=true`

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

      {/* Main content — full-height iframe that auto-fits the page */}
      <main className="flex-1 min-h-0 bg-[#525659]">
        <iframe
          key={`${currentPage}-${lang}`}
          src={src}
          className="w-full h-full border-none block"
          title={`Trang ${currentPage}`}
          sandbox="allow-same-origin allow-scripts"
        />
      </main>
    </div>
  )
}
