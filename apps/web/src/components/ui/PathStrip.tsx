/**
 * The lesson's path, as the engine currently sees it.
 *
 * Reads the teaching session's `plan` — topics with a status of done, current
 * or planned — and draws it as a short strip: filled for what is behind,
 * orange for where the lesson is, hollow for what is ahead. It renders
 * nothing until the engine has written a plan, rather than drawing a path
 * it does not have. No logic of its own; the engine decides the plan.
 */

type Step = { topic?: string | null; status?: string | null };

export function PathStrip({ plan, className = '' }: { plan: Step[]; className?: string }) {
  const steps = plan.filter((step) => step.topic);
  if (steps.length === 0) return null;
  return (
    <ol className={`flex flex-wrap gap-x-4 gap-y-2 ${className}`} aria-label="path">
      {steps.map((step, index) => {
        const status = step.status === 'done' || step.status === 'current' ? step.status : 'planned';
        return (
          <li key={`${step.topic}-${index}`} className="flex items-center gap-2 text-sm">
            <span
              aria-hidden="true"
              className={`inline-block h-2.5 w-2.5 rounded-full border ${
                status === 'done'
                  ? 'border-ink-400 bg-ink-400'
                  : status === 'current'
                    ? 'border-signal bg-signal'
                    : 'border-line bg-transparent'
              }`}
            />
            <span
              className={
                status === 'current'
                  ? 'text-ink-900'
                  : status === 'done'
                    ? 'text-ink-500 line-through decoration-ink-300'
                    : 'text-ink-500'
              }
            >
              {step.topic}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
