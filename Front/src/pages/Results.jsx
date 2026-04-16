import React, { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { resultsApi, processApi } from '../api/client'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from 'recharts'
import { ChevronRight, Loader2, CheckCircle2, XCircle, Download, ChevronDown, Pencil } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { classificationsApi } from '../api/client'
import clsx from 'clsx'

const TABS = ['Resumen', 'Banregio', 'Por Adquirente', 'Por Comercio']

const CLS_LABELS = {
  kushki_acquirer: 'Kushki',
  bitso_acquirer: 'Bitso',
  unlimit_acquirer: 'Unlimit',
  pagsmile_acquirer: 'Pagsmile',
  stp_acquirer: 'STP',
  settlement_to_merchant: 'Dispersión',
  revenue: 'Revenue',
  investment: 'Inversión',
  tax: 'ISR',
  bank_expense: 'Comisión bancaria',
  currency_sale: 'Venta divisas',
  transfer_between_accounts: 'Traspaso',
  unclassified: 'Sin clasificar',
  ignored: 'Ignorado',
}

const CLS_BADGE = {
  kushki_acquirer: 't-badge-blue',
  bitso_acquirer: 't-badge-violet',
  unlimit_acquirer: 't-badge-blue',
  pagsmile_acquirer: 't-badge-orange',
  stp_acquirer: 't-badge-blue',
  settlement_to_merchant: 't-badge-amber',
  revenue: 't-badge-emerald',
  investment: 't-badge-gray',
  tax: 't-badge-red',
  bank_expense: 't-badge-gray',
  currency_sale: 't-badge-gray',
  transfer_between_accounts: 't-badge-gray',
  unclassified: 't-badge-red',
  ignored: 't-badge-gray',
}

function Fmt({ value }) {
  const n = Number(value || 0)
  if (n === 0) return <span className="text-stone-300">—</span>
  return <span className="font-mono">${n.toLocaleString('es-MX', { minimumFractionDigits: 2 })}</span>
}

// ── Tab: Resumen ──────────────────────────────────────────────────────
function ResumenTab({ processId }) {
  const { data, isLoading } = useQuery({
    queryKey: ['recon-view', processId],
    queryFn: () => resultsApi.reconciliationView(processId).then(r => r.data),
  })
  if (isLoading) return <Loader2 size={20} className="animate-spin text-stone-300 mx-auto mt-12" />
  if (!data) return <p className="text-stone-400 text-sm text-center mt-12">Sin datos</p>

  const s = data.summary
  const byClass = Object.entries(s.by_classification || {})
    .map(([k, v]) => ({ name: CLS_LABELS[k] || k, value: v, key: k }))
    .sort((a, b) => b.value - a.value)

  return (
    <div className="space-y-6">
      {/* KPIs */}
      <div className="grid grid-cols-4 gap-4">
        <div className="t-card">
          <p className="kpi-label">Movimientos</p>
          <p className="kpi-value">{s.total_movements}</p>
        </div>
        <div className="t-card">
          <p className="kpi-label">Reconciliados</p>
          <p className="kpi-value text-emerald-800">{s.classified}</p>
          <div className="progress-track mt-2">
            <div className="progress-fill" style={{ width: `${s.coverage_pct}%`, background: '#047857' }} />
          </div>
          <p className="text-xs text-stone-400 mt-1">{s.coverage_pct}%</p>
        </div>
        <div className="t-card">
          <p className="kpi-label">Pendientes</p>
          <p className="kpi-value text-red-700">{s.unclassified}</p>
        </div>
        <div className="t-card">
          <p className="kpi-label">Ignorados</p>
          <p className="kpi-value text-stone-400">{s.ignored}</p>
        </div>
      </div>

    </div>
  )
}

// ── Classification options for the dropdown ───────────────────────────
const CLS_OPTIONS = [
  { value: 'kushki_acquirer', label: 'Kushki', acquirer: 'kushki' },
  { value: 'bitso_acquirer', label: 'Bitso', acquirer: 'bitso' },
  { value: 'unlimit_acquirer', label: 'Unlimit', acquirer: 'unlimit' },
  { value: 'pagsmile_acquirer', label: 'Pagsmile', acquirer: 'pagsmile' },
  { value: 'stp_acquirer', label: 'STP', acquirer: 'stp' },
  { value: 'settlement_to_merchant', label: 'Dispersión' },
  { value: 'revenue', label: 'Revenue' },
  { value: 'investment', label: 'Inversión' },
  { value: 'tax', label: 'ISR' },
  { value: 'bank_expense', label: 'Comisión bancaria' },
  { value: 'currency_sale', label: 'Venta divisas' },
  { value: 'transfer_between_accounts', label: 'Traspaso' },
  { value: 'ignored', label: 'Ignorar' },
]

// ── Inline classify dropdown ──────────────────────────────────────────
function ClassifyDropdown({ processId, movementIndex, currentCls, onDone }) {
  const [open, setOpen] = useState(false)
  const [notes, setNotes] = useState('')
  const [showNotes, setShowNotes] = useState(false)
  const qc = useQueryClient()

  const mutation = useMutation({
    mutationFn: ({ classification, acquirer }) =>
      classificationsApi.classify(processId, movementIndex, {
        classification,
        acquirer: acquirer || null,
        notes: notes || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['recon-view'] })
      qc.invalidateQueries({ queryKey: ['acquirer-breakdown'] })
      setOpen(false)
      setShowNotes(false)
      if (onDone) onDone()
    },
  })

  function handleSelect(opt) {
    if (opt.value === 'ignored') {
      setShowNotes(true)
      return
    }
    mutation.mutate({ classification: opt.value, acquirer: opt.acquirer })
  }

  function handleIgnore() {
    if (!notes.trim() || notes.trim().length < 3) return
    mutation.mutate({ classification: 'ignored', acquirer: null })
  }

  if (!open) {
    const isUnclassified = currentCls === 'unclassified'
    return (
      <button
        onClick={() => setOpen(true)}
        className={`t-badge ${CLS_BADGE[currentCls] || 't-badge-gray'} cursor-pointer hover:opacity-80 transition-opacity`}
        title={isUnclassified ? 'Clasificar este movimiento' : 'Reclasificar'}
      >
        {CLS_LABELS[currentCls] || currentCls}
        {isUnclassified && <Pencil size={10} className="ml-1" />}
      </button>
    )
  }

  return (
    <div className="relative">
      {!showNotes ? (
        <div className="absolute z-30 top-0 left-0 bg-white border border-stone-200 rounded-lg shadow-lg py-1 w-48 max-h-64 overflow-y-auto">
          <div className="px-3 py-1.5 text-[10px] font-semibold text-stone-400 uppercase tracking-wider">
            Clasificar como
          </div>
          {CLS_OPTIONS.map(opt => (
            <button
              key={opt.value}
              onClick={() => handleSelect(opt)}
              disabled={mutation.isPending}
              className="w-full text-left px-3 py-1.5 text-[13px] text-stone-700 hover:bg-stone-50 transition-colors flex items-center gap-2"
            >
              <span className={`t-badge ${CLS_BADGE[opt.value] || 't-badge-gray'}`} style={{ fontSize: 10 }}>
                {opt.label}
              </span>
            </button>
          ))}
          <div className="border-t border-stone-100 mt-1 pt-1">
            <button
              onClick={() => setOpen(false)}
              className="w-full text-left px-3 py-1.5 text-[12px] text-stone-400 hover:text-stone-600"
            >
              Cancelar
            </button>
          </div>
        </div>
      ) : (
        <div className="absolute z-30 top-0 left-0 bg-white border border-stone-200 rounded-lg shadow-lg p-3 w-56">
          <p className="text-[11px] font-semibold text-stone-500 mb-1">Razon para ignorar</p>
          <input
            className="t-input text-[12px] h-8 mb-2"
            placeholder="Ej: Comision bancaria recurrente"
            value={notes}
            onChange={e => setNotes(e.target.value)}
            autoFocus
          />
          <div className="flex gap-2">
            <button
              onClick={handleIgnore}
              disabled={!notes.trim() || notes.trim().length < 3 || mutation.isPending}
              className="btn-primary text-[11px] px-3 py-1"
            >
              {mutation.isPending ? 'Guardando...' : 'Ignorar'}
            </button>
            <button onClick={() => { setShowNotes(false); setOpen(false) }} className="text-[11px] text-stone-400">
              Cancelar
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Tab: Banregio ─────────────────────────────────────────────────────
function BanregioTab({ processId }) {
  const [filter, setFilter] = useState('all')
  const { data, isLoading } = useQuery({
    queryKey: ['recon-view', processId, filter],
    queryFn: () => resultsApi.reconciliationView(processId, filter).then(r => r.data),
  })
  if (isLoading) return <Loader2 size={20} className="animate-spin text-stone-300 mx-auto mt-12" />
  if (!data) return <p className="text-stone-400 text-sm text-center mt-12">Sin datos</p>

  const s = data.summary

  return (
    <div className="space-y-4">
      {/* Coverage bar */}
      <div className="t-card flex items-center gap-6 py-4">
        <div className="flex-1">
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm font-medium text-stone-700">Cobertura Banregio</span>
            <span className="text-sm font-semibold text-stone-900">{s.coverage_pct}%</span>
          </div>
          <div className="progress-track h-2">
            <div className="progress-fill" style={{
              width: `${s.coverage_pct}%`,
              background: s.coverage_pct >= 100 ? '#047857' : s.coverage_pct >= 80 ? '#1c1917' : '#dc2626',
            }} />
          </div>
        </div>
        <div className="text-right text-xs text-stone-500">
          <span className="text-emerald-800 font-semibold">{s.classified}</span> reconciliados ·{' '}
          <span className="text-red-700 font-semibold">{s.unclassified}</span> pendientes
        </div>
      </div>

      {/* Filter pills */}
      <div className="flex gap-1">
        {[
          { key: 'all', label: `Todos (${s.total_movements})` },
          { key: 'reconciled', label: `Reconciliados (${s.classified})` },
          { key: 'pending', label: `Pendientes (${s.unclassified})` },
        ].map(f => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={clsx(
              'px-3 py-1.5 text-[13px] font-medium rounded-lg transition-all',
              filter === f.key
                ? 'bg-stone-900 text-white'
                : 'bg-white text-stone-500 border border-stone-200 hover:bg-stone-50'
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Movements table */}
      <div className="t-card p-0 overflow-hidden">
        <div className="max-h-[500px] overflow-y-auto">
          <table className="t-table">
            <thead className="sticky top-0 bg-white z-10">
              <tr>
                <th style={{ width: 40 }}></th>
                <th>Fecha</th>
                <th>Descripcion</th>
                <th className="text-right">Cargo</th>
                <th className="text-right">Abono</th>
                <th>Clasificacion</th>
                <th>Adquirente</th>
              </tr>
            </thead>
            <tbody>
              {data.movements.map(m => (
                <tr key={m.index}>
                  <td className="text-center">
                    {m.is_reconciled
                      ? <CheckCircle2 size={15} className="text-emerald-700 inline" />
                      : <XCircle size={15} className="text-red-400 inline" />
                    }
                  </td>
                  <td className="text-stone-500 text-[13px] whitespace-nowrap">{m.date}</td>
                  <td className="text-stone-700 text-[13px] max-w-xs truncate">{m.description}</td>
                  <td className="text-right text-red-700 text-[13px]">
                    {m.debit > 0 ? <Fmt value={m.debit} /> : ''}
                  </td>
                  <td className="text-right text-emerald-800 text-[13px]">
                    {m.credit > 0 ? <Fmt value={m.credit} /> : ''}
                  </td>
                  <td>
                    <ClassifyDropdown
                      processId={processId}
                      movementIndex={m.index}
                      currentCls={m.classification}
                    />
                  </td>
                  <td className="text-stone-500 text-[13px]">{m.acquirer || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="px-4 py-2 border-t border-stone-100 text-xs text-stone-400">
          Mostrando {data.showing} de {s.total_movements} movimientos
        </div>
      </div>
    </div>
  )
}

// ── Tab: Por Adquirente ───────────────────────────────────────────────
function AcquirerTab({ processId }) {
  const { data, isLoading } = useQuery({
    queryKey: ['acquirer-breakdown', processId],
    queryFn: () => resultsApi.acquirerBreakdown(processId).then(r => r.data),
  })
  if (isLoading) return <Loader2 size={20} className="animate-spin text-stone-300 mx-auto mt-12" />
  if (!data) return <p className="text-stone-400 text-sm text-center mt-12">Sin datos</p>

  return (
    <div className="space-y-4">
      {data.acquirers.map(acq => (
        <AcquirerSection key={acq.name} acq={acq} />
      ))}

      {data.other_categories.length > 0 && (
        <div className="t-card">
          <p className="text-sm font-semibold text-stone-900 mb-3">Otras categorias</p>
          <table className="t-table">
            <thead>
              <tr>
                <th>Categoria</th>
                <th className="text-right"># Movimientos</th>
                <th className="text-right">Monto neto</th>
              </tr>
            </thead>
            <tbody>
              {data.other_categories.map(c => (
                <tr key={c.name}>
                  <td>
                    <span className={`t-badge ${CLS_BADGE[c.name] || 't-badge-gray'}`}>
                      {CLS_LABELS[c.name] || c.name}
                    </span>
                  </td>
                  <td className="text-right text-stone-600">{c.count}</td>
                  <td className="text-right"><Fmt value={c.total_amount} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function AcquirerSection({ acq }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="t-card">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="t-badge t-badge-blue capitalize">{acq.name}</span>
          <span className="text-sm text-stone-500">{acq.deposits.length} depositos</span>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-sm font-semibold text-stone-900"><Fmt value={acq.total_amount} /></span>
          <ChevronDown size={16} className={clsx('text-stone-400 transition-transform', open && 'rotate-180')} />
        </div>
      </button>

      {open && (
        <div className="mt-4 space-y-4">
          {/* Deposits */}
          <table className="t-table">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Descripcion</th>
                <th className="text-right">Monto</th>
              </tr>
            </thead>
            <tbody>
              {acq.deposits.map((d, i) => (
                <tr key={i}>
                  <td className="text-stone-500 text-[13px]">{d.date}</td>
                  <td className="text-stone-700 text-[13px] max-w-sm truncate">{d.description}</td>
                  <td className="text-right text-emerald-800"><Fmt value={d.amount} /></td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Merchant detail (Kushki) */}
          {acq.merchants && acq.merchants.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-stone-500 uppercase tracking-wider mb-2">
                Desglose por comercio
              </p>
              <table className="t-table">
                <thead>
                  <tr>
                    <th>Comercio</th>
                    <th className="text-right"># Txns</th>
                    <th className="text-right">Bruto</th>
                    <th className="text-right">Comision</th>
                    <th className="text-right">Deposito neto</th>
                  </tr>
                </thead>
                <tbody>
                  {acq.merchants.sort((a, b) => (b.net_deposit || 0) - (a.net_deposit || 0)).map((m, i) => (
                    <tr key={i}>
                      <td className="text-stone-700 font-medium text-[13px]">{m.merchant_name}</td>
                      <td className="text-right text-stone-500">{Number(m.tx_count || 0).toLocaleString()}</td>
                      <td className="text-right"><Fmt value={m.gross_amount} /></td>
                      <td className="text-right text-amber-700"><Fmt value={m.commission} /></td>
                      <td className="text-right text-emerald-800 font-medium"><Fmt value={m.net_deposit} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Tab: Por Comercio ─────────────────────────────────────────────────
function MerchantTab({ processId }) {
  const { data, isLoading } = useQuery({
    queryKey: ['acquirer-breakdown', processId],
    queryFn: () => resultsApi.acquirerBreakdown(processId).then(r => r.data),
  })
  if (isLoading) return <Loader2 size={20} className="animate-spin text-stone-300 mx-auto mt-12" />
  if (!data) return <p className="text-stone-400 text-sm text-center mt-12">Sin datos</p>

  // Collect all merchants from all acquirers
  const merchants = []
  for (const acq of data.acquirers) {
    if (acq.merchants) {
      for (const m of acq.merchants) {
        merchants.push({ ...m, acquirer: acq.name })
      }
    } else {
      // No merchant detail — show acquirer as a single line
      merchants.push({
        merchant_name: acq.name,
        acquirer: acq.name,
        tx_count: acq.deposits.length,
        gross_amount: acq.total_amount,
        commission: 0,
        net_deposit: acq.total_amount,
      })
    }
  }
  merchants.sort((a, b) => (b.net_deposit || 0) - (a.net_deposit || 0))

  return (
    <div className="t-card p-0 overflow-hidden">
      <div className="px-5 py-3 border-b border-stone-100">
        <p className="text-sm font-semibold text-stone-900">{merchants.length} comercios</p>
      </div>
      <div className="max-h-[500px] overflow-y-auto">
        <table className="t-table">
          <thead className="sticky top-0 bg-white z-10">
            <tr>
              <th>Comercio</th>
              <th>Adquirente</th>
              <th className="text-right"># Txns</th>
              <th className="text-right">Monto bruto</th>
              <th className="text-right">Comision</th>
              <th className="text-right">Deposito neto</th>
            </tr>
          </thead>
          <tbody>
            {merchants.map((m, i) => (
              <tr key={i}>
                <td className="text-stone-800 font-medium text-[13px]">{m.merchant_name}</td>
                <td><span className="t-badge t-badge-blue capitalize">{m.acquirer}</span></td>
                <td className="text-right text-stone-500">{Number(m.tx_count || 0).toLocaleString()}</td>
                <td className="text-right"><Fmt value={m.gross_amount} /></td>
                <td className="text-right text-amber-700"><Fmt value={m.commission} /></td>
                <td className="text-right text-emerald-800 font-medium"><Fmt value={m.net_deposit} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────
export default function Results() {
  const { id } = useParams()
  const [tab, setTab] = useState(0)
  const [exporting, setExporting] = useState(false)

  const { data: proc } = useQuery({
    queryKey: ['process', id],
    queryFn: () => processApi.get(id).then(r => r.data),
  })

  async function handleExport() {
    if (exporting) return
    try {
      setExporting(true)
      const response = await resultsApi.exportReconciliation(id)
      const disposition = response.headers?.['content-disposition']
      let filename = `RECONCILIACION_${id}.xlsx`
      if (disposition) {
        const m = disposition.match(/filename\*?=(?:UTF-8''|"?)([^";]+)/i)
        if (m?.[1]) filename = decodeURIComponent(m[1].replace(/"/g, '').trim())
      }
      const url = window.URL.createObjectURL(new Blob([response.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch { /* ignore */ } finally {
      setExporting(false)
    }
  }

  return (
    <div className="px-8 py-6" style={{ maxWidth: 1420 }}>
      {/* Header */}
      <div className="flex items-center justify-between mb-1">
        <div>
          <div className="flex items-center gap-2 text-stone-400 text-sm mb-1">
            <Link to="/processes" className="hover:text-stone-600">Corridas</Link>
            <ChevronRight size={12} />
            <Link to={`/processes/${id}`} className="hover:text-stone-600">{proc?.name}</Link>
            <ChevronRight size={12} />
            <span className="text-stone-700">Resultados</span>
          </div>
          <h1 className="text-xl font-semibold text-stone-900">Reconciliacion</h1>
          {proc && (
            <p className="text-sm text-stone-500 mt-0.5">
              {proc.bank_account || 'Banregio'} · {proc.period_year}-{String(proc.period_month).padStart(2, '0')} · {proc.name}
            </p>
          )}
        </div>
        <button onClick={handleExport} disabled={exporting} className="btn-secondary flex items-center gap-2">
          {exporting
            ? <><Loader2 size={14} className="animate-spin" /> Exportando...</>
            : <><Download size={14} /> Exportar Excel</>
          }
        </button>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-0 border-b border-stone-200 mt-4 mb-6">
        {TABS.map((t, i) => (
          <button
            key={t}
            onClick={() => setTab(i)}
            className={clsx('t-tab', tab === i && 'active')}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Content */}
      {tab === 0 && <ResumenTab processId={id} />}
      {tab === 1 && <BanregioTab processId={id} />}
      {tab === 2 && <AcquirerTab processId={id} />}
      {tab === 3 && <MerchantTab processId={id} />}
    </div>
  )
}
