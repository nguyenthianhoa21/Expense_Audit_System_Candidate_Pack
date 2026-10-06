import { useRef, useState } from 'react'
import { UploadCloud, FileText, Loader2, AlertTriangle, X } from 'lucide-react'

const HINTS = [
  ['PO', '.pdf', 'Purchase Order'],
  ['INV', '.pdf', 'Invoice'],
  ['PR', '.pdf', 'Payment Request'],
]

/** Panel tải lên tối đa 10 tệp PDF/ảnh, gồm ô nhập số hoá đơn và hiển thị tiến độ. */
export default function UploadPanel({ onUploaded, busy, setBusy, onProgress }) {
  const [files, setFiles] = useState([])
  const [label, setLabel] = useState('')
  const [error, setError] = useState('')
  const inputRef = useRef(null)

  const pick = (list) => {
    const arr = Array.from(list || []).slice(0, 10 - files.length)
    setFiles((prev) => [...prev, ...arr].slice(0, 10))
    setError('')
  }

  const removeAt = (i) => setFiles((prev) => prev.filter((_, x) => x !== i))

  const submit = async () => {
    if (!files.length) {
      setError('Vui lòng chọn ít nhất 1 tệp PDF/ảnh.')
      return
    }
    try {
      setBusy(true)
      setError('')
      onProgress?.(0)
      await onUploaded(files, label.trim(), (pct) => onProgress?.(pct))
      setFiles([])
      if (inputRef.current) inputRef.current.value = ''
      return true
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || 'Tải lên thất bại')
    } finally {
      setBusy(false)
      onProgress?.(null)
    }
  }

  const kb = (n) => (n / 1024 >= 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${(n / 1024).toFixed(1)} KB`)

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center gap-2">
        <UploadCloud className="h-5 w-5 text-indigo-600" />
        <h2 className="text-base font-semibold text-slate-800">Tải lên bộ chứng từ</h2>
      </div>
      <p className="mt-1 text-xs text-slate-500">
        Hỗ trợ PDF/ảnh, tối đa 10 tệp. Hệ thống tự phân loại PO / Invoice / Payment Request theo tên tệp và nội dung.
      </p>

      <label htmlFor="reference-label" className="mt-4 block text-xs font-semibold text-slate-700">
        Số hoá đơn / Tên chứng từ
      </label>
      <input
        id="reference-label"
        type="text"
        value={label}
        onChange={(e) => setLabel(e.target.value)}
        placeholder="Ví dụ: HĐ-2026-1234"
        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100"
      />

      <label className="mt-3 flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-300 bg-slate-50 px-4 py-8 text-center hover:border-indigo-400">
        <FileText className="h-8 w-8 text-slate-400" />
        <span className="mt-2 text-sm font-medium text-slate-700">
          Kéo thả chứng từ vào đây, hoặc <span className="text-indigo-600 underline">chọn tệp</span>
        </span>
        <span className="text-xs text-slate-400">.pdf, .png, .jpg, .jpeg, .tiff, .webp — nhiều tệp cùng lúc</span>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,.png,.jpg,.jpeg,.tiff,.webp"
          className="hidden"
          onChange={(e) => pick(e.target.files)}
        />
      </label>

      {files.length > 0 && (
        <ul className="mt-3 divide-y divide-slate-100 rounded-xl border border-slate-200">
          {files.map((f, i) => (
            <li key={i} className="flex items-center justify-between px-3 py-2 text-xs text-slate-700">
              <div className="min-w-0">
                <div className="truncate font-medium">{f.name}</div>
                <div className="text-[11px] text-slate-400">{kb(f.size)}</div>
              </div>
              <button
                type="button"
                aria-label={`Gỡ ${f.name}`}
                className="ml-2 rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-500"
                onClick={() => removeAt(i)}
              >
                <X className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      )}

      {error && (
        <div className="mt-3 flex items-start gap-2 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">
          <AlertTriangle className="mt-0.5 h-4 w-4" /> {error}
        </div>
      )}

      <button
        onClick={submit}
        disabled={busy || !files.length}
        className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-blue-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
      >
        {busy ? (<><Loader2 className="h-4 w-4 animate-spin" /> Đang xử lý…</>) : 'Bắt đầu kiểm tra (Process & Validate)'}
      </button>

      <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
        Mẹo: đặt tên tệp chứa PO / INV / PR (ví dụ PO-2026-1042.pdf) để phân loại chính xác hơn.
      </p>
    </div>
  )
}
