import { useState, useEffect, useRef } from 'react'
import { Building2, Users } from 'lucide-react'

function VerdictBadge({ v }) {
  const s = { REJECTED: 'bg-red-600 text-white', WARNING: 'bg-amber-500 text-white', PASSED: 'bg-emerald-600 text-white', INFO: 'bg-slate-300' }[v] || 'bg-slate-700 text-white'
  return <span className={`inline-flex rounded-full px-3 py-1 text-xs font-bold ${s}`}>{v}</span>
}

const TABS = [
  { id: 'general',  label: 'General Info' },
  { id: 'parties',  label: 'Buyer & Seller' },
  { id: 'items',    label: 'Line Items' },
  { id: 'payment',  label: 'Payment & Bank' },
]

/** Ma tran 3 cot: PO | Invoice | Payment Request. */
export default function SideBySideViewer({ batch, findings, flashKey }) {
  const [tab, setTab] = useState('general')
  const rootRef = useRef(null)

  // Khi bam mot card trong FindingsPanel, browser se phat custom event `audit:flash`.
  useEffect(() => {
    function onFlash(e) {
      const field = e?.detail?.field
      if (!field || !rootRef.current) return
      const el = rootRef.current.querySelector(`[data-field="${field}"]`)
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' })
        el.classList.remove('flash-highlight', 'flash-warn')
        // dung requestAnimationFrame de force reflow
        void el.offsetWidth
        const sev = (e.detail.severity || '').toUpperCase()
        const klass = (sev === 'CRITICAL' || sev === 'HIGH') ? 'flash-highlight' : 'flash-warn'
        el.classList.add(klass)
        setTimeout(() => el.classList.remove(klass), 1600)
      }
    }
    window.addEventListener('audit:flash', onFlash)
    return () => window.removeEventListener('audit:flash', onFlash)
  }, [])

  const docs = batch?.documents || []
  const byType = Object.fromEntries(docs.map((d) => [d.doc_type, d]))

  const COLS = [
    { key: 'PO',             label: 'Purchase Order',     data: byType.PO },
    { key: 'INVOICE',        label: 'Invoice',            data: byType.INVOICE },
    { key: 'PAYMENT_REQUEST',label: 'Payment Request',    data: byType.PAYMENT_REQUEST },
  ]

  return (
    <div ref={rootRef} className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      {/* Header batch */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
        <div className="text-xs text-slate-500">
          Batch <span className="font-mono font-semibold text-slate-700">{(batch?.batch?.id || batch?.batch_id || '').slice(0, 12)}</span>
          <span className="mx-2">•</span>{batch?.batch?.status || batch?.status}
          <span className="mx-2">•</span>{batch?.batch?.created_at || batch?.created_at || ''}
        </div>
        <VerdictBadge v={batch?.overall_verdict || batch?.verdict?.overall_verdict || batch?.batch?.overall_verdict || 'PASSED'} />
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b bg-slate-50 px-3 py-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${tab === t.id ? 'bg-white text-indigo-700 shadow-sm ring-1 ring-slate-200' : 'text-slate-500 hover:text-slate-700'}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 divide-y md:grid-cols-3 md:divide-x md:divide-y-0">
        {COLS.map((col) => (
          <Column key={col.key} column={col} tab={tab} findings={findings} />
        ))}
      </div>
    </div>
  )
}

function money(v) {
  if (v == null) return '—'
  try { return Number(v).toLocaleString('vi-VN') } catch { return String(v) }
}

function Field({ flag, label, value, dataField }) {
  return (
    <div data-field={dataField} className={`rounded-lg border px-3 py-2 ${flag ? 'border-red-200 bg-red-50' : 'border-slate-100 bg-slate-50/60'}`}>
      <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-1 text-xs ${flag ? 'font-semibold text-red-700' : 'text-slate-800'}`}>{value ?? '—'}</div>
    </div>
  )
}

function Column({ column, tab, findings }) {
  const data = column.data
  const ex = data?.extracted || {}
  const isRejected = findings?.some((f) => f._docType === column.key) // placeholder
  if (!data) return (
    <div className="p-4">
      <div className="text-xs font-semibold text-slate-400">{column.label}</div>
      <div className="mt-6 text-center text-xs text-slate-400">Khong co file cho loai nay.</div>
    </div>
  )

  const warn = data.warnings?.length ? data.warnings.join(' ') : ''
  return (
    <div className="p-3.5">
      <div className="text-xs font-semibold text-slate-700">{column.label}</div>
      <div className="mt-1 font-mono text-[11px] text-slate-400">{data.file_name}</div>
      {warn && <div className="mt-2 rounded-lg bg-amber-50 px-2 py-1.5 text-[11px] text-amber-800">{warn}</div>}
      {data.extraction_method && (
        <div className="mt-1 text-[11px] text-slate-400">Trich xuat: {data.extraction_method}{data.extraction_model ? ` • ${data.extraction_model}` : ''}</div>
      )}

      {tab === 'general' && (
        <div className="mt-3 space-y-2">
          <Field label="So chung tu" value={ex.doc_number} dataField={`${column.key}::doc_number`} />
          <Field label="Refs tham chieu" value={(ex.reference_numbers || []).join(', ') || '—'} dataField={`${column.key}::reference_numbers`} />
          <Field label="Ngay phat hanh" value={ex.issue_date} dataField={`${column.key}::issue_date`} />
          <Field label="Tien te" value={ex.currency} dataField={`${column.key}::currency`} />
          <Field label="Ngay han thanh toan" value={ex.due_date || '—'} dataField={`${column.key}::due_date`} />
          <Field label="Trang thai duyet" value={ex.approval_status || '—'} dataField={`${column.key}::approval_status`} />
        </div>
      )}

      {tab === 'parties' && (
        <div className="mt-3 space-y-2">
          <Field label="Ben mua" value={ex.buyer_name} dataField={`${column.key}::buyer_name`} />
          <Field label="Dia chi ben mua" value={ex.buyer_address} dataField={`${column.key}::buyer_address`} />
          <Field label="Ben ban / NCC" value={ex.seller_name} dataField={`${column.key}::seller_name`} />
          <Field label="Dia chi ben ban" value={ex.seller_address} dataField={`${column.key}::seller_address`} />
          <Field label="Nguoi de nghi / Phong ban" value={[ex.requester_name, ex.department].filter(Boolean).join(' — ') || '—'} dataField={`${column.key}::requester_name`} />
        </div>
      )}

      {tab === 'items' && (
        <div className="mt-3">
          <div className="overflow-auto">
            <table className="min-w-full text-xs">
              <thead><tr className="text-[11px] text-slate-500"><th className="px-1.5 py-1 text-left">Ma</th><th className="px-1.5 text-left">Mo ta</th><th className="px-1.5 text-right">SL</th><th className="px-1.5 text-right">Don gia</th><th className="px-1.5 text-right">Thanh tien</th></tr></thead>
              <tbody>
                {(ex.items || []).length ? ex.items.map((it, i) => (
                  <tr key={i} className="border-t border-slate-100">
                    <td className="px-1.5 py-1.5 font-mono text-[11px]">{it.item_code || '—'}</td>
                    <td className="px-1.5 text-[11px]">{it.description || '—'}</td>
                    <td className="px-1.5 text-right">{it.quantity ?? '—'}</td>
                    <td className="px-1.5 text-right">{money(it.unit_price)}</td>
                    <td className={`px-1.5 text-right ${it.quantity != null && it.unit_price != null && it.amount != null && Math.abs(it.quantity * it.unit_price - it.amount) > 1 ? 'font-bold text-red-600' : ''}`}>{money(it.amount)}</td>
                  </tr>
                )) : <tr><td colSpan={5} className="px-2 py-6 text-center text-slate-400">Khong co bang hang hoa.</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <Field label="Subtotal" value={money(ex.subtotal_amount)} dataField={`${column.key}::subtotal_amount`} />
            <Field label="VAT" value={[ex.vat_rate != null ? `${ex.vat_rate}%` : null, money(ex.vat_amount)].filter(Boolean).join(' — ') || '—'} dataField={`${column.key}::vat_amount`} />
            <Field label="Tong" value={money(ex.total_amount)} dataField={`${column.key}::total_amount`} />
            <Field label="So tien de nghi (PR)" value={money(ex.requested_payment_amount)} dataField={`${column.key}::requested_payment_amount`} />
          </div>
        </div>
      )}

      {tab === 'payment' && (
        <div className="mt-3 space-y-2">
          <Field label="Chu TK" value={ex.bank_beneficiary?.account_name} dataField={`${column.key}::bank_beneficiary.account_name`} />
          <Field label="So TK" value={ex.bank_beneficiary?.account_number} dataField={`${column.key}::bank_beneficiary.account_number`} />
          <Field label="Ngan hang" value={ex.bank_beneficiary?.bank_name} dataField={`${column.key}::bank_beneficiary.bank_name`} />
          <Field label="Tong hoa don" value={money(ex.total_amount)} dataField={`${column.key}::total_amount`} />
          <Field label="So tien de nghi" value={money(ex.requested_payment_amount)} dataField={`${column.key}::requested_payment_amount`} />
        </div>
      )}
    </div>
  )
}
