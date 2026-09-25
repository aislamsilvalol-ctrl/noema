/**
 * A labelled text input, styled once. Extracted from `login/page.tsx` when a
 * second and third page (forgot-password, reset-password) needed the exact
 * same field -- not duplicated a second time, but not pulled out before
 * there was a real second caller either. The box itself is the shared
 * `Input`; this adds the label and hint the auth screens share.
 */
import { Input } from '@/components/ui/Input';

export function Field({
  label,
  value,
  onChange,
  type = 'text',
  hint,
  ...rest
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  hint?: string;
  required?: boolean;
  autoComplete?: string;
  inputMode?: 'text' | 'numeric' | 'email';
  autoFocus?: boolean;
}) {
  return (
    <label className="block">
      <span className="text-xs font-medium uppercase tracking-wide text-ink-500">{label}</span>
      <Input
        type={type}
        size="lg"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1.5 w-full"
        {...rest}
      />
      {hint && <span className="mt-1 block text-xs text-ink-500">{hint}</span>}
    </label>
  );
}
