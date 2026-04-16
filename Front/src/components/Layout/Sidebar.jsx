import React from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, ListChecks, Plus, LogOut,
  ShieldCheck, SlidersHorizontal, Bot,
  AlertTriangle, Settings, ArrowLeftRight,
} from 'lucide-react'
import { useAuth } from '../../hooks/useAuth'
import clsx from 'clsx'

const SECTIONS = [
  {
    label: 'Reconciliacion',
    items: [
      { label: 'Overview', to: '/', icon: LayoutDashboard },
      { label: 'Corridas', to: '/processes', icon: ListChecks },
      { label: 'Nueva Corrida', to: '/processes/new', icon: Plus },
    ],
  },
  {
    label: 'Operaciones',
    items: [
      { label: 'Ajustes', to: '/processes', icon: SlidersHorizontal, badge: 'Pronto' },
      { label: 'Bitso', to: '/processes', icon: ArrowLeftRight, badge: 'Pronto' },
    ],
  },
  {
    label: 'Intelligence',
    items: [
      { label: 'Warren AI', to: '/processes', icon: Bot, badge: 'AI' },
      { label: 'Alertas', to: '/processes', icon: AlertTriangle, badge: 'Pronto' },
    ],
  },
]

function NavItem({ item }) {
  if (item.badge) {
    return (
      <div className="flex items-center gap-2.5 px-3 py-2 mx-2 rounded-md text-gray-400 cursor-default">
        <item.icon size={16} strokeWidth={1.75} />
        <span className="flex-1 text-[13.5px] font-medium">{item.label}</span>
        <span
          className={clsx(
            'text-[9px] font-bold tracking-wider px-1.5 py-0.5 rounded-full',
            item.badge === 'AI'
              ? 'bg-blue-50 text-blue-500'
              : 'bg-gray-100 text-gray-400'
          )}
        >
          {item.badge}
        </span>
      </div>
    )
  }

  return (
    <NavLink
      to={item.to}
      end
      className={({ isActive }) =>
        clsx(
          'flex items-center gap-2.5 px-3 py-2 mx-2 rounded-md transition-all duration-100',
          isActive
            ? 'bg-blue-50 text-blue-600'
            : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700'
        )
      }
    >
      <item.icon size={16} strokeWidth={1.75} />
      <span className="text-[13.5px] font-medium">{item.label}</span>
    </NavLink>
  )
}

export default function Sidebar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  return (
    <aside
      className="flex flex-col h-screen sticky top-0 bg-white border-r border-gray-200 z-20"
      style={{ width: 232, minWidth: 232 }}
    >
      {/* Logo */}
      <div className="px-4 py-4">
        <img
          src="/truebook-logo.svg"
          alt="TrueBook"
          className="h-7 opacity-90"
        />
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto pb-4">
        {SECTIONS.map((section, i) => (
          <div key={section.label}>
            {i > 0 && <div className="mx-3 my-1.5 border-t border-gray-100" />}
            <div className="px-5 pt-3 pb-1">
              <span className="text-[10px] font-semibold uppercase tracking-widest text-gray-400">
                {section.label}
              </span>
            </div>
            <div className="space-y-0.5">
              {section.items.map(item => (
                <NavItem key={item.label} item={item} />
              ))}
            </div>
          </div>
        ))}
      </nav>

      {/* Separator */}
      <div className="mx-3 border-t border-gray-100" />

      {/* Settings */}
      <div className="px-2 py-2">
        <NavLink
          to="/processes"
          className="flex items-center gap-2.5 px-3 py-2 mx-0 rounded-md text-gray-400 hover:bg-gray-50 hover:text-gray-600 transition-all"
        >
          <Settings size={16} strokeWidth={1.75} />
          <span className="text-[13.5px] font-medium">Configuracion</span>
        </NavLink>
      </div>

      {/* User */}
      <div className="px-3 py-3 border-t border-gray-100">
        <div className="flex items-center gap-2.5 px-1">
          <div
            className="w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-semibold text-white shrink-0"
            style={{ background: 'linear-gradient(135deg, #3b82f6, #4f46e5)' }}
          >
            {user?.full_name?.[0]?.toUpperCase() || 'U'}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[13px] font-medium text-gray-900 truncate">{user?.full_name}</p>
            <p className="text-[11px] text-gray-400 truncate capitalize">{user?.role}</p>
          </div>
          <button
            onClick={() => { logout(); navigate('/login') }}
            className="text-gray-300 hover:text-red-500 transition-colors p-1"
            title="Cerrar sesion"
          >
            <LogOut size={14} />
          </button>
        </div>
      </div>
    </aside>
  )
}
