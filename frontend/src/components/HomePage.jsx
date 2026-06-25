import { useRef, useState } from 'react'
import axios from 'axios'

const ACCEPTED = { 'text/csv': ['.csv'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'], 'application/vnd.ms-excel': ['.xls'], 'application/json': ['.json'] }
const ACCEPT_STR = '.csv,.xlsx,.xls,.json'

export default function HomePage({ onUploaded }) {
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState(null)
  const [uploading, setUploading] = useState(false)

  async function uploadFile(file) {
    const ext = file.name.split('.').pop().toLowerCase()
    if (!['csv', 'xlsx', 'xls', 'json'].includes(ext)) {
      setError(`Unsupported format: .${ext}. Please use CSV, XLSX, or JSON.`)
      return
    }
    setError(null)
    setUploading(true)
    try {
      const form = new FormData()
      form.append('file', file)
      const { data } = await axios.post('/upload', form)
      onUploaded(data.job_id)
    } catch (e) {
      setError(e.response?.data?.detail || 'Upload failed. Please try again.')
      setUploading(false)
    }
  }

  function onDrop(e) {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) uploadFile(file)
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-[70vh] animate-fade-in">
      {/* Hero */}
      <div className="text-center mb-10">
        <div className="flex justify-center mb-5">
          <div className="bg-blue-600 rounded-2xl p-4 shadow-lg">
            <svg viewBox="0 0 48 48" className="w-14 h-14" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M10 34 L10 14 L20 14 L20 34 M20 24 L30 24 L30 34 M30 18 L38 18 L38 34"
                stroke="white" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round"/>
              <circle cx="38" cy="12" r="5" fill="#93c5fd"/>
              <path d="M36 12 L40 12 M38 10 L38 14" stroke="white" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          </div>
        </div>
        <h1 className="text-4xl font-bold text-gray-900 mb-3">DataCruncher</h1>
        <p className="text-lg text-gray-500 max-w-md">
          Upload a large dataset and we'll automatically club repeating fields together —
          shrinking 100k+ rows to the minimum possible records.
        </p>
      </div>

      {/* Upload zone */}
      <div
        className={`w-full max-w-lg border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition-colors
          ${dragging ? 'border-blue-500 bg-blue-50' : 'border-gray-300 bg-white hover:border-blue-400 hover:bg-blue-50/40'}`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => !uploading && inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT_STR}
          className="hidden"
          onChange={(e) => e.target.files[0] && uploadFile(e.target.files[0])}
        />

        {uploading ? (
          <div className="flex flex-col items-center gap-3">
            <div className="w-10 h-10 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
            <p className="text-gray-600 font-medium">Uploading…</p>
          </div>
        ) : (
          <>
            <div className="flex justify-center mb-4">
              <svg className="w-12 h-12 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
              </svg>
            </div>
            <p className="text-gray-700 font-semibold text-lg mb-1">Drop your dataset here</p>
            <p className="text-gray-400 text-sm mb-4">or click to browse files</p>
            <div className="flex justify-center gap-2">
              {['CSV', 'XLSX', 'JSON'].map(fmt => (
                <span key={fmt} className="px-3 py-1 bg-gray-100 text-gray-600 text-xs font-semibold rounded-full">
                  {fmt}
                </span>
              ))}
            </div>
          </>
        )}
      </div>

      {error && (
        <div className="mt-4 w-full max-w-lg bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm">
          {error}
        </div>
      )}

      <p className="mt-6 text-xs text-gray-400">
        Works best with datasets of 10,000 – 1,000,000 rows
      </p>
    </div>
  )
}
