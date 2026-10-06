import { useState } from 'react'
import { UploadCloud, FileText, Loader2, AlertTriangle } from 'lucide-react'

const HINTS = [
  ['PO', '.pdf', 'Purchase Order'],
  ['INV', '.pdf', 'Invoice'],
  ['PR', '.pdf', 'Payment Request'],
]

/** Panel upload toi da 10 file PDF/anh. */
export default function UploadPanel({ onUploaded, busy, setBusy }) {
  const [files, setFiles] = useState([])
  const [error, setError] = useState('')

  const pick = (list) => {
    const arr = Array.from(list || []).slice(0, 10 - files.length)
    setFiles((prev) => [...prev, ...arr].slice(0, 10))
    setError('')
  }

  const removeAt = (i) => setFiles((prev) => prev.filter((_, x) => x !== i))

  const submit = async () => {
    if (!files.length) {
      setError('Chon it nhat 1 file PDF/anh.')
      return
    }
    try {
      setBusy(true)
      setError('')
      const data = await onUploaded(files)
      setFiles([])
      return data
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || 'Upload that bai')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center gap-2">
        <UploadCloud className="h-5 w-5 text-indigo-600" />
        <h2 className="text-base font-semibold text-slate-800">Upload bo chung tu</h2>
      </div>
      <p className="mt-1 text-xs text-slate-500">
        Ho tro PDF/anh, toi da 10 file. He tu phan loai PO / Invoice / Payment Request theo ten file va noi dung.
      </p>

      <label className="mt-4 flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-300 bg-slate-50 px-4 py-8 text-center hover:border-indigo-400">
        <FileText className="h-8 w-8 text-slate-400" />
        <span className="mt-2 text-sm font-medium text-slate-700">Keo tha hoac bam de chon file</span>
        <span className="text-xs text-slate-400">.pdf, .png, .jpg, .jpeg, .tiff, .webp</span>
        <input
          type="file"
          multiple
          accept=".pdf,.png,.jpg,.jpeg,.tiff,.webp"
          className="hidden"
          onChange={(e) => pick(e.target.files)}
        />
      </label>

      {files.length > 0 && (
        <ul className="mt-3 space-y-1.5">
          {files.map((f, i) => (
            <li key={i} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-1.5 text-xs text-slate-700">
              <span className="truncate">{f.name}</span>
              <button className="ml-2 text-slate-400 hover:text-red-500" onClick={() => removeAt(i)}>x</button>
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
        className="mt-4 w-full rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
      >
        {busy ? (<span className="inline-flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" /> Dang trich xuat + audit...</span>) : 'Chay audit ngay'}
      </button>

      <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
        Tiep goi y: dat ten file chua PO / INV / PR (vi du PO-2026-1042.pdf) de phan loai chinh xac hon.
      </p>
    </div>
  )
}
