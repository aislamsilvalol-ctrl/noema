'use client';

/**
 * Two-step verification in Settings: off, setting up, showing the recovery
 * codes once, on. The QR code arrives from the server as SVG and is drawn as
 * an <img> from a data URI, never injected as markup.
 */

import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { api } from '@/lib/api';
import { humanError, passwordError } from '@/lib/errors';
import { useT } from '@/lib/i18n';

type Stage =
  | { kind: 'loading' }
  | { kind: 'off' }
  | { kind: 'password'; then: 'setup' | 'codes' | 'disable' }
  | { kind: 'scan'; secret: string; qr: string }
  | { kind: 'codes'; codes: string[] }
  | { kind: 'on'; left: number };

export function MfaSection() {
  const t = useT();
  const copy = t.security;
  const [stage, setStage] = useState<Stage>({ kind: 'loading' });
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const status = await api.mfaStatus();
      setStage(status.enabled ? { kind: 'on', left: status.recovery_codes_left } : { kind: 'off' });
    } catch (err) {
      setMessage(humanError(err, t, 'load'));
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  function reset() {
    setPassword('');
    setCode('');
    setMessage(null);
  }

  async function run(task: () => Promise<void>, wrong: string) {
    setBusy(true);
    setMessage(null);
    try {
      await task();
    } catch (err) {
      setMessage(passwordError(err, wrong, humanError(err, t, 'save')));
    } finally {
      setBusy(false);
    }
  }

  function withPassword(event: FormEvent) {
    event.preventDefault();
    if (stage.kind !== 'password') return;
    const then = stage.then;
    void run(async () => {
      if (then === 'setup') {
        const setup = await api.mfaSetup(password);
        setStage({ kind: 'scan', secret: setup.secret, qr: setup.qr_svg });
      } else if (then === 'codes') {
        const { recovery_codes } = await api.mfaRecoveryCodes(password);
        setStage({ kind: 'codes', codes: recovery_codes });
      } else {
        await api.mfaDisable(password, code);
        setStage({ kind: 'off' });
      }
      setPassword('');
      setCode('');
    }, then === 'disable' ? copy.mfaWrongCode : copy.wrong);
  }

  function confirmCode(event: FormEvent) {
    event.preventDefault();
    void run(async () => {
      const { recovery_codes } = await api.mfaConfirm(code);
      setCode('');
      setStage({ kind: 'codes', codes: recovery_codes });
    }, copy.mfaWrongCode);
  }

  return (
    <div className="mt-10" data-mfa>
      <h3 className="text-base text-ink-900">{copy.mfa}</h3>

      {stage.kind === 'off' && (
        <>
          <p className="mt-2 text-sm text-ink-600">{copy.mfaOffLede}</p>
          <Button
            variant="secondary"
            size="sm"
            className="mt-4"
            onClick={() => {
              reset();
              setStage({ kind: 'password', then: 'setup' });
            }}
          >
            {copy.mfaTurnOn}
          </Button>
        </>
      )}

      {stage.kind === 'on' && (
        <>
          <p className="mt-2 text-sm text-ink-600">{copy.mfaOnLede}</p>
          <p className="mt-1 text-sm text-ink-500">{copy.mfaCodesLeft(stage.left)}</p>
          <div className="mt-4 flex flex-wrap gap-3">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                reset();
                setStage({ kind: 'password', then: 'codes' });
              }}
            >
              {copy.mfaNewCodes}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                reset();
                setStage({ kind: 'password', then: 'disable' });
              }}
            >
              {copy.mfaTurnOff}
            </Button>
          </div>
        </>
      )}

      {stage.kind === 'password' && (
        <form className="mt-4 space-y-4" onSubmit={withPassword}>
          <label className="block">
            <span className="text-sm text-ink-600">{copy.confirm}</span>
            <Input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="mt-1.5 block w-full max-w-sm"
              autoFocus
              required
            />
          </label>
          {stage.then === 'disable' && (
            <label className="block">
              <span className="text-sm text-ink-600">{t.login.mfaCode}</span>
              <Input
                inputMode="numeric"
                autoComplete="one-time-code"
                value={code}
                onChange={(event) => setCode(event.target.value)}
                className="mt-1.5 block w-full max-w-[12rem]"
                required
              />
            </label>
          )}
          <div className="flex gap-3">
            <Button type="submit" variant="secondary" size="sm" busy={busy ? copy.mfaConfirm : undefined}>
              {copy.mfaConfirm}
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => void load()}>
              {t.common.cancel}
            </Button>
          </div>
        </form>
      )}

      {stage.kind === 'scan' && (
        <form className="mt-4 space-y-4" onSubmit={confirmCode}>
          <p className="text-sm text-ink-600">{copy.mfaScan}</p>
          {/* eslint-disable-next-line @next/next/no-img-element -- a data URI, not an asset */}
          <img
            src={`data:image/svg+xml;utf8,${encodeURIComponent(stage.qr)}`}
            alt=""
            width={200}
            height={200}
            className="rounded-md border border-line bg-white p-2"
          />
          <p className="text-sm text-ink-600">
            {copy.mfaManual}{' '}
            <code className="select-all break-all font-mono text-sm text-ink-900">{stage.secret}</code>
          </p>
          <label className="block">
            <span className="text-sm text-ink-600">{t.login.mfaCode}</span>
            <Input
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              className="mt-1.5 block w-full max-w-[12rem]"
              autoFocus
              required
            />
          </label>
          <Button type="submit" variant="primary" size="sm" busy={busy ? copy.mfaConfirm : undefined}>
            {copy.mfaConfirm}
          </Button>
        </form>
      )}

      {stage.kind === 'codes' && (
        <div className="mt-4">
          <p className="text-md text-ink-900">{copy.mfaCodesTitle}</p>
          <p className="mt-1 text-sm text-ink-600">{copy.mfaCodesLede}</p>
          <ul className="mt-4 grid max-w-sm grid-cols-2 gap-2 font-mono text-sm text-ink-900" data-recovery-codes>
            {stage.codes.map((item) => (
              <li key={item} className="select-all">
                {item}
              </li>
            ))}
          </ul>
          <Button variant="secondary" size="sm" className="mt-4" onClick={() => void load()}>
            {copy.mfaCodesDone}
          </Button>
        </div>
      )}

      {message && (
        <p role="alert" className="mt-3 text-sm text-critical">
          {message}
        </p>
      )}
    </div>
  );
}
