import { useState } from 'react';

import { INFO_PAGES, type InfoPageId } from '@/content/infoPages';

import { InfoDialog } from './InfoDialog';
import { Logo } from './Logo';

export function SiteFooter() {
  const [page, setPage] = useState<InfoPageId | null>(null);
  return (
    <footer className="border-t border-line bg-surface print:hidden">
      <div className="mx-auto flex max-w-[1200px] flex-col gap-4 px-4 py-8 sm:px-6 md:flex-row md:items-center md:justify-between">
        <div>
          <Logo />
          <p className="mt-2 max-w-md text-sm text-ink-secondary">
            Design demo. Feeltriva does not confirm a diagnosis and has not been clinically validated.
          </p>
        </div>
        <nav aria-label="Footer">
          <ul className="flex flex-wrap gap-x-2 gap-y-1">
            {INFO_PAGES.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => setPage(item.id)}
                  className="inline-flex min-h-11 items-center rounded-control px-3 font-medium text-ink-secondary hover:bg-teal-soft hover:text-ink"
                >
                  {item.id === 'about' ? 'About' : item.title}
                </button>
              </li>
            ))}
          </ul>
        </nav>
      </div>
      <InfoDialog page={page} onClose={() => setPage(null)} />
    </footer>
  );
}
