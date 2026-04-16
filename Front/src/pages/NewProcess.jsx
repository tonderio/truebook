import React, { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { processApi } from '../api/client'
import { Card, Title, Text } from '@tremor/react'
import { Loader2, ChevronRight, Calendar, Cpu } from 'lucide-react'

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
  STP:     { bg: 'bg-purple-50', border: 'border-purple-200', text: 'text-purple-700' },
}

export default function NewProcess() {
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
      qc.invalidateQueries(['processes'])
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

  return (
    <div className="p-6 lg:p-8">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-gray-500 mb-1">
        <Link to="/processes" className="hover:text-gray-700">Proceso Contable</Link>
        <ChevronRight size={14} />
        <span className="text-gray-900">Nueva corrida</span>
      </div>
      <h1 className="text-2xl font-semibold text-gray-900">Nueva corrida contable</h1>
      <p className="text-sm text-gray-500 mt-1 mb-6">
        Configura el periodo y parametros del cierre mensual
      </p>

      <Card className="max-w-2xl space-y-6">
        {/* Name */}
        <div>
          <label className="label">Nombre de la corrida</label>
          <input
            className="input"
            value={form.name}
            onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
            placeholder="Ej: Cierre Enero 2026"
          />
        </div>

        {/* Period */}
        <div>
          <label className="label flex items-center gap-1.5">
            <Calendar size={14} /> Periodo contable
          </label>
          <div className="grid grid-cols-2 gap-3">
            <select
              className="input"
              value={form.period_year}
              onChange={e => setForm(f => ({ ...f, period_year: parseInt(e.target.value) }))}
            >
              {[2024, 2025, 2026].map(y => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
            <select
              className="input"
              value={form.period_month}
              onChange={e => setForm(f => ({ ...f, period_month: parseInt(e.target.value) }))}
            >
              {MONTHS.map((m, i) => (
                <option key={i + 1} value={i + 1}>{m}</option>
              ))}
            </select>
          </div>
          <p className="text-xs text-gray-400 mt-2">
            Ventana: 1 {MONTHS[form.period_month - 1]} 00:00 UTC-6 — {form.period_month === 2 ? 28 : 31} {MONTHS[form.period_month - 1]} 23:59 UTC-6
          </p>
        </div>

        {/* Bank account */}
        <div>
          <label className="t-label flex items-center gap-1.5">
            Cuenta bancaria a conciliar
          </label>
          <select
            className="t-input"
            value={form.bank_account}
            onChange={e => setForm(f => ({ ...f, bank_account: e.target.value }))}
          >
            {BANK_ACCOUNTS.map(b => (
              <option key={b} value={b}>{b}</option>
            ))}
          </select>
          <p className="text-xs text-gray-400 mt-2">
            Fuente de verdad financiera contra la cual se concilian los adquirentes
          </p>
        </div>

        {/* Acquirers */}
        <div>
          <label className="label flex items-center gap-1.5">
            <Cpu size={14} /> Adquirentes a procesar
          </label>
          <div className="flex flex-wrap gap-2 mt-1">
            {ACQUIRERS.map(a => {
              const active = form.acquirers.includes(a)
              const colors = ACQ_COLORS[a]
              return (
                <button
                  key={a}
                  type="button"
                  onClick={() => toggleAcquirer(a)}
                  className={`px-3.5 py-2 rounded-lg text-sm font-medium transition-all border ${
                    active
                      ? `${colors.bg} ${colors.border} ${colors.text}`
                      : 'bg-white border-gray-200 text-gray-400'
                  }`}
                >
                  {a}
                </button>
              )
            })}
          </div>
          <p className="text-xs text-gray-400 mt-2">
            {form.acquirers.length} de {ACQUIRERS.length} adquirentes seleccionados
          </p>
        </div>

        {mutation.error && (
          <div className="text-sm text-red-600 bg-red-50 rounded-lg px-4 py-3 border border-red-100">
            {mutation.error.response?.data?.detail || 'Error al crear la corrida'}
          </div>
        )}

        <div className="flex justify-end gap-3 pt-2">
          <button onClick={() => navigate(-1)} className="btn-secondary">
            Cancelar
          </button>
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || !form.name || form.acquirers.length === 0}
            className="btn-primary flex items-center gap-2"
          >
            {mutation.isPending
              ? <><Loader2 size={14} className="animate-spin" /> Creando...</>
              : <>Crear y continuar <ChevronRight size={14} /></>
            }
          </button>
        </div>
      </Card>
    </div>
  )
}
