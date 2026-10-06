import { ShieldAlert, CheckCircle2, AlertTriangle } from 'lucide-react'

function VerdictPill({ v }) {
  const m = { REJECTED: 'bg-red-600', WARNING: 'bg-amber-500', PASSED: 'bg-emerald-600' }[v] || 'bg-slate-600'
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-bold text-white ${m}`}>{v}</span>
}

export default function HistoryView({ items, total, onView }) {
  if (!items?.length) return <div className="rounded-xl border bg-white px-4 py-6 text-center text-sm text-slate-500">Chua co lich su audit.</div>
  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-800">Audit History</h3>
        <span className="text-xs text-slate-500">{total} batch</span>
      </div>
      <table className="min-w-full text-xs">
        <thead className="bg-slate-50 text-[11px] text-slate-500">
          <tr><th className="px-3 py-2 text-left">Ngay</th><th className="px-3 text-left">Status</th><th className="px-3 text-left">Verdict</th><th className="px-3 text-left">Files</th><th className="px-3"></th></tr>
        </thead>
        <tbody>
          {items.map((b) => (
            <tr key={b.id} className="border-t hover:bg-slate-50">
              <td className="px-3 py-2 font-mono text-[11px]">{new Date(b.created_at).toLocaleString('vi-VN')}</td>
              <td className="px-3">{b.status}</td>
              <td className="px-3"><VerdictPill v={b.overall_verdict} /></td>
              <td className="px-3">{b.document_count}</td>
              <td className="px-3 text-right"><button onClick={() => onView(b.id)} className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700">Xem</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
