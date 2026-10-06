import { useEffect, useState, useCallback } from 'react'
import { LayoutDashboard, History, RotateCcw, Download, Loader2 } from 'lucide-react'
import UploadPanel from './components/UploadPanel.jsx'
import FindingsPanel from './components/FindingsPanel.jsx'
import SideBySideViewer from './components/SideBySideViewer.jsx'
import HistoryView from './components/HistoryView.jsx'
import { uploadBatch, listBatches, getBatch, exportCsvUrl } from './api.js'

/** Lấy danh sách ô cần highlight do backend chỉ định (severity + suggestion + highlight_targets). */
function findingTargets(f) {
  if (Array.isArray(f.highlight_targets) && f.highlight_targets.length) {
    return f.highlight_targets
  }
  return []
}

/** Gộp nhiều bản ghi tài liệu về cùng một định dạng cho cả upload mới và xem lịch sử. */
function normalizeDocuments(docs = []) {
  return docs.map((d) => ({
    file_name: d.file_name,
    doc_type: d.doc_type,
    extraction_method: d.extraction_method,
    extraction_model: d.extraction_model,
    warnings: d.warnings || [],
    extracted: d.extracted,
  }))
}

export default function App() {
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState(null)
  const [result, setResult] = useState(null)
  const [detail, setDetail] = useState(null)
  const [history, setHistory] = useState({ items: [], total: 0 })
  const [view, setView] = useState('audit')

  const refreshHistory = useCallback(async () => {
    try {
      const h = await listBatches(50, 0)
      setHistory(h)
    } catch {
      /* backend chưa bật -> hiển thị rỗng */
    }
  }, [])

  useEffect(() => { refreshHistory() }, [refreshHistory])

  const normalizeUpload = (data) => ({
    batch_id: data.batch_id,
    status: data.status,
    reference_label: data.reference_label,
    overall_verdict: data.overall_verdict,
    summary_note: data.summary_note,
    documents: normalizeDocuments(data.documents),
    findings: data.findings || [],
    rule_results: data.rule_results || [],
  })

  const normalizeDetail = (d) => ({
    batch_id: d.batch?.id,
    status: d.batch?.status,
    reference_label: d.batch?.reference_label,
    overall_verdict: d.verdict?.overall_verdict || d.batch?.overall_verdict,
    summary_note: d.verdict?.summary_note,
    created_at: d.batch?.created_at,
    documents: normalizeDocuments(d.documents),
    findings: d.findings || [],
    rule_results: d.rule_results || [],
  })

  const handleUpload = async (files, label, onProgress) => {
    const data = await uploadBatch(files, label, onProgress)
    setResult(normalizeUpload(data))
    setDetail(null)
    refreshHistory()
    return data
  }

  const handleViewHistory = async (id) => {
    const d = await getBatch(id)
    setDetail(normalizeDetail(d))
    setResult(null)
    setView('audit')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const reset = () => { setResult(null); setDetail(null) }
  const shown = detail || result
  const findings = shown?.findings || []

  // Bấm 1 cảnh báo -> lần lượt cuộn và nhấp nháy các ô dữ liệu tương ứng.
  const handleSelectFinding = (f) => {
    const targets = findingTargets(f)
    targets.forEach((field, i) => {
      setTimeout(() => {
        window.dispatchEvent(
          new CustomEvent('audit:flash', { detail: { field, severity: f.severity } })
        )
      }, i * 600)
    })
  }

  return (
    <div className="min-h-screen bg-slate-100">
      <header className="sticky top-0 z-10 border-b bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2">
            <div className="rounded-xl bg-blue-700 p-2 text-white">
              <LayoutDashboard className="h-5 w-5" />
            </div>
            <div>
              <div className="text-sm font-bold text-slate-800">AI Expense Audit System</div>
              <div className="text-[11px] text-slate-500">
                Đối soát 3 chiều PO - Hoá đơn - Đề nghị thanh toán (R0-R12)
              </div>
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setView('audit')}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${
                view === 'audit' ? 'bg-blue-700 text-white' : 'bg-slate-100 text-slate-600'
              }`}
            >
              Kiểm tra
            </button>
            <button
              onClick={() => { setView('history'); refreshHistory() }}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold ${
                view === 'history' ? 'bg-blue-700 text-white' : 'bg-slate-100 text-slate-600'
              }`}
            >
              <History className="h-3.5 w-3.5" /> Lịch sử
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-4 px-4 py-6">
        {view === 'history' ? (
          <HistoryView items={history.items} total={history.total} onView={handleViewHistory} />
        ) : (
          <>
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
              <div>
                <UploadPanel
                  onUploaded={handleUpload}
                  busy={busy}
                  setBusy={setBusy}
                  onProgress={setProgress}
                />
              </div>
              <div className="lg:col-span-2">
                {!shown && !busy && (
                  <div className="flex h-full min-h-[280px] flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-slate-300 bg-white px-6 text-center text-sm text-slate-500">
                    <span>
                      Tải lên bộ 3 chứng từ để bắt đầu. Bộ mẫu kèm theo sẽ ra{' '}
                      <b className="text-red-600">TỪ CHỐI (REJECTED)</b> — 1 lỗi nghiêm trọng, 3 lỗi cao, 1 lỗi trung bình.
                    </span>
                    <span className="text-xs text-slate-400">
                      Bấm vào từng cảnh báo để tự động nhảy tới các ô dữ liệu bị lỗi.
                    </span>
                  </div>
                )}
                {busy && (
                  <div className="flex h-full min-h-[280px] flex-col items-center justify-center gap-3 rounded-2xl border bg-white px-6 text-center">
                    <Loader2 className="h-7 w-7 animate-spin text-blue-700" />
                    <div className="text-sm font-semibold text-slate-700">Đang trích xuất dữ liệu và đối soát…</div>
                    <div className="text-xs text-slate-500">
                      Hệ thống đang đọc nội dung tệp bằng AI, sau đó chạy 13 quy tắc kiểm tra R0-R12.
                    </div>
                    <div className="text-[11px] text-slate-400">
                      Nếu mô hình AI bị giới hạn tốc độ, hệ thống tự động dùng bộ phân tích dự phòng cục bộ.
                    </div>
                    {progress != null && (
                      <div className="mt-1 w-full max-w-[260px]">
                        <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200">
                          <div
                            className="h-full rounded-full bg-blue-700 transition-all"
                            style={{ width: `${Math.max(6, progress)}%` }}
                          />
                        </div>
                        <div className="mt-1 text-[11px] font-medium text-slate-500">
                          Đang tải lên: {progress}%
                        </div>
                      </div>
                    )}
                  </div>
                )}
                {shown && (
                  <FindingsPanel findings={findings} onSelectFinding={handleSelectFinding} />
                )}
              </div>
            </div>

            {shown && (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    onClick={reset}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-300"
                  >
                    <RotateCcw className="h-3.5 w-3.5" /> Kiểm tra bộ mới
                  </button>
                  <a
                    href={exportCsvUrl(shown.batch_id)}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700"
                  >
                    <Download className="h-3.5 w-3.5" /> Xuất CSV cảnh báo
                  </a>
                  {shown.reference_label && (
                    <span className="rounded-lg bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 ring-1 ring-slate-200">
                      Số/Tên chứng từ: {shown.reference_label}
                    </span>
                  )}
                  <span className="text-xs text-slate-500">{shown.summary_note}</span>
                </div>
                <SideBySideViewer batch={shown} />
                <details className="rounded-xl border bg-white px-4 py-3 text-xs text-slate-600">
                  <summary className="cursor-pointer font-semibold">
                    Chi tiết 13 quy tắc kiểm tra R0-R12 (dành cho người review / gỡ lỗi)
                  </summary>
                  <ul className="mt-2 space-y-1 font-mono text-[11px]">
                    {(shown.rule_results || []).map((r, i) => (
                      <li key={i} className={r.status === 'FAILED' ? 'font-bold text-red-600' : ''}>
                        [{r.status}] {r.rule_id} {r.rule_name} — {r.message}
                      </li>
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
