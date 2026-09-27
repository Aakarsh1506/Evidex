import { useTranslation } from "../i18n";
import "./CaseSummary.css";

// Every summary item cites supplied source IDs; the citations are rendered as the
// documents and passages they came from, so a reader can check the claim at source.
export default function CaseSummary({ summary, generating, error, onGenerate, onOpenSource }) {
  const { t } = useTranslation();
  const sources = Object.fromEntries((summary?.sources || []).map((s) => [s.id, s]));

  return (
    <section className="case-summary" aria-label={t("caseSummaryTitle")}>
      <div className="case-summary-head">
        <div>
          <h3>{t("caseSummaryTitle")}</h3>
          <p className="case-summary-note">{t("caseSummaryNote")}</p>
        </div>
        <button type="button" className="stamp-btn small" disabled={generating} onClick={onGenerate}>
          {generating
            ? t("caseSummaryGenerating")
            : t(summary ? "caseSummaryRegenerate" : "caseSummaryGenerate")}
        </button>
      </div>

      {generating && <p className="case-summary-working" role="status">{t("caseSummaryWorking")}</p>}
      {error && <p className="case-summary-error" role="alert">{error}</p>}

      {!summary && !generating && !error && (
        <p className="empty-note">{t("caseSummaryEmpty")}</p>
      )}

      {summary && (
        <>
          <p className="case-summary-meta">
            {summary.generatedBy ? `${t("caseSummaryBy")} ${summary.generatedBy}` : null}
            {summary.generatedAt ? ` · ${new Date(summary.generatedAt).toLocaleString()}` : null}
            {summary.coverage?.documents != null
              ? ` · ${summary.coverage.documents} ${t("caseDocumentCount")}`
              : null}
          </p>
          <p className="case-summary-verify">{t("caseSummaryVerify")}</p>

          {summary.sections.map((section) => (
            <div className="case-summary-section" key={section.category}>
              <h4>{t(`caseSummary_${section.category}`)}</h4>
              <ul>
                {section.items.map((item, index) => (
                  <li key={index}>
                    {item.text}
                    <span className="case-summary-cites">
                      {item.sources.map((sourceId) => {
                        const source = sources[sourceId];
                        if (!source) return null;
                        // Citations open the stored original in place rather than
                        // navigating away, which also avoids the browser refusing to
                        // display or download formats it does not recognise.
                        return source.documentId && onOpenSource ? (
                          <button key={sourceId} type="button" className="case-summary-cite"
                            title={source.quote || source.label}
                            onClick={() => onOpenSource(source.documentId)}>
                            {source.label}
                          </button>
                        ) : (
                          <em key={sourceId}>{source.label}</em>
                        );
                      })}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </>
      )}
    </section>
  );
}
