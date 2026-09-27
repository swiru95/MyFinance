import { useCallback, useEffect, useState } from "react";
import { incomeApi } from "@/lib/incomeApi";
import { useI18n } from "@/lib/i18n";
import type { IncomeSource, IncomeSummary } from "@/lib/incomeTypes";
import SourceCard from "@/components/income/SourceCard";
import SourceForm from "@/components/income/SourceForm";
import YearSchedule from "@/components/income/YearSchedule";
import TaxEnvelope from "@/components/income/TaxEnvelope";
import YearOverviewChart from "@/components/income/YearOverviewChart";
import OtherIncomeCard from "@/components/income/OtherIncomeCard";

export default function IncomePage() {
  const { t } = useI18n();
  const [sources, setSources] = useState<IncomeSource[]>([]);
  const [summary, setSummary] = useState<IncomeSummary | null>(null);
  const [year, setYear] = useState(new Date().getFullYear());
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<IncomeSource | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const [list, sum] = await Promise.all([incomeApi.sources(), incomeApi.summary(year)]);
      setSources(list);
      setSummary(sum);
      setError(null);
      setSelectedId((prev) =>
        prev != null && list.some((s) => s.id === prev) ? prev : (list[0]?.id ?? null)
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failedLoad"));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const base = summary?.base_currency ?? "PLN";
  const hasB2b = sources.some((s) => s.kind === "b2b");

  function openNew() {
    setEditing(null);
    setFormOpen(true);
  }

  function openEdit(source: IncomeSource) {
    setEditing(source);
    setFormOpen(true);
  }

  async function remove(source: IncomeSource) {
    if (!confirm(t("inc.confirmDelete", { name: source.name }))) return;
    try {
      await incomeApi.deleteSource(source.id);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failedDelete"));
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{t("inc.title")}</h1>
          <p className="text-sm muted">{t("inc.subtitle")}</p>
        </div>
        <button onClick={openNew} className="btn-primary">{t("inc.addSource")}</button>
      </div>

      {error && <div className="banner-error">{error}</div>}

      {loading ? (
        <p className="text-sm subtle">{t("common.loading")}</p>
      ) : sources.length === 0 ? (
        <div className="card grid h-40 place-items-center text-sm subtle">{t("inc.empty")}</div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {sources.map((s) => (
            <SourceCard
              key={s.id}
              source={s}
              base={base}
              onEdit={() => openEdit(s)}
              onDelete={() => remove(s)}
            />
          ))}
        </div>
      )}

      {sources.length > 0 && (
        <YearSchedule
          sources={sources}
          base={base}
          selectedId={selectedId}
          onSelect={setSelectedId}
          year={year}
          onYear={setYear}
          onChanged={refresh}
        />
      )}

      {hasB2b && summary && <TaxEnvelope summary={summary} />}

      {summary && (
        <div className="card">
          <h2 className="text-lg font-semibold">{t("inc.chart.title")}</h2>
          <p className="mb-3 text-sm muted">{t("inc.chart.subtitle")}</p>
          <YearOverviewChart months={summary.months} currency={base} />
        </div>
      )}

      <OtherIncomeCard base={base} />

      {formOpen && (
        <div className="fixed inset-0 z-20 grid place-items-center overflow-y-auto bg-black/40 p-4">
          <div className="card my-8 w-full max-w-md">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold">
                {editing ? t("inc.form.editTitle") : t("inc.form.newTitle")}
              </h2>
              <button onClick={() => setFormOpen(false)} className="subtle">✕</button>
            </div>
            <SourceForm
              base={base}
              existing={editing}
              onDone={() => {
                setFormOpen(false);
                setEditing(null);
                refresh();
              }}
              onCancel={() => {
                setFormOpen(false);
                setEditing(null);
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
