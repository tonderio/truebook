import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { sftpApi } from '../api/client'
import {
  Server, CheckCircle2, XCircle, Loader2, RefreshCw,
  Download, Clock, AlertTriangle, Wifi, WifiOff, Zap,
} from 'lucide-react'
import clsx from 'clsx'
import { format } from 'date-fns'
import { es } from 'date-fns/locale'

const ACQ_COLORS = {
  kushki: 't-badge-blue',
  stp: 't-badge-violet',
  pagsmile: 't-badge-orange',
  paysafe: 't-badge-gray',
  bitso: 't-badge-emerald',
}

function StatusCard({ acq, onTest, testing }) {
  const [result, setResult] = useState(null)

  function handleTest() {
    setResult(null)
    onTest(acq.name, (res) => setResult(res))
  }

  const statusConfig = acq.is_configured && acq.enabled
    ? { label: 'Activo', dot: 'bg-emerald-500', text: 'text-emerald-700' }
    : acq.is_configured
    ? { label: 'Pausado', dot: 'bg-amber-500', text: 'text-amber-700' }
    : { label: 'Sin configurar', dot: 'bg-stone-300', text: 'text-stone-400' }

  const isApi = acq.kind === 'api'

  return (
    <div className="t-card fade-in p-5 flex flex-col">
      {/* Header: name + status dot */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          {isApi
            ? <Zap size={14} className={acq.is_configured ? 'text-emerald-600' : 'text-stone-300'} strokeWidth={2} />
            : acq.is_configured
              ? <Wifi size={14} className="text-stone-500" strokeWidth={2} />
              : <WifiOff size={14} className="text-stone-300" strokeWidth={2} />}
          <span className="text-[14px] font-semibold text-stone-900">{acq.label}</span>
          {isApi && (
            <span className="text-[9px] font-semibold uppercase tracking-wider text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded">
              API
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <span className={clsx('w-1.5 h-1.5 rounded-full', statusConfig.dot)} />
          <span className={clsx('text-[11px] font-medium', statusConfig.text)}>{statusConfig.label}</span>
        </div>
      </div>

      {/* Body: config details */}
      {acq.is_configured ? (
        <div className="space-y-2.5 mb-4 flex-1">
          <div>
            <div className="text-[10px] uppercase tracking-wide text-stone-400 font-medium mb-0.5">
              {isApi ? 'Base URL' : 'Host'}
            </div>
            <div className="text-[11px] font-mono text-stone-700 break-all leading-snug" title={acq.host}>
              {acq.host}
            </div>
          </div>
          {isApi ? (
            <div>
              <div className="text-[10px] uppercase tracking-wide text-stone-400 font-medium mb-0.5">API Key</div>
              <div className="text-[12px] text-stone-700 font-mono">{acq.username || '—'}</div>
            </div>
          ) : (
            <div className="flex gap-6">
              <div>
                <div className="text-[10px] uppercase tracking-wide text-stone-400 font-medium mb-0.5">Usuario</div>
                <div className="text-[12px] text-stone-700 font-mono">{acq.username}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wide text-stone-400 font-medium mb-0.5">Puerto</div>
                <div className="text-[12px] text-stone-700 font-mono">{acq.port}</div>
              </div>
            </div>
          )}
          <div>
            <div className="text-[10px] uppercase tracking-wide text-stone-400 font-medium mb-0.5">
              {isApi ? 'Endpoint' : 'Directorio'}
            </div>
            <div className="text-[12px] text-stone-700 font-mono">{acq.remote_dir}</div>
          </div>
        </div>
      ) : (
        <p className="text-[12px] text-stone-400 mb-4 flex-1 leading-relaxed">
          Sin credenciales. Agrega las variables de entorno en Railway para conectar.
        </p>
      )}

      {/* Test result */}
      {result && (
        <div className={clsx(
          'rounded-md px-2.5 py-2 mb-3 text-[11px] leading-snug border',
          result.success
            ? 'bg-emerald-50/60 border-emerald-100 text-emerald-800'
            : 'bg-red-50/60 border-red-100 text-red-800'
        )}>
          <div className="flex items-start gap-1.5">
            {result.success
              ? <CheckCircle2 size={12} className="shrink-0 mt-0.5" />
              : <XCircle size={12} className="shrink-0 mt-0.5" />}
            <span>{result.success ? result.message : result.error}</span>
          </div>
        </div>
      )}

      <button
        onClick={handleTest}
        disabled={!acq.is_configured || testing}
        className="flex items-center justify-center gap-1.5 text-[12px] font-medium text-stone-600 hover:text-stone-900 hover:bg-stone-50 rounded-md py-2 border border-stone-200 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {testing ? (
          <><Loader2 size={11} className="animate-spin" /> Probando...</>
        ) : (
          <><RefreshCw size={11} /> Probar conexion</>
        )}
      </button>
    </div>
  )
}

function Fmt({ bytes }) {
  if (!bytes) return <span className="text-stone-300">-</span>
  if (bytes < 1024) return <span>{bytes} B</span>
  if (bytes < 1048576) return <span>{(bytes / 1024).toFixed(1)} KB</span>
  return <span>{(bytes / 1048576).toFixed(1)} MB</span>
}

export default function SftpModule() {
  const [testingAcq, setTestingAcq] = useState(null)
  const qc = useQueryClient()

  const { data: statusData, isLoading: loadingStatus } = useQuery({
    queryKey: ['sftp-status'],
    queryFn: () => sftpApi.status().then(r => r.data),
  })

  const { data: logs = [], isLoading: loadingLogs } = useQuery({
    queryKey: ['sftp-logs'],
    queryFn: () => sftpApi.logs(50).then(r => r.data),
  })

  const { data: downloads = [], isLoading: loadingDownloads } = useQuery({
    queryKey: ['sftp-downloads'],
    queryFn: () => sftpApi.downloads(50).then(r => r.data),
  })

  const testMut = useMutation({
    mutationFn: (acquirer) => sftpApi.test(acquirer).then(r => r.data),
  })

  function handleTest(acquirer, callback) {
    setTestingAcq(acquirer)
    testMut.mutate(acquirer, {
      onSuccess: (data) => { callback(data); setTestingAcq(null) },
      onError: (err) => {
        callback({ success: false, error: err.response?.data?.detail || 'Error de red' })
        setTestingAcq(null)
      },
    })
  }

  const acquirers = statusData?.acquirers || []
  const configured = acquirers.filter(a => a.is_configured).length
  const active = acquirers.filter(a => a.is_configured && a.enabled).length

  return (
    <div className="px-8 py-6" style={{ maxWidth: 1420 }}>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-stone-900">Conexiones</h1>
          <p className="text-sm text-stone-500 mt-0.5">
            {active} activas · {configured} configuradas · {acquirers.length} adquirentes
          </p>
        </div>
      </div>

      {loadingStatus ? (
        <Loader2 size={20} className="animate-spin text-stone-300 mx-auto mt-12" />
      ) : (
        <>
          {/* Acquirer cards */}
          <div className="grid grid-cols-5 gap-4 mb-8">
            {acquirers.map(acq => (
              <StatusCard
                key={acq.name}
                acq={acq}
                onTest={handleTest}
                testing={testingAcq === acq.name}
              />
            ))}
          </div>

          {/* Downloads */}
          <div className="t-card p-0 overflow-hidden mb-6">
            <div className="px-5 py-4 border-b border-stone-100">
              <div className="flex items-center gap-2">
                <Download size={15} className="text-stone-400" />
                <p className="text-sm font-semibold text-stone-900">Archivos descargados</p>
                <span className="t-badge t-badge-gray">{downloads.length}</span>
              </div>
              <p className="text-xs text-stone-400 mt-0.5">Archivos descargados automaticamente via SFTP</p>
            </div>
            {loadingDownloads ? (
              <div className="py-8 flex justify-center"><Loader2 size={16} className="animate-spin text-stone-300" /></div>
            ) : downloads.length === 0 ? (
              <p className="text-center text-sm text-stone-400 py-8">Sin descargas registradas</p>
            ) : (
              <table className="t-table">
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>Adquirente</th>
                    <th>Archivo</th>
                    <th className="text-right">Tamano</th>
                    <th>Corrida</th>
                    <th>Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {downloads.map(f => (
                    <tr key={f.id}>
                      <td className="text-[13px] text-stone-500 whitespace-nowrap">
                        {f.uploaded_at ? format(new Date(f.uploaded_at), 'dd MMM, HH:mm', { locale: es }) : '-'}
                      </td>
                      <td><span className={`t-badge ${ACQ_COLORS[f.file_type] || 't-badge-gray'}`}>{f.file_type}</span></td>
                      <td className="text-[13px] text-stone-700 font-mono max-w-xs truncate">{f.original_name}</td>
                      <td className="text-right text-[13px] text-stone-500"><Fmt bytes={f.file_size} /></td>
                      <td className="text-[13px] text-stone-500">#{f.process_id}</td>
                      <td><span className={`t-badge ${f.status === 'parsed' ? 't-badge-emerald' : 't-badge-amber'}`}>{f.status}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Logs */}
          <div className="t-card p-0 overflow-hidden">
            <div className="px-5 py-4 border-b border-stone-100">
              <div className="flex items-center gap-2">
                <Clock size={15} className="text-stone-400" />
                <p className="text-sm font-semibold text-stone-900">Logs de conexion</p>
                <span className="t-badge t-badge-gray">{logs.length}</span>
              </div>
              <p className="text-xs text-stone-400 mt-0.5">Actividad SFTP de corridas recientes</p>
            </div>
            {loadingLogs ? (
              <div className="py-8 flex justify-center"><Loader2 size={16} className="animate-spin text-stone-300" /></div>
            ) : logs.length === 0 ? (
              <p className="text-center text-sm text-stone-400 py-8">Sin logs SFTP</p>
            ) : (
              <table className="t-table">
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>Corrida</th>
                    <th>Stage</th>
                    <th>Nivel</th>
                    <th>Mensaje</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map(log => (
                    <tr key={log.id}>
                      <td className="text-[13px] text-stone-500 whitespace-nowrap">
                        {log.created_at ? format(new Date(log.created_at), 'dd MMM, HH:mm', { locale: es }) : '-'}
                      </td>
                      <td className="text-[13px] text-stone-500">#{log.process_id}</td>
                      <td><span className="t-badge t-badge-blue">{log.stage}</span></td>
                      <td>
                        <span className={clsx('t-badge',
                          log.level === 'error' ? 't-badge-red' :
                          log.level === 'warning' ? 't-badge-amber' : 't-badge-gray'
                        )}>
                          {log.level}
                        </span>
                      </td>
                      <td className="text-[13px] text-stone-700 max-w-lg truncate">{log.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  )
}
