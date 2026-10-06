import { useEffect, useState } from 'react'
import { AlertTriangle, ShieldAlert, CheckCircle2, ChevronLeft, ChevronRight } from 'lucide-react'

const SEV = {
  CRITICAL: { label: 'Nghiêm trọng', bg: 'bg-red-600' },
  HIGH:     { label: 'Cao',         bg: 'bg-orange-500' },
  MEDIUM:   { label: 'Trung bình',  bg: 'bg-amber-500' },
  LOW:      { label: 'Thấp',        bg: 'bg-slate-500' },
  INFO:     { label: 'Thông báo',   bg: 'bg-slate-400' },
}

const PAGE_SIZE = 3

function SevBadge({ sev }) {
  const s = SEV[sev] || SEV.INFO
  return (
    <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-bold text-white ${s.bg}`}>
      {s.label}
    </span>
  )
}

/**
 * Danh sách cảnh báo rủi ro, mỗi trang hiển thị tối đa 3 mục.
 * Bấm vào một cảnh báo sẽ cuộn tới và làm nổi bật các ô dữ liệu tương ứng
 * trong bảng đối chiếu 3 cột PO - Invoice - Payment Request.
 */
export default function FindingsPanel({ findings, onSelectFinding }) {
  const [page, setPage] = useState(0)

  const list = findings || []
  const totalPages = Math.max(1, Math.ceil(list.length / PAGE_SIZE))

  // Khi danh sách findings thay đổi (đổi bộ chứng từ), luôn quay về trang đầu.
  useEffect(() => { setPage(0) }, [list.length])

  // Chặn trang vượt quá giới hạn nếu số findings bị thay đổi.
  const safePage = Math.min(page, totalPages - 1)
  const start = safePage * PAGE_SIZE
  const visible = list.slice(start, start + PAGE_SIZE)

  if (!list.length) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-6 text-center shadow-sm">
        <CheckCircle2 className="mx-auto h-8 w-8 text-emerald-500" />
        <div className="mt-2 text-sm font-semibold text-slate-800">Không phát hiện vi phạm</div>
        <p className="mt-1 text-xs text-slate-500">Bộ chứng từ đã vượt qua toàn bộ 13 quy tắc kiểm tra R0-R12.</p>
      </div>
    )
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <ShieldAlert className="h-4 w-4 text-red-500" />
          <h3 className="text-sm font-semibold text-slate-800">Cảnh báo rủi ro</h3>
          <span className="rounded-full bg-red-100 px-2 py-0.5 text-[11px] font-bold text-red-700">
            {list.length} vi phạm
          </span>
        </div>
        {totalPages > 1 && (
          <div className="text-[11px] font-medium text-slate-500">
            Trang {safePage + 1}/{totalPages}
          </div>
        )}
      </div>

      <ul className="divide-y divide-slate-100">
        {visible.map((f, i) => (
          <li key={start + i}>
            <button
              type="button"
              onClick={() => onSelectFinding?.(f)}
              className="flex w-full cursor-pointer flex-col gap-1.5 px-4 py-3 text-left transition hover:bg-red-50/60"
            >
              <div className="flex w-full flex-wrap items-center gap-2">
                <SevBadge sev={f.severity} />
                <span className="text-[11px] font-mono font-bold text-slate-600">
                  {(f.rule_id || '').split('_')[0]}
                </span>
                <span className="text-xs text-slate-500">{f.rule_name}</span>
              </div>
              <p className="text-xs leading-relaxed text-slate-800">{f.reason}</p>
              {(f.expected_value || f.actual_value) && (
                <p className="text-[11px] text-slate-500">
                  Kỳ vọng: <b className="text-slate-700">{f.expected_value ?? '—'}</b>
                  {'   '}Thực tế: <b className="text-slate-700">{f.actual_value ?? '—'}</b>
                </p>
              )}
              {f.suggestion && (
                <p className="text-[11px] text-indigo-600">→ {f.suggestion}</p>
              )}
            </button>
          </li>
        ))}
      </ul>

      {totalPages > 1 && (
        <div className="flex items-center justify-between border-t px-4 py-2.5">
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={safePage === 0}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <ChevronLeft className="h-3.5 w-3.5" /> Trang trước
          </button>

          <div className="flex items-center gap-1.5">
            {Array.from({ length: totalPages }, (_, p) => (
              <button
                key={p}
                type="button"
                aria-label={`Đến trang ${p + 1}`}
                onClick={() => setPage(p)}
                className={`h-2 rounded-full transition-all ${
                  p === safePage ? 'w-6 bg-red-600' : 'w-2 bg-slate-300 hover:bg-slate-400'
                }`}
              />
            ))}
          </div>

          <button
            type="button"
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={safePage >= totalPages - 1}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Trang sau <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
    </div>
  )
}
