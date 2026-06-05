'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Zap, BarChart2, ClipboardList, Search, Settings, Shield } from 'lucide-react'
import clsx from 'clsx'

const links = [
  { href: '/queue',      label: 'Live Queue',       icon: Zap },
  { href: '/metrics',    label: 'FP Metrics',       icon: BarChart2 },
  { href: '/audit',      label: 'Suppression Audit', icon: ClipboardList },
  { href: '/detail',     label: 'Alert Detail',     icon: Search },
  { href: '/thresholds', label: 'Thresholds',       icon: Settings },
]

export default function Nav() {
  const pathname = usePathname()

  return (
    <aside className="w-56 flex-shrink-0 border-r border-border bg-canvas-overlay flex flex-col">
      {/* Logo */}
      <div className="px-4 py-5 border-b border-border">
        <div className="flex items-center gap-2">
          <Shield className="text-accent-blue" size={20} />
          <div>
            <p className="text-sm font-semibold text-fg leading-tight">AML/TMS</p>
            <p className="text-xs text-fg-muted leading-tight">Enhancement Agent</p>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-2 py-4 space-y-0.5">
        {links.map(({ href, label, icon: Icon }) => {
          const active = pathname === href
          return (
            <Link
              key={href}
              href={href}
              className={clsx(
                'flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors',
                active
                  ? 'bg-canvas-subtle text-fg font-medium'
                  : 'text-fg-muted hover:text-fg hover:bg-canvas-subtle'
              )}
            >
              <Icon size={15} />
              {label}
            </Link>
          )
        })}
      </nav>

      {/* Footer */}
      <div className="px-4 py-4 border-t border-border space-y-1">
        <p className="text-xs text-fg-subtle">Regulatory framework</p>
        <div className="flex flex-wrap gap-1">
          {['BSA', 'SR 11-7', 'FinCEN', 'FATF'].map(tag => (
            <span key={tag} className="text-xs px-1.5 py-0.5 bg-canvas-subtle border border-border rounded text-fg-muted">
              {tag}
            </span>
          ))}
        </div>
      </div>
    </aside>
  )
}
