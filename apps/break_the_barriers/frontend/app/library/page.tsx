import Link from "next/link"
import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "Thư viện sách | Break The Barriers",
  description: "Khám phá các web-book song ngữ được xuất bản bởi cộng đồng.",
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

interface BookInfo {
  slug: string
  title: string
  description: string
  cover_url: string | null
  languages: string[]
  page_count: number
  published_at: string
  book_url: string
}

interface BookListResponse {
  books: BookInfo[]
  total: number
  page: number
  per_page: number
}

async function fetchBooks(q: string, lang: string, page: number): Promise<BookListResponse> {
  const params = new URLSearchParams()
  if (q) params.set("q", q)
  if (lang) params.set("lang", lang)
  params.set("page", String(page))
  params.set("per_page", "12")
  try {
    const res = await fetch(`${API_URL}/api/books?${params}`, { cache: "no-store" })
    if (!res.ok) return { books: [], total: 0, page: 1, per_page: 12 }
    return res.json()
  } catch {
    return { books: [], total: 0, page: 1, per_page: 12 }
  }
}

function gradientFor(slug: string): string {
  let hash = 0
  for (let i = 0; i < slug.length; i++) hash = slug.charCodeAt(i) + ((hash << 5) - hash)
  const h1 = Math.abs(hash) % 360
  const h2 = (h1 + 40) % 360
  return `linear-gradient(135deg, hsl(${h1},65%,55%), hsl(${h2},65%,45%))`
}

function resolveCover(coverUrl: string): string | null {
  if (coverUrl.startsWith("https://") || coverUrl.startsWith("http://")) return coverUrl
  if (coverUrl.startsWith("/")) return `${API_URL}${coverUrl}`
  return null
}

const LANG_LABEL: Record<string, string> = { vi: "🇻🇳 VI", en: "🇺🇸 EN" }

const LANG_OPTIONS = [
  { value: "", label: "Tất cả" },
  { value: "vi", label: "🇻🇳 Tiếng Việt" },
  { value: "en", label: "🇺🇸 English" },
]

function pageHref(q: string, lang: string, p: number): string {
  const params = new URLSearchParams()
  if (q) params.set("q", q)
  if (lang) params.set("lang", lang)
  params.set("page", String(p))
  return `/library?${params}`
}

export default async function LibraryPage({
  searchParams,
}: {
  searchParams: { q?: string; lang?: string; page?: string }
}) {
  const q = searchParams.q ?? ""
  const lang = searchParams.lang ?? ""
  const page = Math.max(1, parseInt(searchParams.page ?? "1", 10) || 1)

  const data = await fetchBooks(q, lang, page)
  const totalPages = Math.ceil(data.total / data.per_page)

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-8">
        <div className="max-w-5xl mx-auto">
          <h1 className="text-3xl font-bold text-gray-900 mb-1">Thư viện sách</h1>
          <p className="text-gray-500 text-sm mb-6">
            {data.total} web-book song ngữ được cộng đồng xuất bản
          </p>

          {/* Search + filter form */}
          <form className="flex flex-col sm:flex-row gap-3">
            <input
              name="q"
              defaultValue={q}
              placeholder="Tìm kiếm theo tiêu đề..."
              className="flex-1 border border-gray-300 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
            <select
              name="lang"
              defaultValue={lang}
              className="border border-gray-300 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            >
              {LANG_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <button
              type="submit"
              className="bg-indigo-600 text-white rounded-lg px-5 py-2 text-sm font-semibold hover:bg-indigo-700"
            >
              Tìm
            </button>
          </form>
        </div>
      </div>

      {/* Book grid */}
      <div className="max-w-5xl mx-auto px-6 py-8">
        {data.books.length === 0 ? (
          <p className="text-center text-gray-400 py-20 text-sm">
            {q || lang ? "Không tìm thấy sách phù hợp." : "Chưa có sách nào được xuất bản."}
          </p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-6">
            {data.books.map((book) => (
              <Link key={book.slug} href={`/read/${book.slug}`} className="group block">
                <div className="bg-white rounded-xl overflow-hidden shadow-sm hover:shadow-md transition-shadow border border-gray-100">
                  {/* Cover */}
                  <div
                    className="h-36 flex items-end p-3"
                    style={(() => {
                      const cover = book.cover_url ? resolveCover(book.cover_url) : null
                      return cover
                        ? { backgroundImage: `url(${cover})`, backgroundSize: "cover", backgroundPosition: "center" }
                        : { background: gradientFor(book.slug) }
                    })()}
                  >
                    <div className="flex gap-1 flex-wrap">
                      {book.languages.map((l) => (
                        <span
                          key={l}
                          className="text-xs bg-black/30 text-white rounded px-2 py-0.5 backdrop-blur-sm"
                        >
                          {LANG_LABEL[l] ?? l.toUpperCase()}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Info */}
                  <div className="p-4">
                    <h2 className="font-semibold text-gray-800 text-sm leading-snug group-hover:text-indigo-600 line-clamp-2 mb-1">
                      {book.title}
                    </h2>
                    {book.description && (
                      <p className="text-xs text-gray-500 line-clamp-2 mb-2">{book.description}</p>
                    )}
                    <span className="text-xs text-gray-400">{book.page_count} trang</span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex justify-center gap-3 mt-10">
            {page > 1 && (
              <Link
                href={pageHref(q, lang, page - 1)}
                className="text-sm text-indigo-600 hover:underline"
              >
                ← Trang trước
              </Link>
            )}
            <span className="text-sm text-gray-400">
              {page} / {totalPages}
            </span>
            {page < totalPages && (
              <Link
                href={pageHref(q, lang, page + 1)}
                className="text-sm text-indigo-600 hover:underline"
              >
                Trang sau →
              </Link>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
