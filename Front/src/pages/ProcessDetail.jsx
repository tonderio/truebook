import React, { useState, useCallback } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { processApi, filesApi } from '../api/client'
import {
  Play, Upload, Loader2, CheckCircle2, AlertCircle, Info,
  FileText, Trash2, ChevronRight, BarChart3, FileSpreadsheet,
} from 'lucide-react'
import StatusBadge from '../components/ui/StatusBadge'
import { format } from 'date-fns'
import { es } from 'date-fns/locale'
import clsx from 'clsx'

const STAGES = [
  { key: 'extracting_transactions', label: 'Extrayendo transacciones' },
  { key: 'extracting_withdrawals',  label: 'Extrayendo retiros' },
  { key: 'extracting_refunds',      label: 'Extrayendo reembolsos' },
  { key: 'processing_fees',         label: 'Procesando comisiones' },
  { key: 'parsing_kushki',          label: 'Parseando Kushki' },
  { key: 'parsing_banregio',        label: 'Parseando Banregio' },
  { key: 'conciliating',            label: 'Conciliando' },
  { key: 'classifying',             label: 'Clasificando movimientos' },
  { key: 'alerting',                label: 'Generando alertas' },
  { key: 'done',                    label: 'Completado' },
]

function StageTimeline({ currentStage, progress, status }) {
  const currentIdx = STAGES.findIndex(s => s.key === currentStage)

  return (
    <div className="space-y-2">
      {STAGES.map((stage, idx) => {
        const done = status === 'completed' || idx < currentIdx
        const active = stage.key === currentStage && status === 'running'
        return (
          <div key={stage.key} className="flex items-center gap-3">
            <div className={clsx(
              'w-6 h-6 rounded-full flex items-center justify-center text-xs shrink-0',
              done   ? 'bg-emerald-700 text-white' :
              active ? 'bg-blue-500 text-white' :
                       'bg-gray-100 text-gray-400'
            )}>
              {done ? <CheckCircle2 size={12} /> : active ? <Loader2 size={12} className="animate-spin" /> : idx + 1}
            </div>
            <span className={clsx(
              'text-sm',
              done   ? 'text-emerald-800' :
              active ? 'text-blue-600 font-medium' :
                       'text-gray-400'
            )}>
              {stage.label}
            </span>
          </div>
        )
      })}
    </div>
  )
}

function FileUpload({ processId, fileType, label }) {
  const qc = useQueryClient()
  const [dragging, setDragging] = useState(false)

  const upload = useMutation({
    mutationFn: (file) => filesApi.upload(processId, fileType, file),
    onSuccess: () => qc.invalidateQueries(['files', processId]),
  })

  const handleFiles = (files) => {
    Array.from(files).forEach(f => upload.mutate(f))
  }

  return (
    <div>
      <p className="text-sm font-medium text-gray-700 mb-2">{label}</p>
      <label
        className={clsx(
          'flex flex-col items-center justify-center h-24 border-2 border-dashed rounded-xl cursor-pointer transition-colors',
          dragging ? 'border-blue-400 bg-blue-50' : 'border-gray-300 hover:border-gray-400'
        )}
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={e => { e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer.files) }}
      >
        <input
          type="file"
          className="hidden"
          multiple
          accept=".csv,.xlsx,.xls,.pdf"
          onChange={e => handleFiles(e.target.files)}
        />
        {upload.isPending
          ? <Loader2 size={20} className="animate-spin text-gray-400" />
          : <>
              <Upload size={20} className="text-gray-400 mb-1" />
              <p className="text-xs text-gray-500">Arrastra o haz clic · CSV, Excel, PDF</p>
            </>
        }
      </label>
    </div>
  )
}

export default function ProcessDetail() {
  const { id } = useParams()
  const qc = useQueryClient()
  const navigate = useNavigate()

  const { data: proc } = useQuery({
    queryKey: ['process', id],
    queryFn: () => processApi.get(id).then(r => r.data),
    refetchInterval: (data) => data?.status === 'running' ? 2000 : false,
  })

  const { data: progress } = useQuery({
    queryKey: ['progress', id],
    queryFn: () => processApi.progress(id).then(r => r.data),
    refetchInterval: (data) => data?.status === 'running' ? 2000 : 10000,
  })

  const { data: files = [] } = useQuery({
    queryKey: ['files', id],
    queryFn: () => filesApi.list(id).then(r => r.data),
  })

  const { data: config } = useQuery({
    queryKey: ['process-config'],
    queryFn: () => processApi.config().then(r => r.data),
    staleTime: Infinity,
  })

  const kushkiSftpEnabled = config?.kushki_sftp_enabled ?? false

  const runMutation = useMutation({
    mutationFn: () => processApi.run(id),
    onSuccess: () => {
      qc.invalidateQueries(['process', id])
      qc.invalidateQueries(['progress', id])
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (fileId) => filesApi.delete(fileId),
    onSuccess: () => qc.invalidateQueries(['files', id]),
  })

  // v2 Banregio Report download — POST returns the .xlsx as a Blob,
  // we convert to ObjectURL and trigger a download via a temp <a>.
  const reportV2Mutation = useMutation({
    mutationFn: () => processApi.downloadBanregioReportV2(id),
    onSuccess: (response) => {
      const blob = response.data
      // Try to read filename from Content-Disposition; fall back to a default
      const disposition = response.headers?.['content-disposition'] || ''
      const match = disposition.match(/filename="?([^"]+)"?/)
      const filename = match
        ? match[1]
        : `RECONCILIACION_BANREGIO_${proc.period_year}_${String(proc.period_month).padStart(2, '0')}_v2.xlsx`

      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    },
  })

  if (!proc) return (
    <div className="flex items-center justify-center h-full py-20">
      <Loader2 size={24} className="animate-spin text-gray-400" />
    </div>
  )

  const canRun = proc.status !== 'running'

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 text-gray-500 text-sm mb-1">
            <Link to="/contabilidad" className="hover:text-gray-700">Contabilidad</Link>
            <ChevronRight size={12} />
            <span className="text-gray-900">{proc.name}</span>
          </div>
          <h1 className="text-2xl font-semibold text-gray-900">{proc.name}</h1>
          <p className="text-gray-500 text-sm mt-0.5">
            Cuenta: {proc.bank_account || 'Banregio'} · Período: {proc.period_year}-{String(proc.period_month).padStart(2, '0')} ·
            Adquirentes: {(proc.acquirers || []).join(', ')}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <StatusBadge status={proc.status} />
          {(proc.status === 'completed' || proc.status === 'reconciled') && (
            <>
              <Link to={`/processes/${id}/results`} className="btn-primary flex items-center gap-2">
                <BarChart3 size={14} />
                Ver resultados
              </Link>
              <button
                onClick={() => reportV2Mutation.mutate()}
                disabled={reportV2Mutation.isPending}
                title="Descargar reporte de reconciliación Banregio v2 (.xlsx)"
                className="btn-primary flex items-center gap-2"
              >
                {reportV2Mutation.isPending
                  ? <><Loader2 size={14} className="animate-spin" /> Generando...</>
                  : <><FileSpreadsheet size={14} /> Reporte v2</>
                }
              </button>
            </>
          )}
          <button
            onClick={() => runMutation.mutate()}
            disabled={!canRun || runMutation.isPending}
            className="btn-primary flex items-center gap-2"
          >
            {proc.status === 'running'
              ? <><Loader2 size={14} className="animate-spin" /> Ejecutando...</>
              : <><Play size={14} /> Ejecutar proceso</>
            }
          </button>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Left: upload + files */}
        <div className="col-span-2 space-y-6">
          {/* File uploads */}
          <div className="card space-y-4">
            <h2 className="text-base font-semibold text-gray-900">Archivos de entrada</h2>
            <div className={`grid gap-4 ${kushkiSftpEnabled ? 'grid-cols-1' : 'grid-cols-2'}`}>
              {!kushkiSftpEnabled && (
                <FileUpload processId={id} fileType="kushki" label="Archivos Kushki" />
              )}
              <FileUpload processId={id} fileType="banregio" label="Archivos Banregio" />
            </div>
            {kushkiSftpEnabled && (
              <p className="text-xs text-emerald-800 flex items-center gap-1">
                <CheckCircle2 size={12} /> Kushki se descargará automáticamente vía SFTP al ejecutar
              </p>
            )}

            {files.length > 0 && (
              <div className="mt-2 space-y-1">
                {files.map(f => (
                  <div key={f.id} className="flex items-center gap-3 px-3 py-2 bg-gray-50 rounded-lg">
                    <FileText size={14} className="text-gray-400 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-gray-900 truncate">{f.original_name}</p>
                      <p className="text-xs text-gray-500">
                        {f.file_type} · {(f.file_size / 1024).toFixed(1)} KB
                      </p>
                    </div>
                    <StatusBadge status={f.status} />
                    <button
                      onClick={() => deleteMutation.mutate(f.id)}
                      className="text-gray-400 hover:text-red-500 transition-colors"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Logs */}
          {progress?.logs?.length > 0 && (
            <div className="card">
              <h2 className="text-base font-semibold text-gray-900 mb-3">Log de ejecución</h2>
              <div className="space-y-1 max-h-72 overflow-y-auto">
                {progress.logs.map(log => (
                  <div
                    key={log.id}
                    className={clsx(
                      'flex items-start gap-2 text-xs px-2 py-1 rounded',
                      log.level === 'error'   ? 'bg-red-50 text-red-600' :
                      log.level === 'warning' ? 'bg-amber-50 text-amber-700' :
                                               'text-gray-500'
                    )}
                  >
                    {log.level === 'error' ? <AlertCircle size={12} className="mt-0.5 shrink-0" /> :
                     log.level === 'warning' ? <AlertCircle size={12} className="mt-0.5 shrink-0" /> :
                     <Info size={12} className="mt-0.5 shrink-0" />}
                    <span className="text-gray-400 shrink-0">
                      [{format(new Date(log.created_at), 'HH:mm:ss')}]
                    </span>
                    <span className="font-medium text-gray-500 shrink-0">[{log.stage}]</span>
                    <span>{log.message}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right: progress */}
        <div className="space-y-4">
          <div className="card">
            <h2 className="text-base font-semibold text-gray-900 mb-4">Progreso</h2>
            <div className="mb-4">
              <div className="flex justify-between text-xs text-gray-500 mb-1">
                <span>{proc.current_stage ? proc.current_stage.replace(/_/g, ' ') : 'Sin iniciar'}</span>
                <span>{proc.progress}%</span>
              </div>
              <div className="progress-track">
                <div
                  className="progress-fill"
                  style={{ background: proc.status === 'failed' ? '#ef4444' : '#3b82f6' }}
                  style={{ width: `${proc.progress}%` }}
                />
              </div>
            </div>
            <StageTimeline
              currentStage={proc.current_stage}
              progress={proc.progress}
              status={proc.status}
            />
          </div>

          {proc.error_message && (
            <div className="t-card border-red-200 bg-red-50">
              <p className="text-sm font-medium text-red-700 mb-1">Error</p>
              <p className="text-xs text-red-600">{proc.error_message}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
