import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { Menu } from 'lucide-react';
import { Link, Outlet } from 'react-router';

import { Logo } from './Logo';
import { SiteFooter } from './SiteFooter';
import { ButtonLink } from './ui/Button';

const LINKS = [
  { label: 'How it works', to: { pathname: '/', hash: '#how-it-works' } },
  { label: 'About your data', to: { pathname: '/', hash: '#your-data' } },
] as const;

const NAV_LINK_CLASSES =
  'inline-flex min-h-11 items-center rounded-control px-3 font-medium text-ink-secondary hover:bg-teal-soft hover:text-ink';

/** Header and footer for the public screens (introduction, start). */
export function PublicLayout() {
  return (
    <>
      <header className="border-b border-line bg-surface print:hidden">
        <div className="mx-auto flex max-w-[1200px] items-center justify-between gap-2 px-4 py-2 sm:px-6">
          <Link to="/" className="inline-flex min-h-11 items-center rounded-control">
            <Logo />
          </Link>

          <nav aria-label="Main" className="hidden items-center gap-1 md:flex">
            {LINKS.map((link) => (
              <Link key={link.label} to={link.to} className={NAV_LINK_CLASSES}>
                {link.label}
              </Link>
            ))}
            <ButtonLink to="/start" size="sm" className="ml-2">
              Start symptom check
            </ButtonLink>
          </nav>

          <div className="md:hidden">
            <DropdownMenu.Root>
              <DropdownMenu.Trigger
                aria-label="Menu"
                className="inline-flex size-11 items-center justify-center rounded-control text-ink-secondary hover:bg-teal-soft hover:text-ink"
              >
                <Menu aria-hidden="true" className="size-5" />
              </DropdownMenu.Trigger>
              <DropdownMenu.Portal>
                <DropdownMenu.Content
                  align="end"
                  sideOffset={6}
                  className="z-50 min-w-56 rounded-control border border-line bg-surface p-1.5 shadow-float"
                >
                  {LINKS.map((link) => (
                    <DropdownMenu.Item key={link.label} asChild>
                      <Link
                        to={link.to}
                        className="flex min-h-11 items-center rounded-lg px-3 font-medium text-ink data-[highlighted]:bg-teal-soft data-[highlighted]:outline-none"
                      >
                        {link.label}
                      </Link>
                    </DropdownMenu.Item>
                  ))}
                  <DropdownMenu.Item asChild>
                    <Link
                      to="/start"
                      className="flex min-h-11 items-center rounded-lg px-3 font-semibold text-primary data-[highlighted]:bg-teal-soft data-[highlighted]:outline-none"
                    >
                      Start symptom check
                    </Link>
                  </DropdownMenu.Item>
                </DropdownMenu.Content>
              </DropdownMenu.Portal>
            </DropdownMenu.Root>
          </div>
        </div>
      </header>
      <main id="main-content" className="flex-1">
        <Outlet />
      </main>
      <SiteFooter />
    </>
  );
}
