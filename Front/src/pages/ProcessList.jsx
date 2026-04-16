import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { processApi } from '../api/client'
import {
  Card, Title, Text,
  Table, TableHead, TableHeaderCell, TableBody, TableRow, TableCell,
  Badge, ProgressBar,
} from '@tremor/react'
import { Plus, Loader2, Trash2 } from 'lucide-react'
import StatusBadge from '../components/ui/StatusBadge'
import { format } from 'date-fns'
import { es } from 'date-fns/locale'

export default function ProcessList() {
  const qc = useQueryClient()
  const [confirmId, setConfirmId] = useState(null)

  const { data: processes = [], isLoading } = useQuery({
    queryKey: ['processes'],
    queryFn: () => processApi.list().then(r => r.data),
    refetchInterval: 8_000,
  })

  const deleteMutation = useMutation({
    mutationFn: (id) => processApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries(['processes'])
      setConfirmId(null)
    },
  })

  return (
    <div className="p-6 lg:p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Proceso Contable</h1>
          <p className="text-gray-500 text-sm mt-1">Historial de corridas de cierre mensual</p>
        </div>
        <Link to="/processes/new" className="btn-primary flex items-center gap-2">
          <Plus size={16} />
          Nueva corrida
        </Link>
      </div>

      <Card className="p-0 overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={20} className="animate-spin text-gray-400" />
          </div>
        ) : processes.length === 0 ? (
          <div className="text-center py-16">
            <p className="text-gray-500 mb-3">No hay corridas registradas.</p>
            <Link to="/processes/new" className="btn-primary text-sm inline-flex items-center gap-2">
              <Plus size={14} /> Crear corrida
            </Link>
          </div>
        ) : (
          <Table>
            <TableHead>
              <TableRow>
                <TableHeaderCell>ID</TableHeaderCell>
                <TableHeaderCell>Nombre</TableHeaderCell>
                <TableHeaderCell>Cuenta</TableHeaderCell>
                <TableHeaderCell>Periodo</TableHeaderCell>
                <TableHeaderCell>Adquirentes</TableHeaderCell>
                <TableHeaderCell>Estado</TableHeaderCell>
                <TableHeaderCell>Reconciliacion</TableHeaderCell>
                <TableHeaderCell>Creado</TableHeaderCell>
                <TableHeaderCell></TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {processes.map(p => (
                <TableRow key={p.id}>
                  <TableCell className="text-gray-500">#{p.id}</TableCell>
                  <TableCell>
                    <span className="font-medium text-gray-900">{p.name}</span>
                  </TableCell>
                  <TableCell>
                    <Badge color="blue" size="xs">{p.bank_account || 'Banregio'}</Badge>
                  </TableCell>
                  <TableCell className="text-gray-600">
                    {p.period_year}-{String(p.period_month).padStart(2, '0')}
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {(p.acquirers || []).map(a => (
                        <Badge key={a} color="gray" size="xs">{a}</Badge>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell><StatusBadge status={p.status} /></TableCell>
                  <TableCell>
                    {p.coverage_pct != null ? (
                      <div className="w-28">
                        <ProgressBar
                          value={p.coverage_pct}
                          color={p.coverage_pct >= 100 ? 'emerald' : p.coverage_pct >= 50 ? 'blue' : 'red'}
                        />
                        <span className="text-xs text-gray-500">{p.coverage_pct}%</span>
                      </div>
                    ) : (
                      <span className="text-xs text-gray-400">
                        {p.status === 'completed' || p.status === 'reconciled' ? '0%' : '—'}
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="text-gray-500 text-sm">
                    {format(new Date(p.created_at), 'dd/MM/yyyy HH:mm', { locale: es })}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-3">
                      <Link to={`/processes/${p.id}`} className="text-blue-600 hover:text-blue-700 text-sm font-medium">
                        Abrir
                      </Link>
                      {p.status !== 'running' && (
                        confirmId === p.id ? (
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => deleteMutation.mutate(p.id)}
                              disabled={deleteMutation.isPending}
                              className="text-xs text-red-600 hover:text-red-700 font-medium"
                            >
                              {deleteMutation.isPending ? <Loader2 size={12} className="animate-spin" /> : 'Confirmar'}
                            </button>
                            <button
                              onClick={() => setConfirmId(null)}
                              className="text-xs text-gray-500 hover:text-gray-700"
                            >
                              Cancelar
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => setConfirmId(p.id)}
                            className="text-gray-400 hover:text-red-500 transition-colors"
                          >
                            <Trash2 size={14} />
                          </button>
                        )
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>
    </div>
  )
}
