import { useState, useEffect, useRef } from 'react'
import { sanitizeWarnings } from '../utils/safeWarnings.js'

function VerdictBadge({ v }) {
  const s = { REJECTED: 'bg-red-600 text-white', WARNING: 'bg-amber-500 text-white', PASSED: 'bg-emerald-600 text-white', INFO: 'bg-slate-300' }[v] || 'bg-slate-700 text-white'
  return <span className={`inline-flex rounded-full px-3 py-1 text-xs font-bold ${s}`}>{v}</span>
}

const TABS = [
  { id: 'general',  label: 'Thông tin chung' },
  { id: 'parties',  label: 'Bên mua & Nhà cung cấp' },
  { id: 'items',    label: 'Chi tiết hàng hoá' },
  { id: 'payment',  label: 'Thanh toán & Ngân hàng' },
]

/** Lớp hiển thị mức độ rủi ro áp cho từng ô — backend là nguồn duy nhất cho highlight_targets. */
function riskClass(sev) {
  const v = (sev || '').toUpperCase()
  if (v === 'CRITICAL') return 'cell-risk-critical'
  if (v === 'HIGH')     return 'cell-risk-high'
  if (v === 'MEDIUM')   return 'cell-risk-medium'
  if (v === 'INFO')     return 'cell-risk-info'
  return ''
}

/**
 * Ma trận 3 cột PO | Invoice | Payment Request.
 * - Mỗi ô dữ liệu mang thuộc tính data-field="<DOC_TYPE>::<field>".
 * - FindingsPanel phát sự kiện audit:flash để cuộn + làm nổi bật ô vi phạm.
 */
export default function SideBySideViewer({ batch }) {
  const [tab, setTab] = useState('general')
  const rootRef = useRef(null)

  // Khi FindingsPanel yêu cầu làm nổi bật: chuyển đúng tab rồi cuộn và nhấp nháy ô tương ứng.
  useEffect(() => {
    const TABS_FOR_FIELD = {
      'items': 'items', 'items.__table': 'items',
      'subtotal_amount': 'items', 'vat_amount': 'items', 'total_amount': 'items',
      'requested_payment_amount': 'items',
      'buyer_name': 'parties', 'buyer_address': 'parties',
      'seller_name': 'parties', 'seller_address': 'parties',
      'requester_name': 'parties',
      'bank_beneficiary': 'payment', 'bank_beneficiary.account_number': 'payment',
      'bank_beneficiary.account_name': 'payment', 'bank_beneficiary.bank_name': 'payment',
      'doc_number': 'general', 'reference_numbers': 'general', 'issue_date': 'general',
      'currency': 'general', 'due_date': 'general', 'approval_status': 'general',
    }
    function onFlash(e) {
      const field = e?.detail?.field
      if (!field || !rootRef.current) return
      const parts = field.split('::')
      const fpath = parts.slice(1).join('::') || field
      const root = fpath.split('.')[0]
      const tab = TABS_FOR_FIELD[fpath] || TABS_FOR_FIELD[root]
      if (tab) setTab(tab)
      // Đợi React đổi tab xong rồi mới tìm ô.
      const tries = [80, 220, 420]
      tries.forEach((ms, idx) => {
        setTimeout(() => {
          // Với items: nháy cả bảng vì từng dòng không có data-field riêng.
          let el = rootRef.current?.querySelector(`[data-field="${field}"]`)
          if (!el && fpath.startsWith('items')) {
            el = rootRef.current?.querySelector(`[data-field="${parts[0]}::items.__table"]`)
              || rootRef.current?.querySelector(`[data-field="${parts[0]}::items"]`)
          }
          if (!el && rootRef.current) {
            const first = fpath.split('.')[0]
            el = rootRef.current.querySelector(`[data-field^="${parts[0]}::${first}"]`)
          }
          if (!el && idx === tries.length - 1) return
          if (!el) return
          el.scrollIntoView({ behavior: 'smooth', block: 'center' })
          el.classList.remove('flash-highlight', 'flash-warn')
          void el.offsetWidth
          const sev = (e.detail.severity || '').toUpperCase()
          const klass = (sev === 'CRITICAL' || sev === 'HIGH') ? 'flash-highlight' : 'flash-warn'
          el.classList.add(klass)
          setTimeout(() => el.classList.remove(klass), 1600)
        }, ms)
      })
    }
    window.addEventListener('audit:flash', onFlash)
    return () => window.removeEventListener('audit:flash', onFlash)
  }, [])

  const docs = batch?.documents || []
  const byType = Object.fromEntries(docs.map((d) => [d.doc_type, d]))

  const COLS = [
    { key: 'PO',             label: 'Purchase Order',     data: byType.PO },
    { key: 'INVOICE',        label: 'Hoá đơn',            data: byType.INVOICE },
    { key: 'PAYMENT_REQUEST',label: 'Đề nghị thanh toán', data: byType.PAYMENT_REQUEST },
  ]

  return (
    <div ref={rootRef} className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
        <div className="text-xs text-slate-500">
          Mã bộ <span className="font-mono font-semibold text-slate-700">{(batch?.batch?.id || batch?.batch_id || '').slice(0, 12)}</span>
          {batch?.reference_label && (
            <> <span className="mx-2">•</span><span className="font-semibold text-slate-700">{batch.reference_label}</span></>
          )}
          {batch?.batch?.reference_label && !batch?.reference_label && (
            <> <span className="mx-2">•</span><span className="font-semibold text-slate-700">{batch.batch.reference_label}</span></>
          )}
          <span className="mx-2">•</span>{batch?.batch?.status || batch?.status}
          <span className="mx-2">•</span>{batch?.batch?.created_at || batch?.created_at || ''}
        </div>
        <VerdictBadge v={batch?.overall_verdict || batch?.verdict?.overall_verdict || batch?.batch?.overall_verdict || 'PASSED'} />
      </div>

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

      <div className="grid grid-cols-1 divide-y md:grid-cols-3 md:divide-x md:divide-y-0">
        {COLS.map((col) => (
          <Column key={col.key} column={col} tab={tab} findings={batch?.findings || []} />
        ))}
      </div>
    </div>
  )
}

function money(v) {
  if (v == null) return '—'
  try { return Number(v).toLocaleString('vi-VN') } catch { return String(v) }
}

function Field({ flag, sev, label, value, dataField }) {
  const rc = riskClass(sev)
  return (
    <div data-field={dataField} className={`rounded-lg border px-3 py-2 transition-colors ${rc || (flag ? 'border-red-200 bg-red-50' : 'border-slate-100 bg-slate-50/60')}`}>
      <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-1 text-xs ${rc.includes('risk') ? 'font-semibold' : ''} ${flag ? 'font-semibold text-red-700' : ''} ${!rc ? 'text-slate-800' : ''}`}>{value ?? '—'}</div>
    </div>
  )
}

function isFlagged(docKey, field, findings) {
  // Tìm mức độ nghiêm trọng cao nhất tác động tới ô này.
  // field = "items" sẽ khớp cả target "items" lẫn "items.__table" từ backend.
  const base = field.split('.')[0]
  const want = [`${docKey}::${field}`, `${docKey}::${base}`, `${docKey}::${base}.__table`]
  let max = null
  for (const f of findings || []) {
    for (const t of f.highlight_targets || []) {
      if (want.includes(t)) {
        const s = (f.severity || '').toUpperCase()
        const rank = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1, INFO: 0 }[s] ?? -1
        const cur  = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1, INFO: 0 }[max] ?? -1
        if (rank > cur) max = s
      }
    }
  }
  return max
}

function Column({ column, tab, findings }) {
  const data = column.data
  const ex = data?.extracted || {}
  if (!data) return (
    <div className="p-4">
      <div className="text-xs font-semibold text-slate-400">{column.label}</div>
      <div className="mt-6 text-center text-xs text-slate-400">Không có tệp cho loại này.</div>
    </div>
  )

  const warnList = sanitizeWarnings(data.warnings)
  const warn = warnList.length ? warnList.join(' ') : ''
  const f = (field) => isFlagged(column.key, field, findings)

  return (
    <div className="p-3.5">
      <div className="text-xs font-semibold text-slate-700">{column.label}</div>
      <div className="mt-1 font-mono text-[11px] text-slate-400">{data.file_name}</div>
      {warn && <div className="mt-2 rounded-lg bg-amber-50 px-2 py-1.5 text-[11px] text-amber-800">{warn}</div>}
      {data.extraction_method && (
        <div className="mt-1 text-[11px] text-slate-400">Trích xuất: {data.extraction_method}{data.extraction_model ? ` • ${data.extraction_model}` : ''}</div>
      )}

      {tab === 'general' && (
        <div className="mt-3 space-y-2">
          <Field label="Số chứng từ" sev={f('doc_number')} value={ex.doc_number} dataField={`${column.key}::doc_number`} />
          <Field label="Tham chiếu" sev={f('reference_numbers')} value={(ex.reference_numbers || []).join(', ') || '—'} dataField={`${column.key}::reference_numbers`} />
          <Field label="Ngày phát hành" sev={f('issue_date')} value={ex.issue_date} dataField={`${column.key}::issue_date`} />
          <Field label="Tiền tệ" sev={f('currency')} value={ex.currency} dataField={`${column.key}::currency`} />
          <Field label="Ngày hết hạn thanh toán" sev={f('due_date')} value={ex.due_date || '—'} dataField={`${column.key}::due_date`} />
          <Field label="Trạng thái phê duyệt" sev={f('approval_status')} value={ex.approval_status || '—'} dataField={`${column.key}::approval_status`} />
        </div>
      )}

      {tab === 'parties' && (
        <div className="mt-3 space-y-2">
          <Field label="Bên mua" sev={f('buyer_name')} value={ex.buyer_name} dataField={`${column.key}::buyer_name`} />
          <Field label="Địa chỉ bên mua" sev={f('buyer_address')} value={ex.buyer_address} dataField={`${column.key}::buyer_address`} />
          <Field label="Bên bán / NCC" sev={f('seller_name')} value={ex.seller_name} dataField={`${column.key}::seller_name`} />
          <Field label="Địa chỉ bên bán" sev={f('seller_address')} value={ex.seller_address} dataField={`${column.key}::seller_address`} />
          <Field label="Người đề nghị / Phòng ban" sev={f('requester_name')} value={[ex.requester_name, ex.department].filter(Boolean).join(' — ') || '—'} dataField={`${column.key}::requester_name`} />
        </div>
      )}

      {tab === 'items' && (
        <div className="mt-3">
          <div className="overflow-auto">
            <div data-field={`${column.key}::items.__table`} className={`overflow-auto rounded-lg ${riskClass(f('items')) || ''}`}>
            <table className="min-w-full text-xs">
              <thead><tr className="text-[11px] text-slate-500"><th className="px-1.5 py-1 text-left">Mã</th><th className="px-1.5 text-left">Mô tả</th><th className="px-1.5 text-right">SL</th><th className="px-1.5 text-right">Đơn giá</th><th className="px-1.5 text-right">Thành tiền</th></tr></thead>
              <tbody>
                {(ex.items || []).length ? ex.items.map((it, i) => {
                  const wrong = it.quantity != null && it.unit_price != null && it.amount != null && Math.abs(it.quantity * it.unit_price - it.amount) > 1
                  return (
                    <tr key={i} className={`border-t border-slate-100 ${wrong ? 'bg-red-50' : ''}`}>
                      <td className="px-1.5 py-1.5 font-mono text-[11px]">{it.item_code || '—'}</td>
                      <td className="px-1.5 text-[11px]">{it.description || '—'}</td>
                      <td className="px-1.5 text-right">{it.quantity ?? '—'}</td>
                      <td className="px-1.5 text-right">{money(it.unit_price)}</td>
                      <td className={`px-1.5 text-right ${wrong ? 'font-bold text-red-600' : ''}`}>{money(it.amount)}</td>
                    </tr>
                  )
                }) : <tr><td colSpan={5} className="px-2 py-6 text-center text-slate-400">Không có bảng hàng hoá.</td></tr>}
              </tbody>
            </table>
            </div>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <Field label="Tạm tính" sev={f('subtotal_amount')} value={money(ex.subtotal_amount)} dataField={`${column.key}::subtotal_amount`} />
            <Field label="Thuế VAT" sev={f('vat_amount')} value={[ex.vat_rate != null ? `${ex.vat_rate}%` : null, money(ex.vat_amount)].filter(Boolean).join(' — ') || '—'} dataField={`${column.key}::vat_amount`} />
            <Field label="Tổng" sev={f('total_amount')} value={money(ex.total_amount)} dataField={`${column.key}::total_amount`} />
            <Field label="Số tiền đề nghị (PR)" sev={f('requested_payment_amount')} value={money(ex.requested_payment_amount)} dataField={`${column.key}::requested_payment_amount`} />
          </div>
        </div>
      )}

      {tab === 'payment' && (
        <div className="mt-3 space-y-2">
          <Field label="Chủ tài khoản" sev={f('bank_beneficiary.account_number')} value={ex.bank_beneficiary?.account_name} dataField={`${column.key}::bank_beneficiary.account_name`} />
          <Field label="Số tài khoản" sev={f('bank_beneficiary.account_number')} value={ex.bank_beneficiary?.account_number} dataField={`${column.key}::bank_beneficiary.account_number`} />
          <Field label="Ngân hàng" sev={f('bank_beneficiary.bank_name')} value={ex.bank_beneficiary?.bank_name} dataField={`${column.key}::bank_beneficiary.bank_name`} />
          <Field label="Tổng hoá đơn" sev={f('total_amount')} value={money(ex.total_amount)} dataField={`${column.key}::total_amount`} />
          <Field label="Số tiền đề nghị" sev={f('requested_payment_amount')} value={money(ex.requested_payment_amount)} dataField={`${column.key}::requested_payment_amount`} />
        </div>
      )}
    </div>
  )
}
