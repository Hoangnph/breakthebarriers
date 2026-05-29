"use client"

import { Suspense, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { Check, X, ArrowLeft } from "lucide-react"

const PLANS = [
  {
    name: "Free",
    price: "$0",
    period: "/tháng",
    pages: "20 trang/lần",
    features: ["1 upload", "PDF & EPUB", "AI dịch Gemini"],
    missing: ["Unlimited uploads", "Web-Book", "API access", "Watermark-free"],
    cta: "Đang dùng",
    ctaDisabled: true,
    highlight: false,
  },
  {
    name: "Pro",
    price: "$29",
    period: "/tháng",
    pages: "500 trang/tháng",
    features: ["Unlimited uploads", "PDF & EPUB", "AI dịch Gemini", "Web-Book", "Không watermark"],
    missing: ["API access"],
    cta: "Chọn Pro",
    ctaDisabled: false,
    highlight: true,
    badge: "Phổ biến nhất",
  },
  {
    name: "Enterprise",
    price: "$99",
    period: "/tháng",
    pages: "2000 trang/tháng",
    features: ["Tất cả tính năng Pro", "API access", "Priority queue", "Custom domain"],
    missing: [],
    cta: "Liên hệ",
    ctaDisabled: false,
    highlight: false,
  },
] as const

function PricingContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const quotaExceeded = searchParams.get("reason") === "quota"
  const [showModal, setShowModal] = useState(false)

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center gap-3">
        <button onClick={() => router.push("/dashboard")} className="text-gray-500 hover:text-gray-700">
          <ArrowLeft size={18} />
        </button>
        <span className="font-bold text-indigo-600">Break The Barriers</span>
      </header>

      <div className="max-w-4xl mx-auto px-6 py-12">
        {quotaExceeded && (
          <div className="mb-6 bg-orange-50 border border-orange-200 rounded-lg px-4 py-3 text-sm text-orange-700">
            Bạn đã hết quota tháng này. Nâng cấp để tiếp tục dịch sách.
          </div>
        )}

        <div className="text-center mb-10">
          <h1 className="text-2xl font-bold text-gray-900">Chọn gói phù hợp</h1>
          <p className="text-gray-500 mt-2 text-sm">Bắt đầu miễn phí, nâng cấp bất cứ lúc nào</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {PLANS.map((plan) => (
            <div
              key={plan.name}
              className={`bg-white rounded-xl p-6 border-2 relative flex flex-col ${
                plan.highlight ? "border-indigo-500 shadow-lg" : "border-gray-200"
              }`}
            >
              {"badge" in plan && plan.badge && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-indigo-600 text-white text-xs px-3 py-1 rounded-full whitespace-nowrap">
                  {plan.badge}
                </span>
              )}
              <div className="mb-4">
                <h2 className={`font-bold text-lg ${plan.highlight ? "text-indigo-600" : "text-gray-800"}`}>
                  {plan.name}
                </h2>
                <div className="mt-1">
                  <span className="text-3xl font-bold text-gray-900">{plan.price}</span>
                  <span className="text-gray-400 text-sm">{plan.period}</span>
                </div>
                <p className="text-xs text-gray-500 mt-1">{plan.pages}</p>
              </div>

              <ul className="space-y-2 mb-6 flex-1">
                {plan.features.map((f) => (
                  <li key={f} className="flex items-center gap-2 text-sm text-gray-700">
                    <Check size={14} className="text-green-500 shrink-0" /> {f}
                  </li>
                ))}
                {plan.missing.map((f) => (
                  <li key={f} className="flex items-center gap-2 text-sm text-gray-400">
                    <X size={14} className="shrink-0" /> {f}
                  </li>
                ))}
              </ul>

              <button
                onClick={() => {
                  if (plan.name === "Enterprise") {
                    window.location.href = "mailto:contact@breakthebarriers.app"
                  } else if (!plan.ctaDisabled) {
                    setShowModal(true)
                  }
                }}
                disabled={plan.ctaDisabled}
                className={`w-full py-2 rounded text-sm font-medium transition-colors ${
                  plan.highlight
                    ? "bg-indigo-600 text-white hover:bg-indigo-700"
                    : plan.ctaDisabled
                    ? "border border-gray-300 text-gray-400 cursor-default"
                    : "border border-indigo-600 text-indigo-600 hover:bg-indigo-50"
                }`}
              >
                {plan.cta}
              </button>
            </div>
          ))}
        </div>
      </div>

      {showModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl p-6 max-w-sm w-full shadow-xl">
            <h3 className="font-bold text-gray-900 mb-2">Sắp ra mắt 🚀</h3>
            <p className="text-sm text-gray-600 mb-4">
              Tính năng billing đang được phát triển. Liên hệ email để được nâng cấp thủ công:
            </p>
            <a
              href="mailto:contact@breakthebarriers.app"
              className="block w-full text-center bg-indigo-600 text-white py-2 rounded text-sm hover:bg-indigo-700"
            >
              Liên hệ qua email
            </a>
            <button onClick={() => setShowModal(false)} className="w-full mt-2 text-sm text-gray-400 hover:text-gray-600">
              Đóng
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default function PricingPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-gray-50 flex items-center justify-center"><span className="text-gray-400">Loading...</span></div>}>
      <PricingContent />
    </Suspense>
  )
}
