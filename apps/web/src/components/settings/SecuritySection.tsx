'use client';

/**
 * The account's own security: the password, and every device signed in.
 *
 * A wrong current password is a 403 from the server, not a 401: the session is
 * fine, the confirmation is not, and this screen says so without signing the
 * owner out for a typo.
 */

import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { api, type ActiveSession } from '@/lib/api';
import { humanError, passwordError } from '@/lib/errors';
import { MfaSection } from '@/components/settings/MfaSection';
import { useI18n, useT } from '@/lib/i18n';


export function SecuritySection() {
  const t = useT();
  const { locale } = useI18n();
  const copy = t.security;
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [saving, setSaving] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState<{ ok: boolean; text: string } | null>(
    null,
  );
  const [devices, setDevices] = useState<ActiveSession[] | null>(null);
  const [devicesMessage, setDevicesMessage] = useState<string | null>(null);

  const loadDevices = useCallback(async () => {
    try {
      setDevices(await api.activeSessions());
    } catch (err) {
      setDevicesMessage(humanError(err, t, 'load'));
    }
  }, [t]);

  useEffect(() => {
    void loadDevices();
  }, [loadDevices]);

  async function changePassword(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setPasswordMessage(null);
    try {
      await api.changePassword(current, next);
      setCurrent('');
      setNext('');
      setPasswordMessage({ ok: true, text: copy.saved });
      void loadDevices();
    } catch (err) {
      setPasswordMessage({ ok: false, text: passwordError(err, copy.wrong, humanError(err, t, 'save')) });
    } finally {
      setSaving(false);
    }
  }

  async function end(id: string) {
    setDevicesMessage(null);
    try {
      await api.endSession(id);
      await loadDevices();
    } catch (err) {
      setDevicesMessage(humanError(err, t, 'save'));
    }
  }

  async function endOthers() {
    setDevicesMessage(null);
    try {
      const { revoked } = await api.endOtherSessions();
      setDevicesMessage(copy.endedOthers(revoked));
      await loadDevices();
    } catch (err) {
      setDevicesMessage(humanError(err, t, 'save'));
    }
  }

  const date = new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short' });
  const others = devices?.filter((device) => !device.current) ?? [];

  return (
    <section className="mt-16 max-w-reading" aria-labelledby="security-title" data-security>
      <h2 id="security-title" className="text-lg text-ink-900">
        {copy.title}
      </h2>
      <p className="mt-2 text-sm text-ink-600">{copy.lede}</p>

      <form className="mt-6 space-y-4" onSubmit={changePassword} aria-label={copy.password}>
        <h3 className="text-base text-ink-900">{copy.password}</h3>
        <label className="block">
          <span className="text-sm text-ink-600">{copy.current}</span>
          <Input
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(event) => setCurrent(event.target.value)}
            className="mt-1.5 block w-full max-w-sm"
            required
          />
        </label>
        <label className="block">
          <span className="text-sm text-ink-600">{copy.new}</span>
          <Input
            type="password"
            autoComplete="new-password"
            minLength={12}
            value={next}
            onChange={(event) => setNext(event.target.value)}
            className="mt-1.5 block w-full max-w-sm"
            required
          />
          <span className="mt-1 block text-sm text-ink-500">{copy.newHint}</span>
        </label>
        <Button type="submit" variant="secondary" busy={saving ? copy.save : undefined}>
          {copy.save}
        </Button>
        {passwordMessage && (
          <p role={passwordMessage.ok ? 'status' : 'alert'} className={`text-sm ${passwordMessage.ok ? 'text-ink-700' : 'text-critical'}`}>
            {passwordMessage.text}
          </p>
        )}
      </form>

      <MfaSection />

      <div className="mt-10">
        <h3 className="text-base text-ink-900">{copy.devices}</h3>
        {devices && (
          <ul className="mt-3 divide-y divide-line border-y border-line">
            {devices.map((device) => {
              const name = [device.browser, device.os].filter(Boolean).join(' · ') || copy.unknownDevice;
              return (
                <li key={device.id} className="flex items-center justify-between gap-4 py-4">
                  <span className="min-w-0">
                    <span className="block text-md text-ink-900">{name}</span>
                    <span className="block text-sm text-ink-500">
                      {device.current
                        ? copy.thisDevice
                        : copy.lastActive(date.format(new Date(device.last_active_at)))}
                      {' · '}
                      {copy.since(date.format(new Date(device.started_at)))}
                    </span>
                  </span>
                  {!device.current && (
                    <Button variant="ghost" size="sm" onClick={() => void end(device.id)}>
                      {copy.end}
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        {others.length > 0 && (
          <Button variant="secondary" size="sm" className="mt-4" onClick={() => void endOthers()}>
            {copy.endOthers}
          </Button>
        )}
        {devicesMessage && (
          <p role="status" className="mt-3 text-sm text-ink-600">
            {devicesMessage}
          </p>
        )}
      </div>
    </section>
  );
}
