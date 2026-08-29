// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ExamPage from './page';
import type { Exam } from '@/lib/api';

// Next's real useParams()/useRouter()/useSearchParams() are referentially
// stable across renders; a fresh object literal here would give this page's
// load-by-id effect a new dependency identity every render and retrigger it
// in a loop (see cards/page.test.tsx and notebooks/[id]/page.test.tsx, where
// this bit before).
const push = vi.fn();
const router = { push };
let params = new URLSearchParams();
vi.mock('next/navigation', () => ({
  useParams: () => ({ id: 'nb-1' }),
  useRouter: () => router,
  useSearchParams: () => params,
}));

vi.mock('@/components/Shell', () => ({
  Shell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/components/QuestionInput', () => ({
  QuestionInput: () => <div />,
}));

const exam: Exam = {
  id: 'exam-1',
  notebook_id: 'nb-1',
  minutes: 20,
  started_at: new Date().toISOString(),
  submitted_at: null,
  score: null,
  overtime: false,
  results: { concepts: [] },
  questions: [
    {
      id: 'q-1',
      notebook_id: 'nb-1',
      concept_id: null,
      type: 'true_false',
      difficulty: 'medium',
      prompt: 'The heart has four chambers.',
      payload: { statement: 'The heart has four chambers.' },
      created_at: new Date().toISOString(),
    },
  ],
};

const { apiExam } = vi.hoisted(() => ({ apiExam: vi.fn() }));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return { ...actual, api: { ...actual.api, exam: apiExam } };
});

afterEach(() => {
  apiExam.mockReset();
  params = new URLSearchParams();
});

describe('ExamPage', () => {
  it('offers to start a fresh exam when there is no examId in the URL', async () => {
    render(<ExamPage />);
    await screen.findByText(/sit an exam/i);
    expect(apiExam).not.toHaveBeenCalled();
  });

  it('loads an already-generated exam by id from the URL, without a second start', async () => {
    params = new URLSearchParams({ examId: 'exam-1' });
    apiExam.mockResolvedValue(exam);

    render(<ExamPage />);

    await screen.findByText('The heart has four chambers.');
    expect(apiExam).toHaveBeenCalledWith('exam-1');
    expect(apiExam).toHaveBeenCalledTimes(1);
  });
});
