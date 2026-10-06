import { useEffect, useState, useCallback } from 'react'
import { LayoutDashboard, History, RotateCcw, Download } from 'lucide-react'
import UploadPanel from './components/UploadPanel.jsx'
import FindingsPanel from './components/FindingsPanel.jsx'
import SideBySideViewer from './components/SideBySideViewer.jsx'
import HistoryView from './components/HistoryView.jsx'
import { uploadBatch, listBatches, getBatch, exportCsvUrl } from './api.js'

// field chung -> cac field chi tiet tren 3 cot
const RULE_FIELD_MAP = {
  R0_doc_number: ['PO::doc_number', 'INVOICE::doc_number', 'PAYMENT_REQUEST::doc_number'],
  R1: ['INVOICE::reference_numbers', 'PAYMENT_REQUEST::reference_numbers'],
  R2: ['PAYMENT_REQUEST::bank_beneficiary.account_name', 'PAYMENT_REQUEST::bank_beneficiary.account_number', 'INVOICE::bank_beneficiary.account_number', 'PO::bank_beneficiary.account_number'],
  R3: ['INVOICE::subtotal_amount'],
  R4: ['INVOICE::subtotal_amount', 'INVOICE::vat_amount', 'INVOICE::total_amount', 'PO::total_amount'],
  R5: ['INVOICE::subtotal_amount'],
  R6: ['INVOICE::subtotal_amount'],
  R7: ['PO::total_amount', 'INVOICE::total_amount', 'PAYMENT_REQUEST::requested_payment_amount'],
  R8: ['PO::seller_name', 'INVOICE::seller_name', 'PAYMENT_REQUEST::seller_name'],
  R9: ['PO::buyer_name', 'INVOICE::buyer_name', 'PAYMENT_REQUEST::buyer_name'],
  R10: ['PO::buyer_address', 'PO::seller_address', 'INVOICE::buyer_address', 'INVOICE::seller_address'],
  R11: ['PO::issue_date', 'INVOICE::issue_date', 'PAYMENT_REQUEST::issue_date', 'INVOICE::due_date'],
  R12: ['PO::approval_status', 'PAYMENT_REQUEST::approval_status'],
}

function findingTargets(f) {
  const rule = (f.rule_id || '').split('_')[0]
  // neu co field_name cu the -> uu tien
  if (f.field_name) {
    return [lookupByFieldToken(f.field_name)]
  }
  return RULE_FIELD_MAP[rule] || []
}

function lookupByFieldToken(token) {
  const t = token.toLowerCase()
  if (t.includes('account')) return 'PAYMENT_REQUEST::bank_beneficiary.account_number'
  if (t.includes('subtotal')) return 'INVOICE::subtotal_amount'
  if (t.includes('total')) return 'INVOICE::total_amount'
  if (t.includes('seller')) return 'INVOICE::seller_name'
  if (t.includes('buyer')) return 'PO::buyer_name'
  if (t.includes('address')) return 'INVOICE::seller_address'
  if (t.includes('date') || t.includes('due')) return 'INVOICE::issue_date'
  if (t.includes('status') || t.includes('approv')) return 'PAYMENT_REQUEST::approval_status'
  return 'INVOICE::total_amount'
}

export default function App() {
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [detail, setDetail] = useState(null)
  const [history, setHistory] = useState({ items: [], total: 0 })
  const [view, setView] = useState('audit')

  const refreshHistory = useCallback(async () => {
    try {
      const h = await listBatches(50, 0)
      setHistory(h)
    } catch { /* backend chua bat -> hien thi rong */ }
  }, [])

  useEffect(() => { refreshHistory() }, [refreshHistory])

  const handleUpload = async (files) => {
    const data = await uploadBatch(files)
    const normalized = {
      batch_id: data.batch_id,
      status: data.status,
      overall_verdict: data.overall_verdict,
      summary_note: data.summary_note,
      documents: data.documents.map((d) => ({...d, doc_type: d.doc_type, extracted: d.extracted})),
      findings: (data.findings || []).map((f) => ({...f, rule_name: f.rule_name || ''})),
      rule_results: data.rule_results || [],
    }
    setResult(normalized)
    setDetail(null)
    refreshHistory()
    return data
  }

  const handleViewHistory = async (id) => {
    const d = await getBatch(id)
    const normalized = {
      batch_id: d.batch?.id,
      status: d.batch?.status,
      overall_verdict: d.verdict?.overall_verdict || d.batch?.overall_verdict,
      summary_note: d.verdict?.summary_note,
      documents: d.documents.map((x) => ({ file_name: x.file_name, doc_type: x.doc_type, extraction_method: x.extraction_method, extraction_model: x.extraction_model, warnings: x.warnings, extracted: x.extracted })),
      findings: (d.findings || []).map((f) => ({...f, rule_name: f.rule_id})),
      rule_results: d.rule_results || [],
    }
    setDetail(normalized)
    setResult(null)
    setView('audit')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const reset = () => { setResult(null); setDetail(null) }
  const shown = detail || result
  const findings = shown ? applySuggestion(shown) : []

  // bo sung suggestion ngan cho hien thi (backend chua co suggestion o response /upload)
  function applySuggestion(sh) {
    const SUG = {
      R2: 'Xac minh TK thu huong voi NCC; khong thanh toan khi chua khop.',
      R3: 'Soat lai qty x unit_price tung dong hang.',
      R5: 'Invoice khong vuot so luong PO; yeu cau dieu chinh.',
      R6: 'Don gia Invoice khong vuot PO.',
      R7: 'So tien PR phai khop 100% Invoice; Invoice khong vuot PO.',
      R12: 'Hoan tat phe duyet truoc khi thanh toan.',
    }
    return (sh.findings || []).map((f) => ({...f, suggestion: f.suggestion || SUG[(f.rule_id||'').split('_')[0]]}))
  }

  const handleSelectFinding = (f) => {
    const targets = findingTargets(f)
    // flash tung field lien quan (cach nhau 900ms)
    targets.forEach((field, i) => {
      setTimeout(() => window.dispatchEvent(new CustomEvent('audit:flash', { detail: { field, severity: f.severity } })), i * 900)
    })
  }

  return (
    <div className="min-h-screen bg-slate-100">
      <header className="sticky top-0 z-10 border-b bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2">
            <div className="rounded-xl bg-indigo-600 p-2 text-white"><LayoutDashboard className="h-5 w-5" /></div>
            <div>
              <div className="text-sm font-bold text-slate-800">AI Expense Audit System</div>
              <div className="text-[11px] text-slate-500">Doi soat 3 chieu PO - Invoice - Payment Request (R0-R12)</div>
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={() => setView('audit')} className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${view === 'audit' ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600'}`}>Audit</button>
            <button onClick={() => { setView('history'); refreshHistory() }} className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold ${view === 'history' ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600'}`}><History className="h-3.5 w-3.5" /> History</button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-4 px-4 py-6">
        {view === 'history' ? (
          <HistoryView items={history.items} total={history.total} onView={handleViewHistory} />
        ) : (
          <>
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
              <div><UploadPanel onUploaded={handleUpload} busy={busy} setBusy={setBusy} /></div>
              <div className="lg:col-span-2">
                {!shown && !busy && (
                  <div className="flex h-full min-h-[280px] items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-white px-6 text-center text-sm text-slate-500">
                    Upload bo 3 chung tu de bat dau.<br />Vi du: mau sample ban se ra REJECTED (1 CRITICAL + 3 HIGH + 1 MEDIUM).
                  </div>
                )}
                {busy && <div className="flex h-full min-h-[280px] items-center justify-center rounded-2xl border bg-white text-sm text-slate-500">Dang trich xuat + audit (LLM, fallback offline neu rate-limit)...</div>}
                {shown && <FindingsPanel findings={findings} onSelectFinding={handleSelectFinding} />}
              </div>
            </div>

            {shown && (
              <>
                <div className="flex items-center gap-2">
                  <button onClick={reset} className="inline-flex items-center gap-1.5 rounded-lg bg-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-300"><RotateCcw className="h-3.5 w-3.5" /> Audit batch moi</button>
                  <a href={exportCsvUrl(shown.batch_id)} className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700"><Download className="h-3.5 w-3.5" /> Xuat CSV findings</a>
                  <span className="text-xs text-slate-500">{shown.summary_note}</span>
                </div>
                <SideBySideViewer batch={shown} findings={findings} />
                <details className="rounded-xl border bg-white px-4 py-3 text-xs text-slate-600">
                  <summary className="cursor-pointer font-semibold">Chi tiet 13 rules R0-R12 (cho reviewer / debug)</summary>
                  <ul className="mt-2 space-y-1 font-mono text-[11px]">
                    {(shown.rule_results || []).map((r, i) => (
                      <li key={i} className={r.status === 'FAILED' ? 'font-bold text-red-600' : ''}>[{r.status}] {r.rule_id} {r.rule_name} — {r.message}</li>
                    ))}
                  </ul>
                </details>
              </>
            )}
          </>
        )}
      </main>
    </div>
  )
}

