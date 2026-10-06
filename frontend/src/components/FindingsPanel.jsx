import { AlertTriangle, ShieldAlert, Info, CheckCircle2 } from 'lucide-react'

const SEV = {
  CRITICAL: { label: 'CRITICAL', bg: 'bg-red-600', sub: 'text-red-100', ring: 'ring-red-200' },
  HIGH:     { label: 'HIGH',     bg: 'bg-orange-500', sub: 'text-orange-50', ring: 'ring-orange-200' },
  MEDIUM:   { label: 'MEDIUM',   bg: 'bg-amber-500',  sub: 'text-amber-50',  ring: 'ring-amber-200' },
  LOW:      { label: 'LOW',      bg: 'bg-slate-500',  sub: 'text-slate-100', ring: 'ring-slate-200' },
  INFO:     { label: 'INFO',     bg: 'bg-slate-400',  sub: 'text-white',     ring: 'ring-slate-200' },
}

function SevBadge({ sev }) {
  const s = SEV[sev] || SEV.INFO
  return <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-bold text-white ${s.bg}`}>{s.label}</span>
}

/**
 * Tot hop finding tu backend + su kien scroll toi field lien quan tren 3 cot.
 * Click mot card trong panel -> smooth scroll toi o du lieu tren ma tran va nhap nhay.
 */
export default function FindingsPanel({ findings, onSelectFinding }) {
  const hasFailed = findings?.length
  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-2">
          {hasFailed ? <ShieldAlert className="h-4 w-4 text-red-500" /> : <CheckCircle2 className="h-4 w-4 text-emerald-500" />}
          <h3 className="text-sm font-semibold text-slate-800">
            Findings {hasFailed ? `(${hasFailed} vi pham)` : '(khong co vi pham)'}
          </h3>
        </div>
      </div>

      {!hasFailed ? (
        <div className="px-4 py-6 text-center text-sm text-slate-500">Ho so hop le. Khong co vi pham can xu ly.</div>
      ) : (
        <div className="space-y-2 p-3">
          {findings.map((f, i) => (
            <button
              key={i}
              onClick={() => onSelectFinding?.(f)}
              className="flex w-full cursor-pointer flex-col items-start gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-left shadow-sm hover:border-indigo-300 hover:bg-indigo-50/40"
            >
              <div className="flex w-full flex-wrap items-center gap-2">
                <SevBadge sev={f.severity} />
                <span className="text-xs font-semibold text-slate-700">{f.rule_id}</span>
                <span className="text-xs text-slate-500">{f.rule_name}</span>
              </div>
              <p className="text-xs leading-relaxed text-slate-800">{f.reason}</p>
              {(f.expected_value || f.actual_value) && (
                <p className="text-[11px] text-slate-500">
                  Ky vong: <b className="text-slate-700">{f.expected_value ?? '—'}</b>
                  {'  '} Thuc te: <b className="text-slate-700">{f.actual_value ?? '—'}</b>
                </p>
              )}
              {f.suggestion && <p className="text-[11px] text-indigo-600">→ {f.suggestion}</p>}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
