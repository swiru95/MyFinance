import { useI18n } from "@/lib/i18n";

/** Every response with tax figures carries `disclaimer_key: "tax.disclaimer"`
 *  (tax/pl is estimates for planning, not tax advice) - this renders it
 *  under a block of tax figures, per 00-architecture.md and the WP spec. */
export default function TaxDisclaimer({ year }: { year: number }) {
  const { t } = useI18n();
  return <p className="text-xs subtle">{t("tax.disclaimer", { year })}</p>;
}
