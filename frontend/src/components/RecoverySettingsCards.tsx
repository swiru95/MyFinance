import { useEffect, useState } from "react";
import { ApiError, api, fmtDateTime } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { RECOVERY_CONFIRMED_EVENT, isNetworkError } from "@/lib/recovery";
import type { ContactState, RecoveryStatus } from "@/lib/types";
import { useSettings } from "./SettingsProvider";
import RecoveryCodeFlow from "./RecoveryCodeFlow";
import RestoreForm from "./RestoreForm";

/** Settings card: recovery-code status, create/replace, and restore. */
export function RecoveryCard() {
  const { t, locale } = useI18n();
  const { timeZone } = useSettings();
  const [status, setStatus] = useState<RecoveryStatus | null>(null);
  const [failed, setFailed] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .recoveryStatus()
      .then((s) => {
        if (!cancelled) setStatus(s);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    // The first-run modal prompt confirms a code on its own copy of the status.
    const onConfirmed = (e: Event) => setStatus((e as CustomEvent<RecoveryStatus>).detail);
    window.addEventListener(RECOVERY_CONFIRMED_EVENT, onConfirmed);
    return () => {
      cancelled = true;
      window.removeEventListener(RECOVERY_CONFIRMED_EVENT, onConfirmed);
    };
  }, []);

  let statusLine = t("rec.set.loading");
  if (failed) {
    statusLine = t("common.failedLoad");
  } else if (status) {
    const date = status.created_at ? fmtDateTime(status.created_at, locale, timeZone) : "";
    if (!status.configured) statusLine = t("rec.set.statusNone");
    else if (!status.confirmed) statusLine = t("rec.set.statusUnconfirmed", { date });
    else if (date) statusLine = t("rec.set.statusConfirmed", { date });
    else statusLine = t("rec.set.statusConfirmedNoDate");
  }

  return (
    <div className="card max-w-md space-y-4">
      <div>
        <h2 className="text-lg font-semibold">{t("rec.set.title")}</h2>
        <p className="text-sm muted">{t("rec.set.subtitle")}</p>
      </div>
      {msg ? <p className="banner-info">{msg}</p> : null}
      {status ? (
        <RecoveryCodeFlow
          replace={status.confirmed}
          intro={<p className="text-sm">{statusLine}</p>}
          startLabel={status.configured ? t("rec.set.createNew") : t("rec.set.create")}
          confirmStart={status.confirmed ? t("rec.set.replaceConfirm") : undefined}
          onConfirmed={(s) => {
            setStatus(s);
            setMsg(t("rec.set.confirmedMsg"));
          }}
          onDismiss={() => setMsg(null)}
        />
      ) : (
        <p className="text-sm">{statusLine}</p>
      )}
      <div className="divider space-y-3 border-t pt-4">
        <h3 className="text-sm font-semibold">{t("rec.set.restoreTitle")}</h3>
        <p className="text-xs muted">{t("rec.set.restoreBody")}</p>
        <RestoreForm inputId="set-recovery-code" />
      </div>
    </div>
  );
}

/** Settings card: opt-in to future e-mail notifications. */
export function NotificationsCard() {
  const { t } = useI18n();
  const [state, setState] = useState<ContactState | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getContact()
      .then((s) => {
        if (!cancelled) setState(s);
      })
      .catch(() => {
        if (!cancelled) setMsg(t("rec.contact.loadFailed"));
      });
    return () => {
      cancelled = true;
    };
    // Load once; t is stable per language and a re-fetch on a language
    // switch would be pointless.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function change(optIn: boolean) {
    setBusy(true);
    setMsg(null);
    try {
      setState(await (optIn ? api.optInContact() : api.optOutContact()));
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // No verified e-mail on the token: reflect it instead of an error.
        setState((s) => (s ? { ...s, can_opt_in: false } : s));
      } else {
        setMsg(isNetworkError(err) ? t("rec.err.network") : t("common.failedSave"));
      }
    } finally {
      setBusy(false);
    }
  }

  const blocked = !!state && !state.opted_in && !state.can_opt_in;

  return (
    <div className="card max-w-md space-y-4">
      <div>
        <h2 className="text-lg font-semibold">{t("rec.contact.title")}</h2>
        <p className="text-sm muted">{t("rec.contact.subtitle")}</p>
      </div>
      <p className="text-xs muted">{t("rec.contact.body")}</p>
      {state ? (
        <>
          <p className="text-sm font-medium">
            {state.opted_in ? t("rec.contact.on") : t("rec.contact.off")}
          </p>
          {blocked ? <p className="text-xs subtle">{t("rec.contact.noEmail")}</p> : null}
          <div className="flex flex-wrap gap-2">
            {state.opted_in ? (
              <button
                type="button"
                className="btn-ghost"
                disabled={busy}
                onClick={() => change(false)}
              >
                {t("rec.contact.optOut")}
              </button>
            ) : (
              <button
                type="button"
                className="btn-primary"
                disabled={busy || blocked}
                onClick={() => change(true)}
              >
                {t("rec.contact.optIn")}
              </button>
            )}
          </div>
        </>
      ) : msg ? null : (
        <p className="text-sm muted">{t("common.loading")}</p>
      )}
      {msg ? <p className="banner-error">{msg}</p> : null}
    </div>
  );
}

/** Settings card: optional birth year, stored encrypted by the backend. */
export function BirthYearCard() {
  const { t } = useI18n();
  const { settings, apply } = useSettings();
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ error: boolean; text: string } | null>(null);
  const maxYear = new Date().getFullYear();

  useEffect(() => {
    if (!settings) return;
    setValue(settings.birth_year != null ? String(settings.birth_year) : "");
  }, [settings]);

  async function submit(year: number | null) {
    setBusy(true);
    setMsg(null);
    try {
      apply(await api.setBirthYear(year));
      setMsg({ error: false, text: year === null ? t("rec.birth.cleared") : t("rec.birth.saved") });
    } catch (err) {
      setMsg({
        error: true,
        text: isNetworkError(err)
          ? t("rec.err.network")
          : err instanceof ApiError && err.status === 422
            ? t("rec.birth.invalid", { max: maxYear })
            : t("common.failedSave"),
      });
    } finally {
      setBusy(false);
    }
  }

  function save(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = value.trim();
    const year = Number(trimmed);
    if (!/^\d{4}$/.test(trimmed) || !Number.isInteger(year) || year < 1900 || year > maxYear) {
      setMsg({ error: true, text: t("rec.birth.invalid", { max: maxYear }) });
      return;
    }
    void submit(year);
  }

  return (
    <form onSubmit={save} className="card max-w-md space-y-4">
      <div>
        <h2 className="text-lg font-semibold">{t("rec.birth.title")}</h2>
        <p className="text-sm muted">{t("rec.birth.subtitle")}</p>
      </div>
      <div>
        <label className="label" htmlFor="set-birth-year">
          {t("rec.birth.label")}
        </label>
        <input
          id="set-birth-year"
          type="number"
          inputMode="numeric"
          className="input"
          min={1900}
          max={maxYear}
          step={1}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          disabled={busy}
        />
      </div>
      {msg ? <p className={msg.error ? "banner-error" : "banner-info"}>{msg.text}</p> : null}
      <div className="flex flex-wrap gap-2">
        <button type="submit" className="btn-primary" disabled={busy || !value.trim()}>
          {busy ? t("common.saving") : t("common.save")}
        </button>
        <button
          type="button"
          className="btn-ghost"
          disabled={busy || settings?.birth_year == null}
          onClick={() => {
            setValue("");
            void submit(null);
          }}
        >
          {t("rec.birth.clear")}
        </button>
      </div>
    </form>
  );
}
