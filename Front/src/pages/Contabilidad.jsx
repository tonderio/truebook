import React, { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { processApi } from '../api/client'
import {
  Plus, Loader2, Trash2, X, Calendar, Cpu, ChevronRight,
  Search, ArrowRight, CheckCircle2,
} from 'lucide-react'
import StatusBadge from '../components/ui/StatusBadge'
import { format } from 'date-fns'
import { es } from 'date-fns/locale'
import clsx from 'clsx'

const MONTHS = [
  'Enero','Febrero','Marzo','Abril','Mayo','Junio',
  'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'
]
const BANK_ACCOUNTS = ['Banregio']
const ACQUIRERS = ['OXXOPay', 'Bitso', 'Kushki', 'STP']

const ACQ_COLORS = {
  OXXOPay: { bg: 'bg-amber-50', border: 'border-amber-200', text: 'text-amber-700' },
  Bitso:   { bg: 'bg-emerald-50', border: 'border-emerald-200', text: 'text-emerald-700' },
  Kushki:  { bg: 'bg-blue-50', border: 'border-blue-200', text: 'text-blue-700' },
  STP:     { bg: 'bg-violet-50', border: 'border-violet-200', text: 'text-violet-700' },
}

const STATUS_FILTERS = [
  { value: 'all', label: 'Todos' },
  { value: 'pending', label: 'Pendiente' },
  { value: 'running', label: 'En ejecución' },
  { value: 'completed', label: 'Completado' },
  { value: 'reconciled', label: 'Reconciliado' },
  { value: 'failed', label: 'Fallido' },
]

// ─────────────────────────────────────────────────────────────────
// Nueva corrida — modal
// ─────────────────────────────────────────────────────────────────

function NuevaCorridaModal({ open, onClose }) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const now = new Date()

  const [form, setForm] = useState({
    name: `Cierre ${MONTHS[now.getMonth()]} ${now.getFullYear()}`,
    period_year: now.getFullYear(),
    period_month: now.getMonth() + 1,
    bank_account: 'Banregio',
    acquirers: [...ACQUIRERS],
  })

  const mutation = useMutation({
    mutationFn: () => processApi.create(form),
    onSuccess: ({ data }) => {
      qc.invalidateQueries({ queryKey: ['processes'] })
      onClose()
      navigate(`/processes/${data.id}`)
    },
  })

  function toggleAcquirer(a) {
    setForm(f => ({
      ...f,
      acquirers: f.acquirers.includes(a)
        ? f.acquirers.filter(x => x !== a)
        : [...f.acquirers, a],
    }))
  }

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-stone-900/30 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-stone-100">
          <div>
            <h2 className="text-[17px] font-semibold text-stone-900">Nueva corrida contable</h2>
            <p className="text-[13px] text-stone-500 mt-0.5">
              Configura el periodo y parámetros del cierre mensual
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-stone-400 hover:text-stone-700 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-5 space-y-5">
          {/* Name */}
          <div>
            <label className="t-label">Nombre de la corrida</label>
            <input
              className="t-input"
              value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              placeholder="Ej: Cierre Enero 2026"
            />
          </div>

          {/* Period */}
          <div>
            <label className="t-label flex items-center gap-1.5">
              <Calendar size={13} /> Periodo contable
            </label>
            <div className="grid grid-cols-2 gap-3">
              <select
                className="t-input"
                value={form.period_year}
                onChange={e => setForm(f => ({ ...f, period_year: parseInt(e.target.value) }))}
              >
                {[2024, 2025, 2026].map(y => <option key={y} value={y}>{y}</option>)}
              </select>
              <select
                className="t-input"
                value={form.period_month}
                onChange={e => setForm(f => ({ ...f, period_month: parseInt(e.target.value) }))}
              >
                {MONTHS.map((m, i) => <option key={i + 1} value={i + 1}>{m}</option>)}
              </select>
            </div>
          </div>

          {/* Bank */}
          <div>
            <label className="t-label">Cuenta bancaria</label>
            <select
              className="t-input"
              value={form.bank_account}
              onChange={e => setForm(f => ({ ...f, bank_account: e.target.value }))}
            >
              {BANK_ACCOUNTS.map(b => <option key={b} value={b}>{b}</option>)}
            </select>
            <p className="text-[11px] text-stone-400 mt-1.5">
              Fuente de verdad financiera contra la cual se concilian los adquirentes
            </p>
          </div>

          {/* Acquirers */}
          <div>
            <label className="t-label flex items-center gap-1.5">
              <Cpu size={13} /> Adquirentes
            </label>
            <div className="flex flex-wrap gap-2">
              {ACQUIRERS.map(a => {
                const active = form.acquirers.includes(a)
                const colors = ACQ_COLORS[a]
                return (
                  <button
                    key={a}
                    type="button"
                    onClick={() => toggleAcquirer(a)}
                    className={clsx(
                      'px-3 py-1.5 rounded-lg text-[13px] font-medium transition-all border',
                      active
                        ? `${colors.bg} ${colors.border} ${colors.text}`
                        : 'bg-white border-stone-200 text-stone-400 hover:border-stone-300'
                    )}
                  >
                    {a}
                  </button>
                )
              })}
            </div>
            <p className="text-[11px] text-stone-400 mt-1.5">
              {form.acquirers.length} de {ACQUIRERS.length} seleccionados
            </p>
          </div>

          {mutation.error && (
            <div className="text-[13px] text-red-700 bg-red-50 rounded-lg px-3 py-2 border border-red-100">
              {mutation.error.response?.data?.detail || 'Error al crear la corrida'}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 px-6 py-4 border-t border-stone-100 bg-stone-50/50 rounded-b-2xl">
          <button onClick={onClose} className="btn-secondary">Cancelar</button>
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || !form.name || form.acquirers.length === 0}
            className="btn-primary flex items-center gap-2"
          >
            {mutation.isPending
              ? <><Loader2 size={13} className="animate-spin" /> Creando...</>
              : <>Crear y continuar <ChevronRight size={13} /></>
            }
          </button>
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────
// Contabilidad — main page
// ─────────────────────────────────────────────────────────────────

export default function Contabilidad() {
  const qc = useQueryClient()
  const [showNew, setShowNew] = useState(false)
  const [confirmId, setConfirmId] = useState(null)
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [yearFilter, setYearFilter] = useState('all')

  const { data: processes = [], isLoading } = useQuery({
    queryKey: ['processes'],
    queryFn: () => processApi.list().then(r => r.data),
    refetchInterval: 8_000,
  })

  const deleteMutation = useMutation({
    mutationFn: (id) => processApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['processes'] })
      setConfirmId(null)
    },
  })

  const filtered = useMemo(() => {
    return processes.filter(p => {
      if (statusFilter !== 'all' && p.status !== statusFilter) return false
      if (yearFilter !== 'all' && p.period_year !== parseInt(yearFilter)) return false
      if (query) {
        const q = query.toLowerCase()
        const hay = `${p.name} ${p.bank_account || ''} ${p.period_year}-${p.period_month}`.toLowerCase()
        if (!hay.includes(q)) return false
      }
      return true
    })
  }, [processes, statusFilter, yearFilter, query])

  const years = useMemo(() => {
    const s = new Set(processes.map(p => p.period_year).filter(Boolean))
    return ['all', ...Array.from(s).sort((a, b) => b - a)]
  }, [processes])

  // KPIs
  const stats = useMemo(() => {
    const total = processes.length
    const reconciled = processes.filter(p => p.status === 'reconciled').length
    const completed = processes.filter(p => ['completed', 'reconciled'].includes(p.status)).length
    const running = processes.filter(p => p.status === 'running').length
    return { total, reconciled, completed, running }
  }, [processes])

  return (
    <div className="px-8 py-6" style={{ maxWidth: 1420 }}>
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-semibold text-stone-900">Contabilidad</h1>
          <p className="text-sm text-stone-500 mt-0.5">
            {stats.total} {stats.total === 1 ? 'corrida' : 'corridas'}
            {stats.reconciled > 0 && (
              <> · <span className="text-emerald-700 font-medium">{stats.reconciled} reconciliada{stats.reconciled !== 1 ? 's' : ''}</span></>
            )}
            {stats.running > 0 && (
              <> · <span className="text-blue-700 font-medium">{stats.running} en ejecución</span></>
            )}
          </p>
        </div>
        <button
          onClick={() => setShowNew(true)}
          className="btn-primary flex items-center gap-2"
        >
          <Plus size={14} /> Nueva corrida
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-x-2 gap-y-2 mb-4">
        <div className="relative flex-1 min-w-[220px] max-w-sm">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400 pointer-events-none" />
          <input
            type="text"
            placeholder="Buscar por nombre o periodo..."
            value={query}
            onChange={e => setQuery(e.target.value)}
            className="t-input pl-10"
          />
        </div>
        <select
          value={yearFilter}
          onChange={e => setYearFilter(e.target.value)}
          className="t-input"
          style={{ width: 'auto', minWidth: 170, paddingRight: 36 }}
        >
          {years.map(y => (
            <option key={y} value={y}>{y === 'all' ? 'Todos los años' : y}</option>
          ))}
        </select>
        <div className="flex items-center gap-0.5 bg-stone-100 rounded-xl p-1 overflow-x-auto flex-shrink-0" style={{ height: 42 }}>
          {STATUS_FILTERS.map(f => (
            <button
              key={f.value}
              onClick={() => setStatusFilter(f.value)}
              className={clsx(
                'px-3 h-full rounded-lg text-[13px] font-medium transition-all whitespace-nowrap',
                statusFilter === f.value
                  ? 'bg-white text-stone-900 shadow-sm'
                  : 'text-stone-500 hover:text-stone-700'
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="t-card p-0 overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={18} className="animate-spin text-stone-300" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-16">
            {processes.length === 0 ? (
              <>
                <p className="text-sm text-stone-500 mb-3">No hay corridas registradas</p>
                <button
                  onClick={() => setShowNew(true)}
                  className="btn-primary inline-flex items-center gap-2 text-sm"
                >
                  <Plus size={14} /> Crear primera corrida
                </button>
              </>
            ) : (
              <p className="text-sm text-stone-400">Sin resultados para los filtros seleccionados</p>
            )}
          </div>
        ) : (
          <table className="t-table">
            <thead>
              <tr>
                <th>Periodo</th>
                <th>Nombre</th>
                <th>Cuenta</th>
                <th>Adquirentes</th>
                <th>Estado</th>
                <th>Cobertura Banregio</th>
                <th>Fecha</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(p => (
                <tr
                  key={p.id}
                  className="cursor-pointer"
                  onClick={() => window.location.assign(`/processes/${p.id}/results`)}
                >
                  <td className="font-medium text-stone-900 whitespace-nowrap">
                    {p.period_year}-{String(p.period_month).padStart(2, '0')}
                  </td>
                  <td className="text-stone-600">{p.name}</td>
                  <td>
                    <span className="t-badge t-badge-blue">{p.bank_account || 'Banregio'}</span>
                  </td>
                  <td>
                    <div className="flex flex-wrap gap-1">
                      {(p.acquirers || []).slice(0, 3).map(a => (
                        <span key={a} className="t-badge t-badge-gray text-[10px]">{a}</span>
                      ))}
                      {(p.acquirers || []).length > 3 && (
                        <span className="text-[10px] text-stone-400">+{p.acquirers.length - 3}</span>
                      )}
                    </div>
                  </td>
                  <td><StatusBadge status={p.status} /></td>
                  <td>
                    {p.coverage_pct != null ? (
                      <div className="w-24">
                        <div className="progress-track">
                          <div
                            className="progress-fill"
                            style={{
                              width: `${p.coverage_pct}%`,
                              background: p.coverage_pct >= 100 ? '#047857'
                                : p.coverage_pct >= 50 ? '#2F1503' : '#ef4444',
                            }}
                          />
                        </div>
                        <span className="text-[11px] text-stone-400 mt-0.5">{p.coverage_pct}%</span>
                      </div>
                    ) : (
                      <span className="text-[11px] text-stone-400">—</span>
                    )}
                  </td>
                  <td className="text-stone-400 text-[13px] whitespace-nowrap">
                    {format(new Date(p.created_at), 'dd MMM, HH:mm', { locale: es })}
                  </td>
                  <td onClick={e => e.stopPropagation()}>
                    <div className="flex items-center gap-2">
                      <Link
                        to={`/processes/${p.id}/results`}
                        className="text-[13px] text-stone-700 hover:text-stone-900 font-medium flex items-center gap-1"
                      >
                        Abrir <ArrowRight size={11} />
                      </Link>
                      {p.status !== 'running' && (
                        confirmId === p.id ? (
                          <div className="flex items-center gap-1.5 ml-2">
                            <button
                              onClick={() => deleteMutation.mutate(p.id)}
                              disabled={deleteMutation.isPending}
                              className="text-[11px] text-red-600 hover:text-red-700 font-medium"
                            >
                              {deleteMutation.isPending
                                ? <Loader2 size={11} className="animate-spin" />
                                : 'Confirmar'}
                            </button>
                            <button
                              onClick={() => setConfirmId(null)}
                              className="text-[11px] text-stone-400 hover:text-stone-600"
                            >
                              ×
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => setConfirmId(p.id)}
                            className="text-stone-300 hover:text-red-500 transition-colors"
                            title="Eliminar corrida"
                          >
                            <Trash2 size={13} />
                          </button>
                        )
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <NuevaCorridaModal open={showNew} onClose={() => setShowNew(false)} />
    </div>
  )
}
