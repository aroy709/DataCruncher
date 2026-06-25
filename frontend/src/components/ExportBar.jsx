export default function ExportBar({ jobId }) {
  function download(format) {
    const a = document.createElement('a')
    a.href = `/export/${jobId}?format=${format}`
    a.download = `compressed_data.${format}`
    a.click()
  }

  return (
    <div className="flex items-center gap-3 justify-end">
      <span className="text-sm text-gray-500 mr-1">Export:</span>
      <button
        onClick={() => download('csv')}
        className="flex items-center gap-1.5 px-4 py-2 border border-gray-300 rounded-xl text-sm text-gray-700 hover:bg-gray-50 font-medium transition-colors"
      >
        <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
        </svg>
        Download CSV
      </button>
      <button
        onClick={() => download('xlsx')}
        className="flex items-center gap-1.5 px-4 py-2 bg-green-600 text-white rounded-xl text-sm font-medium hover:bg-green-700 shadow transition-colors"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
        </svg>
        Download Excel
      </button>
    </div>
  )
}
