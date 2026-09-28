// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { I18nProvider } from '@/lib/i18n';
import { LEGAL_ISSUES_URL, type LegalConfig } from '@/lib/legal-config';
import { LegalDocument } from './LegalDocument';

const earlyAccess: LegalConfig = {
  stage: 'early-access',
  lastUpdated: '2026-09-28',
  companyName: null,
  address: null,
  city: null,
  region: null,
  postalCode: null,
  country: null,
  contactEmail: null,
};

const launchedIncomplete: LegalConfig = { ...earlyAccess, stage: 'launched' };

const launchedComplete: LegalConfig = {
  stage: 'launched',
  lastUpdated: '2026-09-28',
  companyName: 'Example Ltda.',
  address: 'Rua Exemplo, 1',
  city: 'Cidade',
  region: 'UF',
  postalCode: '00000-000',
  country: 'Brasil',
  contactEmail: 'legal@example.test',
};

// Anything that would read as an unfilled blank, in any of the three languages.
const PLACEHOLDER = /a definir|por definir|to be defined|configura(ção|ción) necess|configuration required/i;

afterEach(() => {
  window.localStorage.clear();
});

describe('LegalDocument in early access', () => {
  it('shows no placeholders or configuration warning, and points at real channels', () => {
    render(<LegalDocument kind="privacy" config={earlyAccess} />);

    expect(screen.queryByText(PLACEHOLDER)).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(PLACEHOLDER);
    expect(screen.getByText('Early access')).toBeInTheDocument();
    expect(screen.getByText(/^NOEMA is in early access, operated independently by its creator/)).toBeInTheDocument();
    expect(screen.getByText(/^During early access, Noema is operated independently/)).toBeInTheDocument();

    const issues = screen.getByRole('link', { name: 'GitHub issues' });
    expect(issues).toHaveAttribute('href', LEGAL_ISSUES_URL);
    expect(screen.getByText(/use “Report a problem” in the app/)).toBeInTheDocument();
    expect(document.querySelector('a[href^="mailto:"]')).toBeNull();
  });

  it('never invents an identity: no email, address or company appears', () => {
    render(<LegalDocument kind="terms" config={earlyAccess} />);
    expect(document.body.textContent).not.toMatch(/@/);
    expect(screen.getByRole('link', { name: 'GitHub issues' })).toBeInTheDocument();
  });

  it('renders the English document with the real publication date', () => {
    render(<LegalDocument kind="privacy" config={earlyAccess} />);
    expect(screen.getByRole('heading', { level: 1, name: 'Privacy Policy' })).toBeInTheDocument();
    expect(screen.getByText('Last updated: September 28, 2026')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'What we collect' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Account deletion' })).toBeInTheDocument();
  });

  it('follows the chosen language', async () => {
    window.localStorage.setItem('noema.locale', 'pt');
    render(
      <I18nProvider>
        <LegalDocument kind="terms" config={earlyAccess} />
      </I18nProvider>,
    );

    expect(await screen.findByRole('heading', { level: 1, name: 'Termos de Uso' })).toBeInTheDocument();
    expect(screen.getByText('Última atualização: 28 de setembro de 2026')).toBeInTheDocument();
    expect(screen.getByText('Acesso antecipado')).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(PLACEHOLDER);
    expect(screen.getByRole('link', { name: 'Issues no GitHub' })).toHaveAttribute('href', LEGAL_ISSUES_URL);
  });
});

describe('LegalDocument once launched', () => {
  it('still refuses to ship half-filled: warning and placeholders come back', () => {
    render(<LegalDocument kind="privacy" config={launchedIncomplete} />);

    expect(screen.getByText('Configuration required before launch')).toBeInTheDocument();
    expect(screen.getByText(/\[legal name to be defined\], operating Noema/)).toBeInTheDocument();
    expect(screen.getByText(/\[contact email to be defined\]/)).toBeInTheDocument();
    expect(screen.queryByText('Early access')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'GitHub issues' })).not.toBeInTheDocument();
  });

  it('renders the configured identity and a mailto once complete', () => {
    render(<LegalDocument kind="privacy" config={launchedComplete} />);

    expect(screen.queryByText('Configuration required before launch')).not.toBeInTheDocument();
    expect(screen.queryByText('Early access')).not.toBeInTheDocument();
    expect(
      screen.getByText('Example Ltda., operating Noema, based at Rua Exemplo, 1, Cidade - UF, 00000-000, Brasil.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'legal@example.test' })).toHaveAttribute(
      'href',
      'mailto:legal@example.test',
    );
  });
});
