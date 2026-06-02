import { useEffect, useRef } from "react"
import type { ContentLayoutProps } from "./LayoutReader"

export default function LayoutSidebar({
  docId, apiUrl, pages, currentPage, lang, zoom, onPageChange,
  onTranslate,
}: ContentLayoutProps & { onTranslate?: (pageNum: number) => void }) {
  const activeRef = useRef<HTMLDivElement | null>(null)

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
            <div
              key={p.page_num}
              ref={active ? activeRef : null}
              className={`px-4 py-2.5 text-sm flex justify-between items-center gap-2 border-b border-gray-100 ${
                active ? "bg-indigo-50 text-indigo-700 font-semibold border-l-2 border-l-indigo-500" : "text-gray-700"
              }`}
            >
              <button onClick={() => onPageChange(p.page_num)}
                      className="flex-1 text-left hover:underline">
                Trang {p.page_num}
              </button>
              <span className={`text-xs ${p.has_translated ? "text-green-600" : p.status === "translating" ? "text-blue-600" : "text-gray-400"}`}>
                {p.status === "translating" ? "●" : statusIcon(p)}
              </span>
              {onTranslate && p.status !== "translating" && (
                <button
                  onClick={() => onTranslate(p.page_num)}
                  className="text-[11px] px-1.5 py-0.5 rounded border border-indigo-200 text-indigo-600 hover:bg-indigo-100"
                >
                  {p.has_translated ? "Dịch lại" : "Dịch"}
                </button>
              )}
            </div>
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
          onLoad={(e) => e.currentTarget.contentWindow?.postMessage({ type: "btb-zoom", zoom }, "*")}
        />
      </main>
    </div>
  )
}
