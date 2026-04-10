import React, { useState, useCallback } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { processApi, filesApi } from '../api/client'
import {
  Play, Upload, Loader2, CheckCircle2, AlertCircle, Info,
  FileText, Trash2, ChevronRight, BarChart3,
} from 'lucide-react'
import StatusBadge from '../components/ui/StatusBadge'
import { format } from 'date-fns'
import { es } from 'date-fns/locale'
import clsx from 'clsx'

const STAGES = [
  { key: 'extracting_transactions', label: 'Extrayendo transacciones' },
  { key: 'extracting_withdrawals',  label: 'Extrayendo withdrawals' },
  { key: 'extracting_refunds',      label: 'Extrayendo refunds' },
  { key: 'processing_fees',         label: 'Procesando FEES' },
  { key: 'parsing_kushki',          label: 'Parseando Kushki' },
  { key: 'parsing_banregio',        label: 'Parseando Banregio' },
  { key: 'conciliating',            label: 'Conciliando' },
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
              done   ? 'bg-emerald-600 text-white' :
              active ? 'bg-brand-600 text-white' :
                       'bg-slate-800 text-slate-500'
            )}>
              {done ? <CheckCircle2 size={12} /> : active ? <Loader2 size={12} className="animate-spin" /> : idx + 1}
            </div>
            <span className={clsx(
              'text-sm',
              done   ? 'text-emerald-400' :
              active ? 'text-brand-300 font-medium' :
                       'text-slate-500'
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
      <p className="text-sm font-medium text-slate-300 mb-2">{label}</p>
      <label
        className={clsx(
          'flex flex-col items-center justify-center h-24 border-2 border-dashed rounded-xl cursor-pointer transition-colors',
          dragging ? 'border-brand-500 bg-brand-900/20' : 'border-slate-700 hover:border-slate-600'
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
          ? <Loader2 size={20} className="animate-spin text-slate-400" />
          : <>
              <Upload size={20} className="text-slate-400 mb-1" />
              <p className="text-xs text-slate-500">Arrastra o haz clic · CSV, Excel, PDF</p>
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

  if (!proc) return (
    <div className="flex items-center justify-center h-full py-20">
      <Loader2 size={24} className="animate-spin text-slate-500" />
    </div>
  )

  const canRun = proc.status !== 'running'

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 text-slate-500 text-sm mb-1">
            <Link to="/processes" className="hover:text-slate-300">Proceso Contable</Link>
            <ChevronRight size={12} />
            <span className="text-slate-300">{proc.name}</span>
          </div>
          <h1 className="text-2xl font-bold text-white">{proc.name}</h1>
          <p className="text-slate-400 text-sm mt-0.5">
            Período: {proc.period_year}-{String(proc.period_month).padStart(2, '0')} ·
            Adquirentes: {(proc.acquirers || []).join(', ')}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <StatusBadge status={proc.status} />
          {proc.status === 'completed' && (
            <Link to={`/processes/${id}/results`} className="btn-primary flex items-center gap-2">
              <BarChart3 size={14} />
              Ver resultados
            </Link>
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
            <h2 className="text-base font-semibold text-white">Archivos de entrada</h2>
            <div className={`grid gap-4 ${kushkiSftpEnabled ? 'grid-cols-1' : 'grid-cols-2'}`}>
              {!kushkiSftpEnabled && (
                <FileUpload processId={id} fileType="kushki" label="Archivos Kushki" />
              )}
              <FileUpload processId={id} fileType="banregio" label="Archivos Banregio" />
            </div>
            {kushkiSftpEnabled && (
              <p className="text-xs text-emerald-400 flex items-center gap-1">
                <CheckCircle2 size={12} /> Kushki se descargará automáticamente vía SFTP al ejecutar
              </p>
            )}

            {files.length > 0 && (
              <div className="mt-2 space-y-1">
                {files.map(f => (
                  <div key={f.id} className="flex items-center gap-3 px-3 py-2 bg-slate-800/50 rounded-lg">
                    <FileText size={14} className="text-slate-400 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-slate-200 truncate">{f.original_name}</p>
                      <p className="text-xs text-slate-500">
                        {f.file_type} · {(f.file_size / 1024).toFixed(1)} KB
                      </p>
                    </div>
                    <StatusBadge status={f.status} />
                    <button
                      onClick={() => deleteMutation.mutate(f.id)}
                      className="text-slate-600 hover:text-red-400 transition-colors"
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
              <h2 className="text-base font-semibold text-white mb-3">Log de ejecución</h2>
              <div className="space-y-1 max-h-72 overflow-y-auto">
                {progress.logs.map(log => (
                  <div
                    key={log.id}
                    className={clsx(
                      'flex items-start gap-2 text-xs px-2 py-1 rounded',
                      log.level === 'error'   ? 'bg-red-900/20 text-red-400' :
                      log.level === 'warning' ? 'bg-amber-900/20 text-amber-400' :
                                               'text-slate-400'
                    )}
                  >
                    {log.level === 'error' ? <AlertCircle size={12} className="mt-0.5 shrink-0" /> :
                     log.level === 'warning' ? <AlertCircle size={12} className="mt-0.5 shrink-0" /> :
                     <Info size={12} className="mt-0.5 shrink-0" />}
                    <span className="text-slate-600 shrink-0">
                      [{format(new Date(log.created_at), 'HH:mm:ss')}]
                    </span>
                    <span className="font-medium text-slate-500 shrink-0">[{log.stage}]</span>
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
            <h2 className="text-base font-semibold text-white mb-4">Progreso</h2>
            <div className="mb-4">
              <div className="flex justify-between text-xs text-slate-400 mb-1">
                <span>{proc.current_stage ? proc.current_stage.replace(/_/g, ' ') : 'Sin iniciar'}</span>
                <span>{proc.progress}%</span>
              </div>
              <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-brand-500 rounded-full transition-all duration-500"
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
            <div className="card border-red-800 bg-red-900/10">
              <p className="text-sm font-medium text-red-400 mb-1">Error</p>
              <p className="text-xs text-red-300">{proc.error_message}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
