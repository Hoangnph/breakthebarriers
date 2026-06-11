export interface FlowLayoutProps {
  docId: string
  apiUrl: string
  zoom: number
}

export default function LayoutFlow({ docId, apiUrl, zoom }: FlowLayoutProps) {
  // Original PDF → HTML element thật (positioned), xếp dọc liền mạch.
  const src = `${apiUrl}/api/docs/${docId}/htmlflow`
  return (
    <main className="flex-1 min-h-0 bg-[#f4f4f5]">
      <iframe
        key="htmlflow"
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
