// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { LEGAL_ISSUES_URL, legalConfig } from '@/lib/legal-config';
import PrivacyPage from './page';

// The page renders the real config: whatever is committed is what ships.
describe('PrivacyPage', () => {
  it('is launchable in early access without a blank to fill', () => {
    expect(legalConfig.stage).toBe('early-access');
    render(<PrivacyPage />);

    expect(document.body.textContent).not.toMatch(/a definir|to be defined|configuration required/i);
    expect(screen.getByText('Early access')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'GitHub issues' })).toHaveAttribute('href', LEGAL_ISSUES_URL);
    expect(document.querySelector('a[href^="mailto:"]')).toBeNull();
  });
});
