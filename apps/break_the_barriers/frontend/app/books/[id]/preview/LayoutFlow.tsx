export interface FlowLayoutProps {
  docId: string
  apiUrl: string
  zoom: number
  lang?: "goc" | "vi"
}

export default function LayoutFlow({ docId, apiUrl, zoom, lang = "goc" }: FlowLayoutProps) {
  // Gốc = HTML element thật giữ layout; Dịch (vi) = text dịch theo block, cùng nền.
  const src = lang === "vi"
    ? `${apiUrl}/api/docs/${docId}/htmlflow?lang=vi`
    : `${apiUrl}/api/docs/${docId}/htmlflow`
  return (
    <main className="flex-1 min-h-0 bg-[#f4f4f5]">
      <iframe
        key={`htmlflow-${lang}`}
        src={src}
        className="w-full h-full border-none block"
        title="Tài liệu liền mạch"
        sandbox="allow-same-origin allow-scripts"
        onLoad={(e) =>
          e.currentTarget.contentWindow?.postMessage({ type: "btb-zoom", zoom }, "*")
        }
      />
    </main>
  )
}
