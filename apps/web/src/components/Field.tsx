/**
 * A labelled text input, styled once. Extracted from `login/page.tsx` when a
 * second and third page (forgot-password, reset-password) needed the exact
 * same field -- not duplicated a second time, but not pulled out before
 * there was a real second caller either.
 */
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
}) {
  return (
    <label className="block">
      <span className="text-xs font-medium uppercase tracking-wide text-ink-500">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1.5 w-full rounded-md border border-line bg-raised px-3 py-2 text-base text-ink-900 transition-colors duration-state focus:border-accent"
        {...rest}
      />
      {hint && <span className="mt-1 block text-xs text-ink-500">{hint}</span>}
    </label>
  );
}
