import Link from "next/link"
import { notFound } from "next/navigation"
import type { Metadata } from "next"

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

interface BookInfo {
  slug: string
  title: string
  description: string
  cover_url: string | null
  languages: string[]
  is_public: boolean
  page_count: number
  published_at: string
  book_url: string
}

async function fetchBook(slug: string): Promise<BookInfo | null> {
  try {
    const res = await fetch(`${API_URL}/api/books/${slug}`, { cache: "no-store" })
    if (!res.ok) return null
    return res.json()
  } catch {
    return null
  }
}

function gradientFor(slug: string): string {
  let hash = 0
  for (let i = 0; i < slug.length; i++) hash = slug.charCodeAt(i) + ((hash << 5) - hash)
  const h1 = Math.abs(hash) % 360
  const h2 = (h1 + 40) % 360
  return `linear-gradient(135deg, hsl(${h1},65%,55%), hsl(${h2},65%,45%))`
}

function resolveCover(coverUrl: string): string {
  return coverUrl.startsWith("http") ? coverUrl : `${API_URL}${coverUrl}`
}

export async function generateMetadata(
  { params }: { params: { slug: string } }
): Promise<Metadata> {
  const book = await fetchBook(params.slug)
  if (!book) return { title: "Không tìm thấy sách" }
  return {
    title: book.title,
    description: book.description,
    openGraph: {
      title: book.title,
      description: book.description,
      images: book.cover_url ? [resolveCover(book.cover_url)] : [],
      type: "book",
    },
  }
}

const LANG_LABEL: Record<string, string> = { vi: "🇻🇳 Tiếng Việt", en: "🇺🇸 English" }

export default async function BookLandingPage(
  { params }: { params: { slug: string } }
) {
  const book = await fetchBook(params.slug)
  if (!book) notFound()

  return (
    <div className="max-w-2xl mx-auto px-6 py-10">
      <div
        className="rounded-xl overflow-hidden mb-6 h-56 flex items-end p-6 text-white"
        style={
          book.cover_url
            ? {
                backgroundImage: `url(${resolveCover(book.cover_url)})`,
                backgroundSize: "cover",
                backgroundPosition: "center",
              }
            : { background: gradientFor(book.slug) }
        }
      >
        <h1 className="text-3xl font-bold drop-shadow">{book.title}</h1>
      </div>

      <div className="flex items-center gap-3 text-sm text-gray-500 mb-4">
        <span>{book.languages.map((l) => LANG_LABEL[l] ?? l).join(" · ")}</span>
        <span>•</span>
        <span>{book.page_count} trang</span>
      </div>

      {book.description && <p className="text-gray-700 mb-6">{book.description}</p>}

      <Link
        href={`/read/${book.slug}/1`}
        className="inline-block bg-indigo-600 text-white rounded-lg px-6 py-3 font-semibold hover:bg-indigo-700"
      >
        Bắt đầu đọc →
      </Link>

      <div className="mt-10 border-t border-gray-100 pt-6">
        <h2 className="text-xs font-bold text-gray-400 uppercase mb-3">Mục lục</h2>
        <div className="flex flex-wrap gap-2">
          {Array.from({ length: book.page_count }, (_, i) => i + 1).map((n) => (
            <Link
              key={n}
              href={`/read/${book.slug}/${n}`}
              className="text-sm border border-gray-200 rounded-lg px-3 py-1 text-gray-600 hover:border-indigo-400 hover:text-indigo-600"
            >
              Trang {n}
            </Link>
          ))}
        </div>
      </div>
    </div>
  )
}
