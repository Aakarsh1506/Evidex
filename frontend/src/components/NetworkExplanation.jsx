import { useEffect, useRef, useState } from "react";
import { useTranslation } from "../i18n";
import formatInsight from "../utils/formatInsight";

export default function NetworkExplanation({ id, selection, onClear }) {
  const { t } = useTranslation();
  const [explanation, setExplanation] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const request = useRef(null);

  useEffect(() => () => request.current?.abort(), []);

  async function explain() {
    if (!selection || request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`/api/criminals/${encodeURIComponent(id)}/explain`, {
        method: "POST", signal: controller.signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ selection: { type: selection.type, id: selection.id } }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || t("insightFailed"));
      if (typeof data.explanation !== "string" || !data.explanation.trim()) throw new Error(t("insightEmpty"));
      if (!controller.signal.aborted) setExplanation(data.explanation);
    } catch (err) {
      if (!controller.signal.aborted) setError(
        err instanceof SyntaxError || err instanceof TypeError
          ? t("backendUnreachable")
          : err.message
      );
    } finally {
      request.current = null;
      if (!controller.signal.aborted) setLoading(false);
    }
  }

  return (
    <section className="network-ai" aria-labelledby="network-ai-title" aria-busy={loading}>
      <h3 id="network-ai-title">{t("aiInsight")}</h3>
      <p>{selection ? `Selected: ${selection.label}` : t("insightSelectFirst")}</p>
      {selection && <p>{t("insightIntro")}</p>}
      <button className="stamp-btn small" onClick={explain} disabled={!selection || loading}>
        {loading ? t("insightGenerating") : explanation ? t("insightRegenerate") : t("aiInsight")}
      </button>
      {selection && <button className="stamp-btn small" type="button" onClick={onClear}>{t("clearSelection")}</button>}
      {loading && <p role="status">{t("insightReading")}</p>}
      {error && <p className="network-ai-error" role="alert">{error}</p>}
      {explanation && <div className="network-ai-answer" aria-live="polite">{formatInsight(explanation)}</div>}

    </section>
  );
}
