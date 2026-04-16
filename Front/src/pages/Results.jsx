import React, { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { resultsApi, processApi } from '../api/client'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from 'recharts'
import { ChevronRight, Loader2, CheckCircle2, XCircle, Download, ChevronDown, Pencil } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { classificationsApi, adjustmentsApi } from '../api/client'
import clsx from 'clsx'

const TABS = ['Resumen', 'Banregio', 'Por Adquirente', 'Por Comercio', 'Auditoría', 'Ajustes']

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
              background: s.coverage_pct >= 100 ? '#047857' : s.coverage_pct >= 80 ? '#2F1503' : '#dc2626',
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
              <div className="overflow-x-auto">
              <table className="t-table">
                <thead>
                  <tr>
                    <th>Comercio</th>
                    <th className="text-right"># Txns</th>
                    <th className="text-right">Bruto</th>
                    <th className="text-right">Ajustes</th>
                    <th className="text-right">Com. Kushki</th>
                    <th className="text-right">IVA Kushki</th>
                    <th className="text-right">Com+IVA</th>
                    <th className="text-right">RR Retenido</th>
                    <th className="text-right">Refund</th>
                    <th className="text-right">Chargeback</th>
                    <th className="text-right">RR Liberado</th>
                    <th className="text-right">Dep. Neto</th>
                    <th className="text-right">Com. Tonder</th>
                    <th className="text-right">IVA 16%</th>
                    <th className="text-right">Tonder c/IVA</th>
                  </tr>
                </thead>
                <tbody>
                  {acq.merchants.sort((a, b) => (b.net_deposit || 0) - (a.net_deposit || 0)).map((m, i) => (
                    <tr key={i}>
                      <td className="text-stone-700 font-medium text-[13px] whitespace-nowrap">{m.merchant_name}</td>
                      <td className="text-right text-stone-500">{Number(m.tx_count || 0).toLocaleString()}</td>
                      <td className="text-right"><Fmt value={m.gross_amount} /></td>
                      <td className="text-right"><Fmt value={m.adjustments} /></td>
                      <td className="text-right"><Fmt value={m.kushki_commission} /></td>
                      <td className="text-right"><Fmt value={m.iva_kushki_commission} /></td>
                      <td className="text-right text-amber-700"><Fmt value={m.commission} /></td>
                      <td className="text-right"><Fmt value={m.rolling_reserve} /></td>
                      <td className="text-right"><Fmt value={m.refund} /></td>
                      <td className="text-right text-red-700"><Fmt value={m.chargeback} /></td>
                      <td className="text-right"><Fmt value={m.rr_released} /></td>
                      <td className="text-right text-emerald-800 font-medium"><Fmt value={m.net_deposit} /></td>
                      <td className="text-right"><Fmt value={m.tonder_fee} /></td>
                      <td className="text-right"><Fmt value={m.tonder_iva} /></td>
                      <td className="text-right text-stone-900 font-medium"><Fmt value={m.tonder_fee_iva} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
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
        <div className="overflow-x-auto">
        <table className="t-table">
          <thead className="sticky top-0 bg-white z-10">
            <tr>
              <th>Comercio</th>
              <th>Adquirente</th>
              <th className="text-right"># Txns</th>
              <th className="text-right">Bruto</th>
              <th className="text-right">Ajustes</th>
              <th className="text-right">Com. Kushki</th>
              <th className="text-right">IVA Kushki</th>
              <th className="text-right">Com+IVA</th>
              <th className="text-right">RR Retenido</th>
              <th className="text-right">Refund</th>
              <th className="text-right">Chargeback</th>
              <th className="text-right">RR Liberado</th>
              <th className="text-right">Dep. Neto</th>
              <th className="text-right">Com. Tonder</th>
              <th className="text-right">IVA 16%</th>
              <th className="text-right">Tonder c/IVA</th>
            </tr>
          </thead>
          <tbody>
            {merchants.map((m, i) => (
              <tr key={i}>
                <td className="text-stone-800 font-medium text-[13px] whitespace-nowrap">{m.merchant_name}</td>
                <td><span className="t-badge t-badge-blue capitalize">{m.acquirer}</span></td>
                <td className="text-right text-stone-500">{Number(m.tx_count || 0).toLocaleString()}</td>
                <td className="text-right"><Fmt value={m.gross_amount} /></td>
                <td className="text-right"><Fmt value={m.adjustments} /></td>
                <td className="text-right"><Fmt value={m.kushki_commission} /></td>
                <td className="text-right"><Fmt value={m.iva_kushki_commission} /></td>
                <td className="text-right text-amber-700"><Fmt value={m.commission} /></td>
                <td className="text-right"><Fmt value={m.rolling_reserve} /></td>
                <td className="text-right"><Fmt value={m.refund} /></td>
                <td className="text-right text-red-700"><Fmt value={m.chargeback} /></td>
                <td className="text-right"><Fmt value={m.rr_released} /></td>
                <td className="text-right text-emerald-800 font-medium"><Fmt value={m.net_deposit} /></td>
                <td className="text-right"><Fmt value={m.tonder_fee} /></td>
                <td className="text-right"><Fmt value={m.tonder_iva} /></td>
                <td className="text-right text-stone-900 font-medium"><Fmt value={m.tonder_fee_iva} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </div>
    </div>
  )
}

// ── Tab: Ajustes ──────────────────────────────────────────────────────

const ADJ_TYPES = [
  { value: 'DELAY_DEPOSIT', label: 'Depósito en tránsito' },
  { value: 'FEE_CORRECTION', label: 'Corrección de comisión' },
  { value: 'AUTOREFUND_OFFSET', label: 'Offset por autorefund' },
  { value: 'DUPLICATE_PAYMENT', label: 'Pago duplicado' },
  { value: 'BANK_ERROR', label: 'Error bancario' },
  { value: 'ACQUIRER_ERROR', label: 'Error de adquirente' },
  { value: 'MANUAL_BITSO', label: 'Ajuste Bitso manual' },
  { value: 'OTHER', label: 'Otro' },
]

const ADJ_AFFECTS = [
  { value: 'expected', label: 'Esperado (adquirente)' },
  { value: 'received', label: 'Recibido (Banregio)' },
  { value: 'delta', label: 'Delta (diferencia)' },
]

function AjustesTab({ processId }) {
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({
    adjustment_type: 'FEE_CORRECTION',
    direction: 'SUBTRACT',
    amount: '',
    affects: 'expected',
    merchant_name: '',
    description: '',
    evidence_url: '',
  })
  const qc = useQueryClient()

  const { data: summary, isLoading: loadingSummary } = useQuery({
    queryKey: ['adj-summary', processId],
    queryFn: () => adjustmentsApi.summary(processId).then(r => r.data),
  })
  const { data: adjustments = [], isLoading } = useQuery({
    queryKey: ['adjustments', processId],
    queryFn: () => adjustmentsApi.list(processId).then(r => r.data),
  })

  const createMut = useMutation({
    mutationFn: (data) => adjustmentsApi.create(processId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['adjustments'] })
      qc.invalidateQueries({ queryKey: ['adj-summary'] })
      setShowForm(false)
      setForm({ adjustment_type: 'FEE_CORRECTION', direction: 'SUBTRACT', amount: '', affects: 'expected', merchant_name: '', description: '', evidence_url: '' })
    },
  })
  const approveMut = useMutation({
    mutationFn: ({ id, notes }) => adjustmentsApi.approve(id, notes),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['adjustments'] }); qc.invalidateQueries({ queryKey: ['adj-summary'] }) },
  })
  const rejectMut = useMutation({
    mutationFn: ({ id, notes }) => adjustmentsApi.reject(id, notes),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['adjustments'] }); qc.invalidateQueries({ queryKey: ['adj-summary'] }) },
  })
  const deleteMut = useMutation({
    mutationFn: (id) => adjustmentsApi.remove(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['adjustments'] }); qc.invalidateQueries({ queryKey: ['adj-summary'] }) },
  })

  if (isLoading) return <Loader2 size={20} className="animate-spin text-stone-300 mx-auto mt-12" />

  const s = summary || { total: 0, by_status: { pending: 0, approved: 0, rejected: 0 }, net_adjustment: 0 }

  function handleCreate(e) {
    e.preventDefault()
    createMut.mutate({
      ...form,
      amount: parseFloat(form.amount),
    })
  }

  return (
    <div className="space-y-4">
      {/* KPIs */}
      <div className="grid grid-cols-4 gap-4">
        <div className="t-card">
          <p className="kpi-label">Total ajustes</p>
          <p className="kpi-value">{s.total}</p>
        </div>
        <div className="t-card">
          <p className="kpi-label">Pendientes</p>
          <p className="kpi-value" style={{ color: s.by_status.pending > 0 ? '#92400E' : '#78716C' }}>{s.by_status.pending}</p>
        </div>
        <div className="t-card">
          <p className="kpi-label">Aprobados</p>
          <p className="kpi-value" style={{ color: '#047857' }}>{s.by_status.approved}</p>
        </div>
        <div className="t-card">
          <p className="kpi-label">Ajuste neto</p>
          <p className="kpi-value"><Fmt value={s.net_adjustment} /></p>
        </div>
      </div>

      {/* Create button */}
      <div className="flex justify-end">
        <button onClick={() => setShowForm(!showForm)} className="btn-primary flex items-center gap-2">
          {showForm ? 'Cancelar' : '+ Crear ajuste'}
        </button>
      </div>

      {/* Create form */}
      {showForm && (
        <form onSubmit={handleCreate} className="t-card space-y-4">
          <p className="text-sm font-semibold text-stone-900">Nuevo ajuste</p>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="t-label">Tipo</label>
              <select className="t-input" value={form.adjustment_type} onChange={e => setForm(f => ({ ...f, adjustment_type: e.target.value }))}>
                {ADJ_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </div>
            <div>
              <label className="t-label">Dirección</label>
              <div className="flex gap-2 mt-1">
                {['ADD', 'SUBTRACT'].map(d => (
                  <button key={d} type="button"
                    onClick={() => setForm(f => ({ ...f, direction: d }))}
                    className={clsx('px-4 py-2 rounded-lg text-sm font-medium border transition-all',
                      form.direction === d ? 'bg-stone-900 text-white border-stone-900' : 'bg-white text-stone-500 border-stone-200'
                    )}>
                    {d === 'ADD' ? '+ Sumar' : '− Restar'}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="t-label">Monto (MXN)</label>
              <input type="number" step="0.01" className="t-input" placeholder="0.00"
                value={form.amount} onChange={e => setForm(f => ({ ...f, amount: e.target.value }))} required />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="t-label">Afecta</label>
              <select className="t-input" value={form.affects} onChange={e => setForm(f => ({ ...f, affects: e.target.value }))}>
                {ADJ_AFFECTS.map(a => <option key={a.value} value={a.value}>{a.label}</option>)}
              </select>
            </div>
            <div>
              <label className="t-label">Comercio (opcional)</label>
              <input className="t-input" placeholder="Ej: AFUN" value={form.merchant_name}
                onChange={e => setForm(f => ({ ...f, merchant_name: e.target.value }))} />
            </div>
            <div>
              <label className="t-label">Evidencia URL (opcional)</label>
              <input className="t-input" placeholder="https://..." value={form.evidence_url}
                onChange={e => setForm(f => ({ ...f, evidence_url: e.target.value }))} />
            </div>
          </div>
          <div>
            <label className="t-label">Descripción (min. 10 caracteres)</label>
            <textarea className="t-input" style={{ height: 'auto', minHeight: 60 }} placeholder="Explica la razón del ajuste..."
              value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} required />
          </div>
          {createMut.error && (
            <p className="text-sm text-red-600">{createMut.error.response?.data?.detail || 'Error al crear ajuste'}</p>
          )}
          <div className="flex justify-end">
            <button type="submit" disabled={createMut.isPending || !form.amount || form.description.length < 10}
              className="btn-primary">
              {createMut.isPending ? 'Creando...' : 'Crear ajuste'}
            </button>
          </div>
        </form>
      )}

      {/* Adjustments table */}
      {adjustments.length === 0 ? (
        <div className="t-card text-center py-8">
          <p className="text-stone-400 text-sm">Sin ajustes registrados para esta corrida</p>
          <p className="text-stone-300 text-xs mt-1">Crea un ajuste para explicar diferencias en la reconciliación</p>
        </div>
      ) : (
        <div className="t-card p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="t-table">
              <thead>
                <tr>
                  <th>Tipo</th>
                  <th>Dir.</th>
                  <th className="text-right">Monto</th>
                  <th>Afecta</th>
                  <th>Comercio</th>
                  <th>Descripción</th>
                  <th>Estado</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {adjustments.map(adj => {
                  const typeLabel = ADJ_TYPES.find(t => t.value === adj.adjustment_type)?.label || adj.adjustment_type
                  return (
                    <tr key={adj.id}>
                      <td className="text-[13px] text-stone-700 whitespace-nowrap">{typeLabel}</td>
                      <td>
                        <span className={`t-badge ${adj.direction === 'ADD' ? 't-badge-emerald' : 't-badge-red'}`}>
                          {adj.direction === 'ADD' ? '+ Sumar' : '− Restar'}
                        </span>
                      </td>
                      <td className="text-right font-medium text-[13px]"><Fmt value={adj.amount} /></td>
                      <td className="text-[13px] text-stone-500">{adj.affects}</td>
                      <td className="text-[13px] text-stone-500">{adj.merchant_name || '—'}</td>
                      <td className="text-[13px] text-stone-600 max-w-xs truncate">{adj.description}</td>
                      <td>
                        <span className={`t-badge ${
                          adj.status === 'approved' ? 't-badge-emerald' :
                          adj.status === 'rejected' ? 't-badge-red' : 't-badge-amber'
                        }`}>
                          {adj.status === 'approved' ? 'Aprobado' : adj.status === 'rejected' ? 'Rechazado' : 'Pendiente'}
                        </span>
                      </td>
                      <td>
                        {adj.status === 'pending' && (
                          <div className="flex gap-1">
                            <button
                              onClick={() => approveMut.mutate({ id: adj.id })}
                              disabled={approveMut.isPending}
                              className="text-[11px] px-2 py-1 rounded bg-emerald-50 text-emerald-700 hover:bg-emerald-100 transition-colors"
                            >
                              Aprobar
                            </button>
                            <button
                              onClick={() => rejectMut.mutate({ id: adj.id })}
                              disabled={rejectMut.isPending}
                              className="text-[11px] px-2 py-1 rounded bg-red-50 text-red-700 hover:bg-red-100 transition-colors"
                            >
                              Rechazar
                            </button>
                            <button
                              onClick={() => deleteMut.mutate(adj.id)}
                              disabled={deleteMut.isPending}
                              className="text-[11px] px-2 py-1 rounded text-stone-400 hover:text-red-600 transition-colors"
                            >
                              Eliminar
                            </button>
                          </div>
                        )}
                        {adj.status !== 'pending' && adj.reviewed_by && (
                          <span className="text-[11px] text-stone-400">
                            por #{adj.reviewed_by}
                          </span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {(approveMut.error || rejectMut.error) && (
            <div className="px-4 py-2 text-sm text-red-600 bg-red-50 border-t border-red-100">
              {(approveMut.error || rejectMut.error)?.response?.data?.detail || 'Error en la operación'}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Tab: Auditoría ────────────────────────────────────────────────────
function AuditTab({ processId }) {
  const { data, isLoading } = useQuery({
    queryKey: ['audit', processId],
    queryFn: () => resultsApi.audit(processId).then(r => r.data),
  })
  if (isLoading) return <Loader2 size={20} className="animate-spin text-stone-300 mx-auto mt-12" />
  if (!data) return <p className="text-stone-400 text-sm text-center mt-12">Sin datos</p>

  const VERDICT_STYLE = {
    VERIFIED: { label: 'Verificado', cls: 't-badge t-badge-emerald' },
    DISCREPANCY: { label: 'Discrepancia', cls: 't-badge t-badge-red' },
    NO_ACQUIRER_REPORT: { label: 'Sin reporte', cls: 't-badge t-badge-gray' },
    PARTIAL: { label: 'Parcial', cls: 't-badge t-badge-amber' },
    NO_DATA: { label: 'Sin datos', cls: 't-badge t-badge-gray' },
  }
  const STATUS_ICON = {
    MATCHED: { icon: '✓', color: 'text-blue-600' },
    MATCHED_AMOUNT_ONLY: { icon: '≈', color: 'text-amber-600' },
    UNMATCHED_ACQUIRER: { icon: '✗', color: 'text-red-600' },
    UNMATCHED_BANREGIO: { icon: '?', color: 'text-red-600' },
    BANREGIO_ONLY: { icon: '—', color: 'text-stone-400' },
  }

  const ov = VERDICT_STYLE[data.overall_verdict] || VERDICT_STYLE.NO_DATA

  return (
    <div className="space-y-4">
      {/* Overall verdict */}
      <div className="t-card flex items-center justify-between py-4">
        <div>
          <p className="text-sm font-medium text-stone-700">Veredicto general</p>
          <p className="text-xs text-stone-400 mt-0.5">Cruce de depósitos de adquirentes vs estado de cuenta Banregio</p>
        </div>
        <span className={ov.cls}>{ov.label}</span>
      </div>

      {/* Per acquirer */}
      {data.acquirers.map(acq => {
        const s = acq.summary
        const v = VERDICT_STYLE[s.verdict] || VERDICT_STYLE.NO_DATA
        return (
          <div key={acq.name} className="t-card">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <span className="t-badge t-badge-blue capitalize">{acq.name}</span>
                <span className={v.cls}>{v.label}</span>
              </div>
              {s.acquirer_total != null && (
                <div className="text-right text-xs text-stone-500">
                  Adquirente: <Fmt value={s.acquirer_total} /> · Banregio: <Fmt value={s.banregio_total} /> · Delta: <Fmt value={s.delta} />
                </div>
              )}
            </div>

            {s.note && (
              <p className="text-xs text-stone-400 mb-3">{s.note}</p>
            )}

            {acq.matches.length > 0 && (
              <table className="t-table">
                <thead>
                  <tr>
                    <th style={{ width: 30 }}></th>
                    <th>Fecha</th>
                    {s.acquirer_total != null && <th className="text-right">Dep. Adquirente</th>}
                    <th className="text-right">Abono Banregio</th>
                    {s.acquirer_total != null && <th className="text-right">Delta</th>}
                    <th>Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {acq.matches.map((m, i) => {
                    const st = STATUS_ICON[m.status] || { icon: '?', color: 'text-stone-400' }
                    return (
                      <tr key={i}>
                        <td className={`text-center font-bold ${st.color}`}>{st.icon}</td>
                        <td className="text-stone-600 text-[13px]">{m.date}</td>
                        {s.acquirer_total != null && (
                          <td className="text-right text-[13px]">
                            {m.acquirer_amount != null ? <Fmt value={m.acquirer_amount} /> : '—'}
                          </td>
                        )}
                        <td className="text-right text-[13px]">
                          {m.banregio_amount != null ? <Fmt value={m.banregio_amount} /> : '—'}
                        </td>
                        {s.acquirer_total != null && (
                          <td className={`text-right text-[13px] font-medium ${
                            m.delta === 0 ? 'text-stone-300' : 'text-red-600'
                          }`}>
                            <Fmt value={m.delta} />
                          </td>
                        )}
                        <td className="text-[12px] text-stone-400">{m.status.replace(/_/g, ' ')}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}

            {/* Summary row */}
            {s.matched > 0 && (
              <div className="flex gap-4 mt-3 text-xs text-stone-500">
                <span>{s.matched} conciliados</span>
                {s.mismatched > 0 && <span className="text-red-600">{s.mismatched} con diferencia</span>}
                {s.unmatched_acquirer > 0 && <span className="text-red-600">{s.unmatched_acquirer} sin match en Banregio</span>}
                {s.unmatched_banregio > 0 && <span className="text-amber-600">{s.unmatched_banregio} sin match en adquirente</span>}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────
export default function Results() {
  const { id } = useParams()
  const [tab, setTab] = useState(0)
  const [exporting, setExporting] = useState(false)
  const qc = useQueryClient()

  const { data: proc } = useQuery({
    queryKey: ['process', id],
    queryFn: () => processApi.get(id).then(r => r.data),
  })

  const { data: coverage } = useQuery({
    queryKey: ['coverage', id],
    queryFn: () => classificationsApi.coverage(id).then(r => r.data),
  })

  const { data: adjSummary } = useQuery({
    queryKey: ['adj-summary', id],
    queryFn: () => adjustmentsApi.summary(id).then(r => r.data),
  })

  const reconcileMut = useMutation({
    mutationFn: () => processApi.reconcile(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['process', id] }) },
  })

  const unreconcileMut = useMutation({
    mutationFn: () => processApi.unreconcile(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['process', id] }) },
  })

  const isReconciled = proc?.status === 'reconciled'
  const coveragePct = coverage?.coverage_pct ?? 0
  const pendingAdj = adjSummary?.by_status?.pending ?? 0
  const canReconcile = coveragePct >= 100 && pendingAdj === 0 && !isReconciled

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
        <div className="flex items-center gap-2">
          {isReconciled ? (
            <>
              <span className="t-badge t-badge-emerald flex items-center gap-1.5 px-3 py-1.5">
                <CheckCircle2 size={13} /> Reconciliado
              </span>
              <button
                onClick={() => unreconcileMut.mutate()}
                disabled={unreconcileMut.isPending}
                className="text-xs text-stone-400 hover:text-stone-600 transition-colors"
              >
                Deshacer
              </button>
            </>
          ) : (
            <button
              onClick={() => reconcileMut.mutate()}
              disabled={!canReconcile || reconcileMut.isPending}
              className="btn-primary flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
              title={
                coveragePct < 100
                  ? `Cobertura: ${coveragePct.toFixed(1)}% (requiere 100%)`
                  : pendingAdj > 0
                  ? `${pendingAdj} ajustes pendientes de aprobación`
                  : 'Marcar como reconciliado'
              }
            >
              {reconcileMut.isPending
                ? <><Loader2 size={14} className="animate-spin" /> Reconciliando...</>
                : <><CheckCircle2 size={14} /> Reconciliar</>
              }
            </button>
          )}
          <button onClick={handleExport} disabled={exporting} className="btn-secondary flex items-center gap-2">
            {exporting
              ? <><Loader2 size={14} className="animate-spin" /> Exportando...</>
              : <><Download size={14} /> Exportar Excel</>
            }
          </button>
        </div>
        {reconcileMut.error && (
          <p className="text-xs text-red-600 text-right mt-1">
            {reconcileMut.error.response?.data?.detail || 'Error al reconciliar'}
          </p>
        )}
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
      {tab === 4 && <AuditTab processId={id} />}
      {tab === 5 && <AjustesTab processId={id} />}
    </div>
  )
}
