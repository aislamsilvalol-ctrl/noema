import Link from 'next/link';

const PILLARS = [
  {
    title: 'It models concepts, not cards',
    body: 'A flashcard app knows you failed card 4,182. NOEMA knows you are failing backpropagation because your chain rule mastery is 38%, and it sends you there first.',
  },
  {
    title: 'It catches confident errors',
    body: 'Answer wrong while certain you are right and you have found a misconception — the one failure spaced repetition never catches, because you would never flag it yourself.',
  },
  {
    title: 'It only answers from your materials',
    body: 'Retrieval with enforced citations: source, page, excerpt. When the answer is not in your documents, it says so instead of inventing one.',
  },
  {
    title: 'It can run entirely on your machine',
    body: 'Ollama and local embeddings. Documents, conversations and progress never leave your laptop. No account, no upload, no telemetry.',
  },
];

export default function LandingPage() {
  return (
    <main className="min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <span className="font-display text-lg tracking-tight text-ink-900">NOEMA</span>
        <nav className="flex items-center gap-6 text-sm text-ink-600">
          <a
            href="https://github.com/aislamsilvalol-ctrl/noema"
            className="transition-colors duration-state hover:text-ink-900"
          >
            GitHub
          </a>
          <Link href="/login" className="transition-colors duration-state hover:text-ink-900">
            Sign in
          </Link>
        </nav>
      </header>

      <section className="mx-auto max-w-6xl px-6 pb-24 pt-20 md:pt-32">
        <h1 className="max-w-3xl font-display text-3xl text-ink-900 md:text-4xl">
          Learn anything.
          <br />
          Actually remember it.
        </h1>

        <p className="mt-8 max-w-reading font-serif text-md text-ink-600">
          NOEMA turns your notes, documents and questions into an adaptive learning system
          built around how you learn — what you have mastered, what you are forgetting, and
          what you only think you understand.
        </p>

        <div className="mt-10 flex flex-wrap items-center gap-4">
          <Link
            href="/login"
            className="rounded-md bg-ink-900 px-5 py-2.5 text-sm font-medium text-ink-50 transition-opacity duration-state hover:opacity-90"
          >
            Start learning
          </Link>
          <a
            href="https://github.com/aislamsilvalol-ctrl/noema"
            className="rounded-md border border-line px-5 py-2.5 text-sm font-medium text-ink-700 transition-colors duration-state hover:border-ink-400"
          >
            View on GitHub
          </a>
        </div>
      </section>

      <section className="border-t border-line">
        <div className="mx-auto grid max-w-6xl gap-px bg-line px-6 md:grid-cols-2">
          {PILLARS.map((pillar) => (
            <article key={pillar.title} className="bg-surface px-2 py-12 md:px-8">
              <h2 className="text-lg text-ink-900">{pillar.title}</h2>
              <p className="mt-3 max-w-reading text-base text-ink-600">{pillar.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-6 py-24">
        <p className="max-w-reading font-serif text-md text-ink-600">
          Every product decision answers one question:{' '}
          <em className="text-ink-900">does this help someone actually learn and remember?</em>{' '}
          If the honest answer is no, it does not ship — however good the demo looks.
        </p>
      </section>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-8 text-sm text-ink-500">
          <span>AGPL-3.0 · Open source</span>
          <span className="font-display">Learn anything. Remember everything.</span>
        </div>
      </footer>
    </main>
  );
}
