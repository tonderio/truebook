import React from 'react'

const CONFIG = {
  completed:  { label: 'Completado',  cls: 't-badge t-badge-blue' },
  reconciled: { label: 'Reconciliado', cls: 't-badge t-badge-emerald' },
  running:    { label: 'Ejecutando',  cls: 't-badge t-badge-amber' },
  failed:     { label: 'Fallido',     cls: 't-badge t-badge-red' },
  pending:    { label: 'Pendiente',   cls: 't-badge t-badge-gray' },
  parsed:     { label: 'Parseado',    cls: 't-badge t-badge-emerald' },
  uploaded:   { label: 'Cargado',     cls: 't-badge t-badge-blue' },
  error:      { label: 'Error',       cls: 't-badge t-badge-red' },
  warning:    { label: 'Advertencia', cls: 't-badge t-badge-amber' },
  approved:   { label: 'Aprobado',    cls: 't-badge t-badge-emerald' },
  rejected:   { label: 'Rechazado',   cls: 't-badge t-badge-red' },
}

export default function StatusBadge({ status }) {
  const cfg = CONFIG[status] || { label: status, cls: 't-badge t-badge-gray' }
  return <span className={cfg.cls}>{cfg.label}</span>
}
