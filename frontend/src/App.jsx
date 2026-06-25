import { useState } from 'react'
import HomePage from './components/HomePage.jsx'
import ProgressBar from './components/ProgressBar.jsx'
import AnalysisReport from './components/AnalysisReport.jsx'
import CustomisePanel from './components/CustomisePanel.jsx'
import ResultsTable from './components/ResultsTable.jsx'
import SummaryBanner from './components/SummaryBanner.jsx'
import ExportBar from './components/ExportBar.jsx'
import Pagination from './components/Pagination.jsx'

// States: IDLE → UPLOADING → PROCESSING → ANALYSIS → INTERACTIVE → RESULTS
export default function App() {
  const [appState, setAppState] = useState('IDLE')
  const [jobId, setJobId] = useState(null)
  const [analysis, setAnalysis] = useState(null)
  const [results, setResults] = useState(null)
  const [page, setPage] = useState(1)
  const [colMeta, setColMeta] = useState(null)

  function handleUploaded(id) {
    setJobId(id)
    setAppState('PROCESSING')
  }

  function handleProcessingComplete(analysisData, colMetaData) {
    setAnalysis(analysisData)
    setColMeta(colMetaData)
    setAppState('ANALYSIS')
  }

  async function handleAcceptAnalysis() {
    await loadResults(jobId, 1)
    setAppState('RESULTS')
  }

  function handleCustomise() {
    setAppState('INTERACTIVE')
  }

  async function handleReanalysisDone() {
    await loadResults(jobId, 1)
    setAppState('RESULTS')
  }

  async function loadResults(id, p) {
    const res = await fetch(`/results/${id}?page=${p}&limit=100`)
    const data = await res.json()
    setResults(data)
    setPage(p)
  }

  async function handlePageChange(newPage) {
    await loadResults(jobId, newPage)
  }

  function handleStartOver() {
    setAppState('IDLE')
    setJobId(null)
    setAnalysis(null)
    setResults(null)
    setPage(1)
    setColMeta(null)
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header bar — always visible */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <svg viewBox="0 0 32 32" className="w-8 h-8" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect width="32" height="32" rx="8" fill="#2563eb"/>
            <path d="M7 22 L7 10 L13 10 L13 22 M13 16 L19 16 L19 22 M19 12 L25 12 L25 22"
              stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          <span className="text-xl font-bold text-gray-900">DataCruncher</span>
        </div>
        {appState !== 'IDLE' && (
          <button
            onClick={handleStartOver}
            className="text-sm text-gray-500 hover:text-gray-700 underline underline-offset-2"
          >
            Start over
          </button>
        )}
      </header>

      <main className="max-w-7xl mx-auto px-4 py-8">
        {appState === 'IDLE' && (
          <HomePage onUploaded={handleUploaded} />
        )}

        {appState === 'PROCESSING' && (
          <ProgressBar
            jobId={jobId}
            onComplete={handleProcessingComplete}
          />
        )}

        {appState === 'ANALYSIS' && analysis && (
          <AnalysisReport
            analysis={analysis}
            onAccept={handleAcceptAnalysis}
            onCustomise={handleCustomise}
          />
        )}

        {appState === 'INTERACTIVE' && (
          <CustomisePanel
            jobId={jobId}
            colMeta={colMeta}
            onDone={handleReanalysisDone}
          />
        )}

        {appState === 'RESULTS' && results && (
          <div className="animate-fade-in space-y-4">
            <SummaryBanner
              originalCount={results.original_count}
              compressedCount={results.compressed_count}
              compressionRatio={results.compression_ratio}
              onCustomise={() => setAppState('INTERACTIVE')}
            />
            <ExportBar jobId={jobId} />
            <ResultsTable columns={results.columns} data={results.data} />
            <Pagination
              page={page}
              total={results.total}
              limit={results.limit}
              onChange={handlePageChange}
            />
          </div>
        )}
      </main>
    </div>
  )
}
