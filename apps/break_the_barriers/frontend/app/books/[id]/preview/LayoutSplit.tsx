import { ChevronLeft, ChevronRight } from "lucide-react"
import type { PageInfo } from "./LayoutReader"

export interface SplitLayoutProps {
  docId: string
  pages: PageInfo[]
  currentPage: number
  apiUrl: string
  zoom: number
  onPageChange: (page: number) => void
}

function IframePane({
  label, src, hasContent, zoom,
}: { label: string; src: string; hasContent: boolean; zoom: number }) {
  return (
    <div className="flex-1 flex flex-col min-w-0 border-r last:border-r-0 border-gray-200">
      <div className="px-4 py-2 bg-gray-50 border-b border-gray-200 text-xs font-semibold text-gray-500 uppercase tracking-wide">
        {label}
      </div>
      {hasContent ? (
        <iframe
          src={src}
          className="flex-1 w-full border-none bg-white"
          title={label}
          sandbox="allow-same-origin allow-scripts"
          onLoad={(e) => e.currentTarget.contentWindow?.postMessage({ type: "btb-zoom", zoom }, "*")}
        />
      ) : (
        <div className="flex-1 flex items-center justify-center text-sm text-gray-400">
          Trang này chưa được dịch
        </div>
      )}
    </div>
  )
}

export default function LayoutSplit({
  docId, pages, currentPage, apiUrl, zoom, onPageChange,
}: SplitLayoutProps) {
  const idx = pages.findIndex((p) => p.page_num === currentPage)
  const currentPageInfo = pages[idx]
  const prev = idx > 0 ? pages[idx - 1].page_num : null
  const next = idx < pages.length - 1 ? pages[idx + 1].page_num : null

  const base = `${apiUrl}/api/docs/${docId}/pages/${currentPage}`
  const srcOriginal = `${base}?lang=en&raw=true`
  const srcTranslated = `${base}?lang=vi&raw=true`

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="flex flex-1 min-h-0 overflow-hidden">
        <IframePane
          label="Original"
          src={srcOriginal}
          hasContent={currentPageInfo?.has_original ?? false}
          zoom={zoom}
        />
        <IframePane
          label="Translated"
          src={srcTranslated}
          hasContent={currentPageInfo?.has_translated ?? false}
          zoom={zoom}
        />
      </div>

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
