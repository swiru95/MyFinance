import { useCallback, useEffect, useRef, useState } from "react";
import { insightsApi, isNotFound } from "@/lib/insightsApi";
import { useI18n } from "@/lib/i18n";
import {
  DRAWDOWN_REACTIONS,
  EMPTY_PROFILE_ANSWERS,
  EXPERIENCES,
  FIRE_INTERESTS,
  GOALS,
  HOUSEHOLDS,
  LOSS_TOLERANCES,
  STABILITY_FEELS,
} from "@/lib/insightsTypes";
import type {
  DrawdownReaction,
  Experience,
  FireInterest,
  Goal,
  Household,
  Insight,
  LossTolerancePct,
  ProfileAnswers,
  ProfileData,
  StabilityFeel,
  SuggestedStyle,
} from "@/lib/insightsTypes";
import Markdown from "@/components/Markdown";

const POLL_MS = 3000;
const PENDING: Insight["status"][] = ["pending", "running", "translating"];

const STYLE_LABEL_KEY: Record<SuggestedStyle, string> = {
  safe: "rep.style.safe",
  balanced: "rep.style.balanced",
  risky: "rep.style.risky",
  long_term: "rep.style.longTerm",
};

interface Props {
  status: { configured: boolean } | null;
  onUseStyle: (style: SuggestedStyle) => void;
}

export default function ProfileTab({ status, onUseStyle }: Props) {
  const { t, lang } = useI18n();
  const [answers, setAnswers] = useState<ProfileAnswers>(EMPTY_PROFILE_ANSWERS);
  const [insight, setInsight] = useState<Insight | null>(null);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [styleApplied, setStyleApplied] = useState(false);
  const pollId = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const a = await insightsApi.getAnswers();
        if (alive) setAnswers({ ...EMPTY_PROFILE_ANSWERS, ...a });
      } catch (e) {
        if (!isNotFound(e) && alive) {
          setError(e instanceof Error ? e.message : t("common.failedLoad"));
        }
      }
      try {
        const latest = await insightsApi.latest("profile", lang);
        if (alive) setInsight(latest);
      } catch (e) {
        if (!isNotFound(e) && alive) {
          setError(e instanceof Error ? e.message : t("common.failedLoad"));
        }
      }
      if (alive) setLoaded(true);
    }
    load();
    return () => {
      alive = false;
    };
  }, [lang, t]);

  const stopPolling = useCallback(() => {
    if (pollId.current) {
      clearInterval(pollId.current);
      pollId.current = null;
    }
  }, []);
  useEffect(() => stopPolling, [stopPolling]);

  const watch = useCallback(
    (id: number) => {
      stopPolling();
      pollId.current = setInterval(async () => {
        try {
          const next = await insightsApi.item(id);
          setInsight(next);
          if (!PENDING.includes(next.status)) {
            stopPolling();
            setBusy(false);
          }
        } catch (e) {
          stopPolling();
          setBusy(false);
          setError(e instanceof Error ? e.message : t("common.failedLoad"));
        }
      }, POLL_MS);
    },
    [stopPolling, t],
  );

  function toggleGoal(goal: Goal) {
    setAnswers((a) => ({
      ...a,
      goals: a.goals.includes(goal)
        ? a.goals.filter((g) => g !== goal)
        : [...a.goals, goal],
    }));
  }

  async function submit() {
    setBusy(true);
    setError(null);
    setStyleApplied(false);
    try {
      await insightsApi.saveAnswers(answers);
      const queued = await insightsApi.create("profile", lang);
      setInsight(queued);
      watch(queued.id);
    } catch (e) {
      setBusy(false);
      setError(e instanceof Error ? e.message : t("common.failedSave"));
    }
  }

  const pending = insight != null && PENDING.includes(insight.status);
  const unavailable = status != null && !status.configured;
  const data =
    insight?.status === "done" && insight.data
      ? (insight.data as unknown as ProfileData)
      : null;

  return (
    <div className="space-y-6">
      <div className="card space-y-5">
        <div>
          <span className="label">{t("ins.profile.goals")}</span>
          <div className="mt-1 grid gap-2 sm:grid-cols-2">
            {GOALS.map((g) => (
              <label key={g} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={answers.goals.includes(g)}
                  onChange={() => toggleGoal(g)}
                  disabled={busy || pending}
                />
                {t(`ins.profile.goal.${g}`)}
              </label>
            ))}
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="ins-horizon">
              {t("ins.profile.horizon")}
            </label>
            <input
              id="ins-horizon"
              type="number"
              min="0"
              className="input"
              value={answers.horizon_years ?? ""}
              onChange={(e) =>
                setAnswers((a) => ({
                  ...a,
                  horizon_years: e.target.value === "" ? null : Number(e.target.value),
                }))
              }
              disabled={busy || pending}
            />
          </div>
          <div>
            <label className="label" htmlFor="ins-dependents">
              {t("ins.profile.dependents")}
            </label>
            <input
              id="ins-dependents"
              type="number"
              min="0"
              className="input"
              value={answers.dependents ?? ""}
              onChange={(e) =>
                setAnswers((a) => ({
                  ...a,
                  dependents: e.target.value === "" ? null : Number(e.target.value),
                }))
              }
              disabled={busy || pending}
            />
          </div>
          <div>
            <label className="label" htmlFor="ins-household">
              {t("ins.profile.household")}
            </label>
            <select
              id="ins-household"
              className="input"
              value={answers.household ?? ""}
              onChange={(e) =>
                setAnswers((a) => ({
                  ...a,
                  household: (e.target.value || null) as Household | null,
                }))
              }
              disabled={busy || pending}
            >
              <option value="" disabled>
                {"—"}
              </option>
              {HOUSEHOLDS.map((h) => (
                <option key={h} value={h}>
                  {t(`ins.profile.household.${h}`)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="ins-stability">
              {t("ins.profile.incomeStability")}
            </label>
            <select
              id="ins-stability"
              className="input"
              value={answers.income_stability_feel ?? ""}
              onChange={(e) =>
                setAnswers((a) => ({
                  ...a,
                  income_stability_feel: (e.target.value || null) as StabilityFeel | null,
                }))
              }
              disabled={busy || pending}
            >
              <option value="" disabled>
                {"—"}
              </option>
              {STABILITY_FEELS.map((s) => (
                <option key={s} value={s}>
                  {t(`ins.profile.level.${s}`)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="ins-drawdown">
              {t("ins.profile.drawdown")}
            </label>
            <select
              id="ins-drawdown"
              className="input"
              value={answers.drawdown_reaction ?? ""}
              onChange={(e) =>
                setAnswers((a) => ({
                  ...a,
                  drawdown_reaction: (e.target.value || null) as DrawdownReaction | null,
                }))
              }
              disabled={busy || pending}
            >
              <option value="" disabled>
                {"—"}
              </option>
              {DRAWDOWN_REACTIONS.map((d) => (
                <option key={d} value={d}>
                  {t(`ins.profile.drawdown.${d}`)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="ins-loss-tolerance">
              {t("ins.profile.lossTolerance")}
            </label>
            <select
              id="ins-loss-tolerance"
              className="input"
              value={answers.loss_tolerance_pct ?? ""}
              onChange={(e) =>
                setAnswers((a) => ({
                  ...a,
                  loss_tolerance_pct: e.target.value
                    ? (Number(e.target.value) as LossTolerancePct)
                    : null,
                }))
              }
              disabled={busy || pending}
            >
              <option value="" disabled>
                {"—"}
              </option>
              {LOSS_TOLERANCES.map((p) => (
                <option key={p} value={p}>
                  {p}%
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="ins-fire-interest">
              {t("ins.profile.fireInterest")}
            </label>
            <select
              id="ins-fire-interest"
              className="input"
              value={answers.fire_interest ?? ""}
              onChange={(e) =>
                setAnswers((a) => ({
                  ...a,
                  fire_interest: (e.target.value || null) as FireInterest | null,
                }))
              }
              disabled={busy || pending}
            >
              <option value="" disabled>
                {"—"}
              </option>
              {FIRE_INTERESTS.map((f) => (
                <option key={f} value={f}>
                  {t(`ins.profile.fire.${f}`)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="ins-experience">
              {t("ins.profile.experience")}
            </label>
            <select
              id="ins-experience"
              className="input"
              value={answers.experience ?? ""}
              onChange={(e) =>
                setAnswers((a) => ({
                  ...a,
                  experience: (e.target.value || null) as Experience | null,
                }))
              }
              disabled={busy || pending}
            >
              <option value="" disabled>
                {"—"}
              </option>
              {EXPERIENCES.map((ex) => (
                <option key={ex} value={ex}>
                  {t(`ins.profile.exp.${ex}`)}
                </option>
              ))}
            </select>
          </div>
        </div>

        {error && <div className="banner-error">{error}</div>}
        {status?.configured === false && (
          <p className="text-sm banner-error">{t("rep.unavailable")}</p>
        )}

        <button
          onClick={submit}
          className="btn-primary"
          disabled={busy || pending || !loaded || unavailable}
        >
          {busy || pending ? t("ins.profile.saving") : t("ins.profile.save")}
        </button>
      </div>

      {pending && (
        <div className="card flex items-center gap-3">
          <span
            className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-brand-600 dark:border-slate-600 dark:border-t-brand-400"
            aria-hidden
          />
          <p className="text-sm muted">
            {insight?.status === "translating"
              ? t("ins.job.translating")
              : insight?.status === "running"
                ? t("ins.job.running")
                : t("ins.job.queued")}
          </p>
        </div>
      )}

      {insight?.status === "failed" && (
        <div className="card space-y-2">
          <p className="text-sm font-medium text-red-600">{t("ins.job.failed")}</p>
          <p className="text-xs muted">{insight.error}</p>
        </div>
      )}

      {!pending && data ? (
        <div className="card space-y-4">
          <div className="flex flex-wrap gap-2">
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium dark:bg-slate-800">
              {t("ins.profile.stated")}: {t(`ins.profile.level.${data.stated_tolerance}`)}
            </span>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium dark:bg-slate-800">
              {t("ins.profile.capacity")}: {t(`ins.profile.level.${data.capacity}`)}
            </span>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium dark:bg-slate-800">
              {t("ins.profile.revealed")}: {t(`ins.profile.level.${data.revealed}`)}
            </span>
          </div>

          <div>
            <h3 className="text-sm font-semibold">{t("ins.profile.summary")}</h3>
            <Markdown text={data.summary_md} />
          </div>

          <div>
            <h3 className="text-sm font-semibold">{t("ins.profile.mismatches")}</h3>
            {data.mismatches.length === 0 ? (
              <p className="text-sm muted">{t("ins.profile.noMismatches")}</p>
            ) : (
              <ul className="mt-2 space-y-2">
                {data.mismatches.map((m, i) => (
                  <li
                    key={i}
                    className="rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-800"
                  >
                    <p className="font-medium">{m.about}</p>
                    <p className="muted">
                      {m.stated} vs. {m.actual}
                    </p>
                    <p className="mt-1 text-xs subtle">{m.why_it_matters}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {data.priorities.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold">{t("ins.profile.priorities")}</h3>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm muted">
                {data.priorities.map((p, i) => (
                  <li key={i}>{p}</li>
                ))}
              </ul>
            </div>
          )}

          <button
            onClick={() => {
              onUseStyle(data.suggested_style);
              setStyleApplied(true);
            }}
            className="btn-ghost text-sm"
          >
            {t("ins.profile.useStyle", {
              style: t(STYLE_LABEL_KEY[data.suggested_style]),
            })}
          </button>
          {styleApplied && (
            <p className="text-xs subtle">{t("ins.profile.useStyleDone")}</p>
          )}
        </div>
      ) : (
        !pending &&
        insight?.status !== "failed" && (
          <div className="card grid h-24 place-items-center text-sm subtle">
            {t("ins.profile.empty")}
          </div>
        )
      )}
    </div>
  );
}
