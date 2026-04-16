import React, { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { resultsApi, processApi } from '../api/client'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, Legend,
} from 'recharts'
import { ChevronRight, Loader2, CheckCircle2, XCircle, AlertTriangle, Download } from 'lucide-react'
import clsx from 'clsx'

const TABS = ['Comisiones', 'Kushki', 'Banregio', 'Conciliaciones']
const EXPORT_CONFIG = [
  { label: 'Exportar Comisiones', fn: resultsApi.exportFees },
  { label: 'Exportar Kushki', fn: resultsApi.exportKushki },
  { label: 'Exportar Banregio', fn: resultsApi.exportBanregio },
  null,
]

function filenameFromDisposition(disposition, fallback) {
  if (!disposition) return fallback
  const m = disposition.match(/filename\*?=(?:UTF-8''|\"?)([^\";]+)/i)
  if (!m || !m[1]) return fallback
  try {
    return decodeURIComponent(m[1].replace(/"/g, '').trim())
  } catch {
    return m[1].replace(/"/g, '').trim()
  }
}

function FmtMoney({ value }) {
  return (
    <span className="font-mono">
      ${Number(value || 0).toLocaleString('es-MX', { minimumFractionDigits: 2 })}
    </span>
  )
}

function FeesTab({ processId }) {
  const { data, isLoading } = useQuery({
    queryKey: ['fees', processId],
    queryFn: () => resultsApi.fees(processId).then(r => r.data),
  })

  if (isLoading) return <Loader2 size={20} className="animate-spin text-gray-400 mx-auto mt-8" />
  if (!data) return <p className="text-gray-400 text-sm text-center mt-8">Sin resultados de comisiones aún</p>

  const chartData = (data.merchant_summary || []).slice(0, 10).map(m => ({
    name: (m.merchant_name || m.merchant_id || '').slice(0, 14),
    fee: parseFloat(m.total_fee || 0),
    txs: m.tx_count,
  }))

  return (
    <div className="space-y-6">
      {/* KPIs */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Total Comisiones', value: data.total_fees },
          { label: 'Comercios', value: data.merchant_summary?.length || 0, isMoney: false },
          { label: 'Registros diarios', value: data.daily_breakdown?.length || 0, isMoney: false },
        ].map(k => (
          <div key={k.label} className="card text-center">
            <p className="text-2xl font-bold text-gray-900">
              {k.isMoney === false ? k.value : <FmtMoney value={k.value} />}
            </p>
            <p className="text-sm text-gray-500 mt-1">{k.label}</p>
          </div>
        ))}
      </div>

      {/* Chart */}
      {chartData.length > 0 && (
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-900 mb-4">Top 10 comercios por comision</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={chartData} margin={{ top: 0, right: 0, left: 10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
              <XAxis dataKey="name" tick={{ fill: '#64748b', fontSize: 11 }} />
              <YAxis tick={{ fill: '#64748b', fontSize: 11 }} />
              <Tooltip
                contentStyle={{ background: '#ffffff', border: '1px solid #e5e7eb', borderRadius: 8 }}
                labelStyle={{ color: '#111827' }}
              />
              <Bar dataKey="fee" fill="#6366f1" radius={[4, 4, 0, 0]} name="Fee" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Merchant table */}
      <div className="card p-0 overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-200">
          <h3 className="text-sm font-semibold text-gray-900">Resumen por comercio</h3>
        </div>
        <table className="w-full text-sm">
          <thead className="border-b border-gray-200 bg-gray-50">
            <tr>
              {['Comercio', 'Transacciones', 'Monto bruto', 'Comision total'].map(h => (
                <th key={h} className="text-left px-5 py-3 text-gray-500 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(data.merchant_summary || []).map((m, i) => (
              <tr key={i} className="border-b border-gray-200/50 hover:bg-blue-50/50">
                <td className="px-5 py-2.5 text-gray-900">{m.merchant_name || m.merchant_id}</td>
                <td className="px-5 py-2.5 text-gray-500">{m.tx_count?.toLocaleString()}</td>
                <td className="px-5 py-2.5 text-gray-700"><FmtMoney value={m.gross_amount} /></td>
                <td className="px-5 py-2.5 text-blue-600 font-medium"><FmtMoney value={m.total_fee} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function KushkiTab({ processId }) {
  const { data, isLoading } = useQuery({
    queryKey: ['kushki', processId],
    queryFn: () => resultsApi.kushki(processId).then(r => r.data),
  })

  if (isLoading) return <Loader2 size={20} className="animate-spin text-gray-400 mx-auto mt-8" />
  if (!data) return <p className="text-gray-400 text-sm text-center mt-8">Sin resultados Kushki</p>

  const chartData = (data.daily_summary || []).map(d => ({
    date: d.date,
    gross: parseFloat(d.gross_amount || 0),
    net: parseFloat(d.net_deposit || 0),
    commission: parseFloat(d.commission || 0),
  }))

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4">
        <div className="card text-center">
          <p className="text-2xl font-bold text-gray-900"><FmtMoney value={data.total_net_deposit} /></p>
          <p className="text-sm text-gray-500 mt-1">Net Deposit Total</p>
        </div>
        <div className="card text-center">
          <p className="text-2xl font-bold text-gray-900">{data.daily_summary?.length || 0}</p>
          <p className="text-sm text-gray-500 mt-1">Días procesados</p>
        </div>
      </div>

      {chartData.length > 0 && (
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-900 mb-4">Depósito neto diario</h3>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
              <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 10 }} />
              <YAxis tick={{ fill: '#64748b', fontSize: 11 }} />
              <Tooltip contentStyle={{ background: '#ffffff', border: '1px solid #e5e7eb', borderRadius: 8 }} />
              <Legend />
              <Line type="monotone" dataKey="gross" stroke="#6366f1" dot={false} name="Bruto" />
              <Line type="monotone" dataKey="net" stroke="#10b981" dot={false} name="Neto" />
              <Line type="monotone" dataKey="commission" stroke="#f59e0b" dot={false} name="Comisión" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="card p-0 overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-200">
          <h3 className="text-sm font-semibold text-gray-900">Resumen diario</h3>
        </div>
        <table className="w-full text-sm">
          <thead className="border-b border-gray-200 bg-gray-50">
            <tr>
              {['Fecha', 'Txs', 'Bruto', 'Comisión', 'Rolling Reserve', 'Depósito neto'].map(h => (
                <th key={h} className="text-left px-4 py-3 text-gray-500 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(data.daily_summary || []).map((d, i) => (
              <tr key={i} className="border-b border-gray-200/50 hover:bg-blue-50/50">
                <td className="px-4 py-2.5 text-gray-700">{d.date}</td>
                <td className="px-4 py-2.5 text-gray-500">{Number(d.tx_count || 0).toLocaleString()}</td>
                <td className="px-4 py-2.5 text-gray-700"><FmtMoney value={d.gross_amount} /></td>
                <td className="px-4 py-2.5 text-amber-600"><FmtMoney value={d.commission} /></td>
                <td className="px-4 py-2.5 text-gray-500"><FmtMoney value={d.rolling_reserve} /></td>
                <td className="px-4 py-2.5 text-emerald-600 font-medium"><FmtMoney value={d.net_deposit} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function BanregioTab({ processId }) {
  const { data, isLoading } = useQuery({
    queryKey: ['banregio', processId],
    queryFn: () => resultsApi.banregio(processId).then(r => r.data),
  })

  if (isLoading) return <Loader2 size={20} className="animate-spin text-gray-400 mx-auto mt-8" />
  if (!data) return <p className="text-gray-400 text-sm text-center mt-8">Sin resultados Banregio</p>

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Total abonos', value: data.summary?.total_credits, money: true },
          { label: 'Total cargos', value: data.summary?.total_debits, money: true },
          { label: 'Movimientos', value: data.movements?.length || 0, money: false },
        ].map(k => (
          <div key={k.label} className="card text-center">
            <p className="text-2xl font-bold text-gray-900">
              {k.money ? <FmtMoney value={k.value} /> : k.value}
            </p>
            <p className="text-sm text-gray-500 mt-1">{k.label}</p>
          </div>
        ))}
      </div>

      <div className="card p-0 overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-200">
          <h3 className="text-sm font-semibold text-gray-900">Movimientos</h3>
        </div>
        <div className="max-h-96 overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-gray-200 bg-gray-50 sticky top-0">
              <tr>
                {['Fecha', 'Descripción', 'Cargo', 'Abono', 'Ref depósito'].map(h => (
                  <th key={h} className="text-left px-4 py-3 text-gray-500 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(data.movements || []).map((m, i) => (
                <tr key={i} className="border-b border-gray-200/50 hover:bg-blue-50/50">
                  <td className="px-4 py-2.5 text-gray-500 text-xs">{m.date}</td>
                  <td className="px-4 py-2.5 text-gray-700 max-w-xs truncate">{m.description}</td>
                  <td className="px-4 py-2.5 text-red-600"><FmtMoney value={m.debit} /></td>
                  <td className="px-4 py-2.5 text-emerald-600"><FmtMoney value={m.credit} /></td>
                  <td className="px-4 py-2.5 text-gray-500"><FmtMoney value={m.deposit_ref} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function ConciliationTab({ processId }) {
  const { data = [], isLoading } = useQuery({
    queryKey: ['conciliation', processId],
    queryFn: () => resultsApi.conciliation(processId).then(r => r.data),
  })

  if (isLoading) return <Loader2 size={20} className="animate-spin text-gray-400 mx-auto mt-8" />
  if (!data.length) return <p className="text-gray-400 text-sm text-center mt-8">Sin conciliaciones aún</p>

  const TYPE_LABEL = {
    fees: 'Comisiones',
    kushki_daily: 'Kushki Diario',
    kushki_vs_banregio: 'Kushki vs Banregio',
  }

  return (
    <div className="space-y-6">
      {data.map(c => (
        <div key={c.id} className="card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-base font-semibold text-gray-900">{TYPE_LABEL[c.conciliation_type] || c.conciliation_type}</h3>
            <div className="flex items-center gap-3 text-sm">
              <span className="flex items-center gap-1 text-emerald-600">
                <CheckCircle2 size={14} />
                Conciliado: <FmtMoney value={c.total_conciliated} />
              </span>
              {c.total_difference > 0 && (
                <span className="flex items-center gap-1 text-amber-600">
                  <AlertTriangle size={14} />
                  Diferencia: <FmtMoney value={c.total_difference} />
                </span>
              )}
            </div>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-4 gap-3 mb-4">
            {[
              { label: 'Conciliados', value: c.matched?.length || 0, color: 'text-emerald-600' },
              { label: 'Diferencias', value: c.differences?.length || 0, color: 'text-amber-600' },
              { label: 'Sin match Kushki', value: c.unmatched_kushki?.length || 0, color: 'text-red-600' },
              { label: 'Sin match Banregio', value: c.unmatched_banregio?.length || 0, color: 'text-red-600' },
            ].map(s => (
              <div key={s.label} className="bg-gray-50 rounded-lg p-3 text-center">
                <p className={`text-xl font-bold ${s.color}`}>{s.value}</p>
                <p className="text-xs text-gray-400 mt-0.5">{s.label}</p>
              </div>
            ))}
          </div>

          {/* Matched rows (Kushki vs Banregio) */}
          {c.conciliation_type === 'kushki_vs_banregio' && c.matched?.length > 0 && (
            <div className="overflow-auto max-h-64">
              <table className="w-full text-xs">
                <thead className="border-b border-gray-200">
                  <tr>
                    {['Fecha', 'Kushki (Col I)', 'Banregio (Col H)', 'Diferencia'].map(h => (
                      <th key={h} className="text-left px-3 py-2 text-gray-500">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {c.matched.map((m, i) => (
                    <tr key={i} className="border-b border-gray-200/50">
                      <td className="px-3 py-2 text-gray-500">{m.date}</td>
                      <td className="px-3 py-2 text-gray-700"><FmtMoney value={m.kushki_amount} /></td>
                      <td className="px-3 py-2 text-gray-700"><FmtMoney value={m.banregio_amount} /></td>
                      <td className={`px-3 py-2 ${m.difference > 0 ? 'text-amber-600' : 'text-emerald-600'}`}>
                        <FmtMoney value={m.difference} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

export default function Results() {
  const { id } = useParams()
  const [tab, setTab] = useState(0)
  const [isExporting, setIsExporting] = useState(false)

  const { data: proc } = useQuery({
    queryKey: ['process', id],
    queryFn: () => processApi.get(id).then(r => r.data),
  })

  const exportConfig = EXPORT_CONFIG[tab]

  async function handleExport() {
    if (!exportConfig || isExporting) return
    try {
      setIsExporting(true)
      const response = await exportConfig.fn(id)
      const fallback = `${TABS[tab]}_${id}.xlsx`
      const filename = filenameFromDisposition(response.headers?.['content-disposition'], fallback)
      const url = window.URL.createObjectURL(new Blob([response.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch (err) {
      const msg = err?.response?.data?.detail || 'No se pudo exportar este resultado'
      window.alert(msg)
    } finally {
      setIsExporting(false)
    }
  }

  return (
    <div className="p-8 space-y-6">
      <div>
        <div className="flex items-center gap-2 text-gray-400 text-sm mb-1">
          <Link to="/processes" className="hover:text-gray-700">Proceso Contable</Link>
          <ChevronRight size={12} />
          <Link to={`/processes/${id}`} className="hover:text-gray-700">{proc?.name}</Link>
          <ChevronRight size={12} />
          <span className="text-gray-700">Resultados</span>
        </div>
        <h1 className="text-2xl font-bold text-gray-900">Resultados del cierre</h1>
        {proc && (
          <p className="text-gray-500 text-sm mt-0.5">
            {proc.period_year}-{String(proc.period_month).padStart(2, '0')} · {proc.name}
          </p>
        )}
      </div>

      {/* Tabs */}
      <div className="flex items-center justify-between border-b border-gray-200">
        <div className="flex">
          {TABS.map((t, i) => (
            <button
              key={t}
              onClick={() => setTab(i)}
              className={clsx(
                'px-5 py-3 text-sm font-medium border-b-2 transition-colors',
                tab === i
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-900'
              )}
            >
              {t}
            </button>
          ))}
        </div>
        {exportConfig && (
          <button
            onClick={handleExport}
            disabled={isExporting}
            className="btn-secondary mb-2 flex items-center gap-2"
          >
            {isExporting
              ? <><Loader2 size={14} className="animate-spin" /> Exportando...</>
              : <><Download size={14} /> {exportConfig.label}</>
            }
          </button>
        )}
      </div>

      {/* Tab content */}
      <div>
        {tab === 0 && <FeesTab processId={id} />}
        {tab === 1 && <KushkiTab processId={id} />}
        {tab === 2 && <BanregioTab processId={id} />}
        {tab === 3 && <ConciliationTab processId={id} />}
      </div>
    </div>
  )
}
