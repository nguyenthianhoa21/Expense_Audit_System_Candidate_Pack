import { ShieldAlert, CheckCircle2, AlertTriangle } from 'lucide-react'

function VerdictPill({ v }) {
  const m = { REJECTED: 'bg-red-600', WARNING: 'bg-amber-500', PASSED: 'bg-emerald-600' }[v] || 'bg-slate-600'
  const vi = { REJECTED: 'Từ chối', WARNING: 'Cảnh báo', PASSED: 'Đạt' }[v] || v
  return <span title={v} className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-bold text-white ${m}`}>{vi}</span>
}

/** Bảng lịch sử các bộ chứng từ đã kiểm tra, kèm số/tên chứng từ người dùng đã nhập. */
export default function HistoryView({ items, total, onView }) {
  if (!items?.length) return <div className="rounded-xl border bg-white px-4 py-6 text-center text-sm text-slate-500">Chưa có lịch sử kiểm tra.</div>
  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-800">Lịch sử kiểm tra</h3>
        <span className="text-xs text-slate-500">{total} bộ</span>
      </div>
      <table className="min-w-full text-xs">
        <thead className="bg-slate-50 text-[11px] text-slate-500">
          <tr><th className="px-3 py-2 text-left">Ngày giờ</th><th className="px-3 text-left">Số/Tên chứng từ</th><th className="px-3 text-left">Trạng thái</th><th className="px-3 text-left">Kết quả</th><th className="px-3 text-left">Tệp</th><th className="px-3"></th></tr>
        </thead>
        <tbody>
          {items.map((b) => (
            <tr key={b.id} className="border-t hover:bg-slate-50">
              <td className="px-3 py-2 font-mono text-[11px]">{new Date(b.created_at).toLocaleString('vi-VN')}</td>
              <td className="px-3 font-semibold text-slate-700">{b.reference_label || '—'}</td>
              <td className="px-3">{b.status}</td>
              <td className="px-3"><VerdictPill v={b.overall_verdict} /></td>
              <td className="px-3">{b.document_count}</td>
              <td className="px-3 text-right"><button onClick={() => onView(b.id)} className="rounded-lg bg-blue-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-800">Xem chi tiết</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
