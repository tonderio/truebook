import React from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, ListChecks, Plus, LogOut,
  SlidersHorizontal, Bot, AlertTriangle,
  Settings, ArrowLeftRight, CreditCard,
} from 'lucide-react'
import { useAuth } from '../../hooks/useAuth'
import clsx from 'clsx'

const NAV = [
  { label: 'Overview', to: '/', icon: LayoutDashboard },
  { label: 'Corridas', to: '/processes', icon: ListChecks },
  { label: 'Nueva corrida', to: '/processes/new', icon: Plus },
  { type: 'divider' },
  { label: 'Ajustes', to: '/processes', icon: SlidersHorizontal, soon: true },
  { label: 'Bitso', to: '/processes', icon: ArrowLeftRight, soon: true },
  { type: 'divider' },
  { label: 'Warren AI', to: '/processes', icon: Bot, tag: 'AI' },
  { label: 'Alertas', to: '/processes', icon: AlertTriangle, soon: true },
]

export default function Sidebar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  return (
    <aside
      className="flex flex-col h-screen sticky top-0 bg-stone-50 border-r border-stone-200/60"
      style={{ width: 240, minWidth: 240 }}
    >
      {/* Icon only */}
      <div className="px-5 pt-5 pb-4">
        <img src="/truebook-icon.svg" alt="TrueBook" className="h-8" />
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto px-3 space-y-0.5">
        {NAV.map((item, i) => {
          if (item.type === 'divider') {
            return <div key={i} className="my-2 mx-2 border-t border-stone-100" />
          }

          if (item.soon) {
            return (
              <div key={item.label} className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-stone-300">
                <item.icon size={18} strokeWidth={1.5} />
                <span className="text-[14px]">{item.label}</span>
                <span className="ml-auto text-[10px] font-medium bg-stone-100 text-stone-400 px-1.5 py-0.5 rounded-md">
                  Pronto
                </span>
              </div>
            )
          }

          if (item.tag) {
            return (
              <div key={item.label} className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-stone-300">
                <item.icon size={18} strokeWidth={1.5} />
                <span className="text-[14px]">{item.label}</span>
                <span className="ml-auto text-[10px] font-semibold bg-violet-50 text-violet-500 px-1.5 py-0.5 rounded-md">
                  {item.tag}
                </span>
              </div>
            )
          }

          return (
            <NavLink
              key={item.label}
              to={item.to}
              end
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-100',
                  isActive
                    ? 'bg-stone-100 text-stone-900 font-medium'
                    : 'text-stone-500 hover:bg-stone-50 hover:text-stone-700'
                )
              }
            >
              <item.icon size={18} strokeWidth={1.5} />
              <span className="text-[14px]">{item.label}</span>
            </NavLink>
          )
        })}
      </nav>

      {/* Bottom */}
      <div className="px-3 py-2 border-t border-stone-100">
        <NavLink
          to="/processes"
          className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-stone-400 hover:bg-stone-50 hover:text-stone-600 transition-all"
        >
          <Settings size={18} strokeWidth={1.5} />
          <span className="text-[14px]">Configuracion</span>
        </NavLink>
      </div>

      <div className="px-4 py-4 border-t border-stone-100">
        <div className="flex items-center gap-3">
          <div
            className="w-8 h-8 rounded-full flex items-center justify-center text-[11px] font-semibold text-white shrink-0"
            style={{ background: '#1c1917' }}
          >
            {user?.full_name?.[0]?.toUpperCase() || 'U'}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[13px] font-medium text-stone-800 truncate">{user?.full_name}</p>
            <p className="text-[11px] text-stone-400 truncate capitalize">{user?.role}</p>
          </div>
          <button
            onClick={() => { logout(); navigate('/login') }}
            className="text-stone-300 hover:text-red-500 transition-colors p-1"
            title="Cerrar sesion"
          >
            <LogOut size={15} strokeWidth={1.5} />
          </button>
        </div>
      </div>
    </aside>
  )
}
