import { SendHorizontal } from 'lucide-react';
import { useId, type KeyboardEvent, type ReactNode } from 'react';

import { cn } from '@/lib/cn';

interface ComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  label: string;
  placeholder?: string;
  /** A request is in flight: the text stays visible and sending again is blocked. */
  pending?: boolean;
  disabled?: boolean;
  /** Inline validation or send error. The typed text is kept. */
  error?: string | null;
  /** Extra line under the field, for example "Not sent yet". */
  note?: ReactNode;
  maxLength?: number;
}

function prefersTouchKeyboard(): boolean {
  return typeof window.matchMedia === 'function' && window.matchMedia('(pointer: coarse)').matches;
}

/**
 * Multiline message box. With a hardware keyboard, Enter sends and Shift+Enter adds a new
 * line. On touch keyboards Enter always adds a new line and the send button sends, which
 * keeps mobile behaviour predictable. There is no microphone or attachment action in v1.
 */
export function Composer({
  value,
  onChange,
  onSend,
  label,
  placeholder,
  pending = false,
  disabled = false,
  error = null,
  note,
  maxLength = 10_000,
}: ComposerProps) {
  const id = useId();
  const canSend = !pending && !disabled && value.trim().length > 0;

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing || prefersTouchKeyboard()) {
      return;
    }
    event.preventDefault();
    if (canSend) {
      onSend();
    }
  };

  return (
    <form
      className="w-full"
      onSubmit={(event) => {
        event.preventDefault();
        if (canSend) {
          onSend();
        }
      }}
    >
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-ink-secondary">
        {label}
      </label>
      <div
        className={cn(
          'flex items-end gap-2 rounded-card border bg-surface p-2 pl-3 transition-colors duration-150 focus-within:border-primary',
          error ? 'border-urgent' : 'border-line',
        )}
      >
        <textarea
          id={id}
          rows={1}
          value={value}
          maxLength={maxLength}
          placeholder={placeholder}
          disabled={disabled}
          aria-invalid={error ? true : undefined}
          aria-describedby={cn(error && `${id}-error`, note ? `${id}-note` : undefined, `${id}-hint`) || undefined}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          className="max-h-40 min-h-[3rem] flex-1 resize-none bg-transparent py-2 text-ink outline-none [field-sizing:content] focus-visible:outline-none disabled:text-ink-muted"
        />
        <button
          type="submit"
          aria-label={pending ? 'Sending' : 'Send'}
          title="Send"
          disabled={!canSend}
          aria-busy={pending || undefined}
          className="inline-flex size-12 shrink-0 items-center justify-center rounded-control bg-primary text-white transition-colors duration-150 hover:bg-primary-hover disabled:bg-line disabled:text-ink-muted"
        >
          <SendHorizontal aria-hidden="true" className="size-5" />
        </button>
      </div>
      <p id={`${id}-hint`} className="mt-1.5 hidden text-sm text-ink-muted md:block">
        Press Enter to send, Shift+Enter for a new line.
      </p>
      {note ? (
        <p id={`${id}-note`} className="mt-1.5 text-sm text-ink-secondary">
          {note}
        </p>
      ) : null}
      {error ? (
        <p id={`${id}-error`} role="alert" className="mt-1.5 text-sm font-medium text-urgent">
          {error}
        </p>
      ) : null}
    </form>
  );
}
