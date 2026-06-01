"use client"

import { useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import Link from "next/link"
import { ChevronLeft, ChevronRight, ArrowLeft } from "lucide-react"

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

interface PageContent {
  page_number: number
  total_pages: number
  lang: string
  html: string
  prev_page: number | null
  next_page: number | null
}

interface BookInfo {
  title: string
  languages: string[]
}

const LANG_FLAG: Record<string, string> = { vi: "VI", en: "EN" }

export default function ChapterReaderPage(
  { params }: { params: { slug: string; page: string } }
) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const lang = searchParams.get("lang") ?? "vi"
  const pageNum = parseInt(params.page, 10)

  const [content, setContent] = useState<PageContent | null>(null)
  const [book, setBook] = useState<BookInfo | null>(null)
  const [error, setError] = useState("")

  useEffect(() => {
    fetch(`${API_URL}/api/books/${params.slug}`)
      .then((r) => (r.ok ? r.json() : null))
      .then(setBook)
      .catch(() => {})
  }, [params.slug])

  useEffect(() => {
    setError("")
    setContent(null)
    fetch(`${API_URL}/api/books/${params.slug}/pages/${pageNum}?lang=${lang}`)
      .then(async (r) => {
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? "Lỗi tải trang")
        return r.json()
      })
      .then((data: PageContent) => {
        setContent(data)
        window.scrollTo(0, 0)
      })
      .catch((e) => setError(e.message))
  }, [params.slug, pageNum, lang])

  function switchLang(newLang: string) {
    router.push(`/read/${params.slug}/${pageNum}?lang=${newLang}`)
  }

  return (
    <div>
      <header className="sticky top-0 bg-white/95 backdrop-blur border-b border-gray-200 px-4 py-3 flex items-center justify-between z-10">
        <Link href={`/read/${params.slug}`} className="flex items-center gap-1 text-sm text-gray-600 hover:text-indigo-600">
          <ArrowLeft size={16} /> {book?.title ?? "Sách"}
        </Link>
        <div className="flex items-center gap-3">
          <div className="flex gap-1">
            {(book?.languages ?? ["vi"]).map((l) => (
              <button key={l} onClick={() => switchLang(l)}
                      className={`text-xs px-2 py-1 rounded ${lang === l ? "bg-indigo-600 text-white" : "bg-gray-100 text-gray-500"}`}>
                {LANG_FLAG[l] ?? l.toUpperCase()}
              </button>
            ))}
          </div>
          {content && <span className="text-xs text-gray-400">{content.page_number}/{content.total_pages}</span>}
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-6 py-8">
        {error && <p className="text-red-500 text-sm">{error}</p>}
        {!content && !error && <p className="text-gray-400 text-sm">Đang tải...</p>}
        {content && (
          <article className="prose max-w-none"
                   dangerouslySetInnerHTML={{ __html: content.html }} />
        )}
      </main>

      {content && (
        <nav className="max-w-2xl mx-auto px-6 pb-12 flex justify-between">
          {content.prev_page ? (
            <Link href={`/read/${params.slug}/${content.prev_page}?lang=${lang}`}
                  className="flex items-center gap-1 text-sm text-indigo-600 hover:underline">
              <ChevronLeft size={16} /> Trang trước
            </Link>
          ) : <span />}
          {content.next_page ? (
            <Link href={`/read/${params.slug}/${content.next_page}?lang=${lang}`}
                  className="flex items-center gap-1 text-sm text-indigo-600 hover:underline">
              Trang sau <ChevronRight size={16} />
            </Link>
          ) : <span />}
        </nav>
      )}
    </div>
  )
}
