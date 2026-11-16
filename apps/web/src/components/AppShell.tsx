import {
  Lock,
  Menu,
  MessageSquarePlus,
  MessagesSquare,
  NotebookText,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { Link, NavLink, Outlet } from 'react-router';

import { cn } from '@/lib/cn';
import { useRegistryEntries } from '@/state/hooks';
import { usePreferences } from '@/state/preferencesContext';
import { useServices } from '@/state/services';

import { Logo } from './Logo';
import { IconButton } from './ui/Button';
import { Sheet } from './ui/Sheet';

interface NavItem {
  label: string;
  to: string | null;
  icon: ReactNode;
  /** Shown instead of a link when the destination does not exist yet. */
  unavailableHint?: string;
  end?: boolean;
}

function useNavItems(): NavItem[] {
  const { registry } = useServices();
  // Subscribing keeps "This conversation" in step with sessions being created or deleted.
  useRegistryEntries();
  const latest = registry.latestActiveSessionId();
  return [
    {
      label: 'New symptom check',
      to: '/start',
      icon: <MessageSquarePlus aria-hidden="true" className="size-5 shrink-0" />,
    },
    {
      label: 'This conversation',
      to: latest ? `/assess/${latest}` : null,
      icon: <MessagesSquare aria-hidden="true" className="size-5 shrink-0" />,
      unavailableHint: 'No conversation yet',
    },
    { label: 'Saved summaries', to: '/history', icon: <NotebookText aria-hidden="true" className="size-5 shrink-0" /> },
    { label: 'Privacy', to: '/settings/privacy', icon: <Lock aria-hidden="true" className="size-5 shrink-0" /> },
  ];
}

function NavList({
  items,
  collapsed = false,
  onNavigate,
}: {
  items: NavItem[];
  collapsed?: boolean;
  onNavigate?: () => void;
}) {
  return (
    <ul className="space-y-1">
      {items.map((item) => (
        <li key={item.label}>
          {item.to ? (
            <NavLink
              to={item.to}
              onClick={onNavigate}
              title={collapsed ? item.label : undefined}
              className={({ isActive }) =>
                cn(
                  'flex min-h-11 items-center gap-3 rounded-control px-3 py-2 font-medium transition-colors duration-150',
                  collapsed && 'justify-center px-0',
                  isActive ? 'bg-teal-soft text-ink' : 'text-ink-secondary hover:bg-page hover:text-ink',
                )
              }
            >
              {item.icon}
              <span className={cn(collapsed && 'sr-only')}>{item.label}</span>
            </NavLink>
          ) : (
            <span
              aria-disabled="true"
              title={collapsed ? `${item.label}: ${item.unavailableHint ?? 'Unavailable'}` : undefined}
              className={cn(
                'flex min-h-11 items-center gap-3 rounded-control px-3 py-2 font-medium text-ink-muted',
                collapsed && 'justify-center px-0',
              )}
            >
              {item.icon}
              <span className={cn(collapsed && 'sr-only')}>
                {item.label}
                <span className="block text-sm font-normal">{item.unavailableHint}</span>
              </span>
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

/**
 * Signed-in style application frame: a 224px navigation rail on wide screens (1280px+),
 * collapsing to a menu button and drawer below that. Content is capped at 1440px.
 */
export function AppShell() {
  const items = useNavItems();
  const { navCollapsed, setNavCollapsed } = usePreferences();
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-1">
      <nav
        aria-label="Main"
        className={cn(
          'sticky top-[var(--demo-banner-height,0px)] hidden h-[calc(100dvh-var(--demo-banner-height,0px))] shrink-0 flex-col border-r border-line bg-surface px-3 py-4 xl:flex print:hidden',
          navCollapsed ? 'w-[4.5rem]' : 'w-56',
        )}
      >
        <Link
          to="/"
          className={cn(
            'mb-5 inline-flex min-h-11 items-center rounded-control px-2',
            navCollapsed && 'justify-center px-0',
          )}
        >
          <Logo compact={navCollapsed} />
        </Link>
        <NavList items={items} collapsed={navCollapsed} />
        <div className={cn('mt-auto flex', navCollapsed ? 'justify-center' : 'justify-end')}>
          <IconButton
            label={navCollapsed ? 'Expand navigation' : 'Collapse navigation'}
            aria-expanded={!navCollapsed}
            onClick={() => setNavCollapsed(!navCollapsed)}
          >
            {navCollapsed ? (
              <PanelLeftOpen aria-hidden="true" className="size-5" />
            ) : (
              <PanelLeftClose aria-hidden="true" className="size-5" />
            )}
          </IconButton>
        </div>
      </nav>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-1 border-b border-line bg-surface px-2 py-1.5 xl:hidden print:hidden">
          <IconButton label="Open navigation" onClick={() => setDrawerOpen(true)}>
            <Menu aria-hidden="true" className="size-5" />
          </IconButton>
          <Link to="/" className="inline-flex min-h-11 items-center rounded-control px-1">
            <Logo />
          </Link>
        </header>
        <main id="main-content" className="flex min-w-0 flex-1 flex-col">
          <Outlet />
        </main>
      </div>

      <Sheet open={drawerOpen} onOpenChange={setDrawerOpen} side="left" title="Navigation">
        <nav aria-label="Main">
          <NavList items={items} onNavigate={() => setDrawerOpen(false)} />
        </nav>
      </Sheet>
    </div>
  );
}
