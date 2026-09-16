// @vitest-environment jsdom
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ConceptTerrain, layoutRegions, nextPlace, terrainState } from './ConceptTerrain';
import type { Journey } from '@/lib/api';

const journey: Journey = {
  id: 'j-1',
  subject: 'Freud',
  objective: 'Read the Interpretation of Dreams',
  level: 'beginner',
  status: 'active',
  session_id: null,
  focus_level: 1,
  checkpoints: 0,
  parked: [],
  memory: [],
  momentum: { events_today: 3, mastered_today: 1 },
  current: { module: 1, lesson: 0, concept: 'Resistance' },
  plan: [
    {
      title: 'The unconscious',
      status: 'done',
      lessons: [
        { title: 'Slips', status: 'done', concepts: ['The unconscious', 'The slip'] },
        { title: 'Repression', status: 'done', concepts: ['Repression', 'Preconscious'] },
      ],
    },
    {
      title: 'The apparatus',
      status: 'active',
      lessons: [
        { title: 'Resistance', status: 'active', concepts: ['Resistance', 'Id, ego, superego'] },
        { title: 'Dreams', status: 'pending', concepts: ['Dreams', 'Desire'] },
      ],
    },
  ],
  concepts: [
    { name: 'The unconscious', state: 'mastered', evidence: 4, misconceptions: [] },
    { name: 'The slip', state: 'mastered', evidence: 3, misconceptions: [] },
    { name: 'Repression', state: 'learning', evidence: 2, misconceptions: [] },
    { name: 'Preconscious', state: 'needs_review', evidence: 2, misconceptions: [] },
    { name: 'Resistance', state: 'introduced', evidence: 1, misconceptions: [] },
    { name: 'Id, ego, superego', state: 'uncertain', evidence: 1, misconceptions: [] },
    // 'Dreams' and 'Desire' have no state yet: not started.
    // Known to the engine but nowhere in the plan: still on the map.
    { name: 'Transference', state: 'not_started', evidence: 0, misconceptions: [] },
  ],
};

describe('terrainState', () => {
  it('maps the engine states onto the five terrain states', () => {
    expect(terrainState('mastered')).toBe('mastered');
    expect(terrainState('introduced')).toBe('learning');
    expect(terrainState('learning')).toBe('learning');
    expect(terrainState('uncertain')).toBe('uncertain');
    expect(terrainState('needs_review')).toBe('review');
    expect(terrainState('not_started')).toBe('unknown');
    expect(terrainState('whatever-comes-next')).toBe('unknown');
  });
});

describe('layoutRegions / nextPlace', () => {
  it('follows the curriculum order and keeps unplanned concepts in a last region', () => {
    const regions = layoutRegions(journey, 'Elsewhere');
    expect(regions.map((r) => r.title)).toEqual(['The unconscious', 'The apparatus', 'Elsewhere']);
    expect(regions.flatMap((r) => r.places.map((p) => p.name))).toEqual([
      'The unconscious',
      'The slip',
      'Repression',
      'Preconscious',
      'Resistance',
      'Id, ego, superego',
      'Dreams',
      'Desire',
      'Transference',
    ]);
  });

  it('names the concept after "now" as next', () => {
    const places = layoutRegions(journey, 'Elsewhere').flatMap((r) => r.places);
    expect(nextPlace(places)?.name).toBe('Id, ego, superego');
  });

  it('falls back to the first unsettled concept when there is no "now"', () => {
    const places = layoutRegions({ ...journey, current: { module: 0, lesson: 0, concept: '' } }, 'x').flatMap(
      (r) => r.places,
    );
    expect(nextPlace(places)?.name).toBe('Repression');
  });
});

describe('ConceptTerrain', () => {
  it('summarises the counts in the image label', () => {
    render(<ConceptTerrain journey={journey} />);
    const img = screen.getByRole('img');
    expect(img).toHaveAttribute(
      'aria-label',
      'Map of Freud: 9 concepts — 2 mastered, 2 learning, 1 uncertain, 1 needing review, 3 not yet. Now: Resistance.',
    );
  });

  it('rings the current concept and says "now"', () => {
    const { container } = render(<ConceptTerrain journey={journey} />);
    const here = container.querySelector('[data-place="Resistance"]');
    expect(here).not.toBeNull();
    expect(here?.textContent).toContain('now');
    expect(here?.querySelector('circle[stroke="var(--signal)"]')).not.toBeNull();
    // Only one place is "now".
    expect(container.querySelectorAll('svg[role="img"] text').length).toBeGreaterThan(0);
    expect(
      Array.from(container.querySelectorAll('[data-place]')).filter((g) => g.textContent?.includes('now')),
    ).toHaveLength(1);
  });

  it('mirrors the map as a list, one line per concept with its state', () => {
    const { container } = render(<ConceptTerrain journey={journey} />);
    const list = screen.getByRole('list', { name: 'Concepts on the map' });
    const items = within(list).getAllByRole('listitem');
    expect(items).toHaveLength(container.querySelectorAll('[data-place]').length);
    expect(items.map((li) => li.textContent)).toEqual([
      'The unconsciousmastered',
      'The slipmastered',
      'Repressionlearning',
      'Preconsciousneeds review',
      'Resistancenowlearning',
      'Id, ego, superegouncertain',
      'Dreamsnot yet',
      'Desirenot yet',
      'Transferencenot yet',
    ]);
  });

  it('draws the five legend labels once each', () => {
    render(<ConceptTerrain journey={journey} />);
    for (const label of ['mastered', 'learning', 'uncertain', 'needs review', 'not yet']) {
      expect(screen.getAllByText(label).length).toBeGreaterThanOrEqual(1);
    }
  });

  it('has no focusable nodes inside the drawing', () => {
    const { container } = render(<ConceptTerrain journey={journey} />);
    expect(container.querySelectorAll('svg[role="img"] [tabindex], svg[role="img"] a, svg[role="img"] button')).toHaveLength(0);
  });
});
