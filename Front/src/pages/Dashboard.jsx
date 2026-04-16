import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { processApi } from '../api/client'
import {
  Plus, ArrowRight, Calendar, Loader2, TrendingUp,
  CheckCircle2, AlertTriangle, Clock,
} from 'lucide-react'
import StatusBadge from '../components/ui/StatusBadge'
import { format } from 'date-fns'
import { es } from 'date-fns/locale'
import { useAuth } from '../hooks/useAuth'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell,
} from 'recharts'

const MONTH_NAMES = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
const PIE_COLORS = ['#047857', '#1c1917', '#f59e0b', '#ef4444', '#d1d5db']

function KpiCard({ label, value, icon: Icon, color, sub, delay = '' }) {
  return (
    <div className={`t-card fade-in ${delay}`}>
      <div className="flex items-center gap-3">
        <div
          className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0"
          style={{ background: color + '12' }}
        >
          <Icon size={18} style={{ color }} strokeWidth={1.75} />
        </div>
        <div>
          <p className="kpi-label">{label}</p>
          <p className="kpi-value mt-0.5">{value}</p>
        </div>
      </div>
      {sub && <p className="text-xs text-stone-400 mt-3">{sub}</p>}
    </div>
  )
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-white border border-stone-200 rounded-lg px-3 py-2 text-xs shadow-lg">
      <p className="font-medium text-stone-900 mb-1">{label}</p>
      {payload.map(p => (
        <p key={p.dataKey} style={{ color: p.color }}>
          {p.name}: {p.value}
        </p>
      ))}
    </div>
  )
}

export default function Dashboard() {
  const { user } = useAuth()
  const { data: processes = [], isLoading } = useQuery({
    queryKey: ['processes'],
    queryFn: () => processApi.list().then(r => r.data),
    refetchInterval: 10_000,
  })

  const stats = {
    total: processes.length,
    completed: processes.filter(p => p.status === 'completed' || p.status === 'reconciled').length,
    reconciled: processes.filter(p => p.status === 'reconciled').length,
    running: processes.filter(p => p.status === 'running').length,
    failed: processes.filter(p => p.status === 'failed').length,
    pending: processes.filter(p => p.status === 'pending').length,
  }

  const chartData = MONTH_NAMES.map((month, i) => ({
    month,
    Corridas: processes.filter(p => new Date(p.created_at).getMonth() === i).length,
  })).slice(0, Math.max(new Date().getMonth() + 1, 1))

  const pieData = [
    { name: 'Reconciliado', value: stats.reconciled },
    { name: 'Completado', value: stats.completed - stats.reconciled },
    { name: 'En ejecucion', value: stats.running },
    { name: 'Fallido', value: stats.failed },
    { name: 'Pendiente', value: stats.pending },
  ].filter(d => d.value > 0)

  const recent = processes.slice(0, 6)
  const now = new Date()
  const greeting = now.getHours() < 12 ? 'Buenos dias' : now.getHours() < 18 ? 'Buenas tardes' : 'Buenas noches'

  return (
    <div className="px-8 py-6" style={{ maxWidth: 1420 }}>

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <p className="text-sm text-stone-500">
            {greeting}, <span className="font-medium text-stone-900">{user?.full_name?.split(' ')[0]}</span>
          </p>
          <h1 className="text-[15px] font-semibold text-stone-900 mt-0.5">
            Overview
            <span className="text-stone-300 mx-2">|</span>
            <span className="text-[13px] font-normal text-stone-400">
              {format(now, "EEEE, d 'de' MMMM yyyy", { locale: es })}
            </span>
          </h1>
        </div>
        <Link to="/processes/new" className="btn-primary flex items-center gap-2">
          <Plus size={14} />
          Nueva corrida
        </Link>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <KpiCard label="Total Corridas" value={stats.total} icon={Clock} color="#78716c"
          sub={stats.total > 0 ? 'Periodo activo' : 'Sin corridas aun'} delay="d1" />
        <KpiCard label="Completadas" value={stats.completed} icon={CheckCircle2} color="#2563eb"
          sub={stats.total > 0 ? `${Math.round(stats.completed / stats.total * 100)}% del total` : ''} delay="d2" />
        <KpiCard label="Reconciliadas" value={stats.reconciled} icon={TrendingUp} color="#047857"
          sub={stats.total > 0 ? `${Math.round(stats.reconciled / stats.total * 100)}% del total` : ''} delay="d3" />
        <KpiCard label="Con Alertas" value={stats.failed} icon={AlertTriangle} color="#ef4444"
          sub={stats.failed > 0 ? 'Requieren revision' : 'Sin errores'} delay="d4" />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        {/* Area chart */}
        <div className="t-card col-span-2 fade-in d3">
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-sm font-semibold text-stone-900">Actividad Mensual</p>
              <p className="text-xs text-stone-400 mt-0.5">Corridas ejecutadas por mes</p>
            </div>
          </div>
          {chartData.some(d => d.Corridas > 0) ? (
            <ResponsiveContainer width="100%" height={180}>
              <AreaChart data={chartData} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="gBlue" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#1c1917" stopOpacity={0.15} />
                    <stop offset="95%" stopColor="#1c1917" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="month" tick={{ fill: '#a8a29e', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#a8a29e', fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
                <Tooltip content={<ChartTooltip />} />
                <Area type="monotone" dataKey="Corridas" stroke="#1c1917" strokeWidth={2}
                  fill="url(#gBlue)" dot={{ fill: '#1c1917', r: 3, strokeWidth: 0 }} />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex flex-col items-center justify-center h-[180px] text-stone-300">
              <TrendingUp size={24} className="mb-2" />
              <p className="text-sm">Sin actividad aun</p>
            </div>
          )}
        </div>

        {/* Donut chart */}
        <div className="t-card fade-in d4">
          <p className="text-sm font-semibold text-stone-900">Estado de Corridas</p>
          <p className="text-xs text-stone-400 mt-0.5 mb-4">Distribucion por status</p>
          {pieData.length > 0 ? (
            <div className="flex flex-col items-center">
              <ResponsiveContainer width="100%" height={140}>
                <PieChart>
                  <Pie data={pieData} cx="50%" cy="50%" innerRadius={40} outerRadius={60}
                    paddingAngle={2} dataKey="value" stroke="none">
                    {pieData.map((_, i) => (
                      <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
              <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
                {pieData.map((d, i) => (
                  <div key={d.name} className="flex items-center gap-1.5 text-xs text-stone-500">
                    <div className="status-dot" style={{ background: PIE_COLORS[i] }} />
                    {d.name} ({d.value})
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-[140px] text-stone-300">
              <p className="text-sm">Sin datos</p>
            </div>
          )}
        </div>
      </div>

      {/* Recent runs */}
      <div className="t-card p-0 overflow-hidden fade-in d5">
        <div className="flex items-center justify-between px-6 py-4 border-b border-stone-100">
          <div>
            <p className="text-sm font-semibold text-stone-900">Corridas Recientes</p>
            <p className="text-xs text-stone-400 mt-0.5">Ultimas corridas de conciliacion</p>
          </div>
          <Link to="/processes" className="text-[13px] text-stone-700 hover:text-blue-700 flex items-center gap-1 font-medium">
            Ver todas <ArrowRight size={13} />
          </Link>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={18} className="animate-spin text-stone-300" />
          </div>
        ) : recent.length === 0 ? (
          <div className="text-center py-16">
            <p className="text-sm text-stone-400 mb-3">Sin corridas registradas</p>
            <Link to="/processes/new" className="btn-primary inline-flex items-center gap-2 text-sm">
              <Plus size={14} /> Crear primera corrida
            </Link>
          </div>
        ) : (
          <table className="t-table">
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Cuenta</th>
                <th>Periodo</th>
                <th>Estado</th>
                <th>Reconciliacion</th>
                <th>Cobertura</th>
                <th>Creado</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {recent.map(p => (
                <tr key={p.id}>
                  <td className="font-medium text-stone-900">{p.name}</td>
                  <td><span className="t-badge t-badge-blue">{p.bank_account || 'Banregio'}</span></td>
                  <td className="text-stone-500">
                    {p.period_year}-{String(p.period_month).padStart(2, '0')}
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
                                : p.coverage_pct >= 50 ? '#1c1917' : '#ef4444',
                            }}
                          />
                        </div>
                        <span className="text-[11px] text-stone-400 mt-0.5">{p.coverage_pct}%</span>
                      </div>
                    ) : (
                      <span className="text-[11px] text-stone-400">—</span>
                    )}
                  </td>
                  <td className="text-stone-500">
                    {p.coverage_pct != null ? `${p.coverage_pct}%` : '—'}
                  </td>
                  <td className="text-stone-400 text-[13px]">
                    {format(new Date(p.created_at), 'dd MMM, HH:mm', { locale: es })}
                  </td>
                  <td>
                    <Link to={`/processes/${p.id}`}
                      className="text-[13px] text-stone-700 hover:text-blue-700 font-medium">
                      Abrir <ArrowRight size={11} className="inline" />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
