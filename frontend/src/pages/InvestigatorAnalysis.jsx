import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import RelationGraph from "../components/RelationGraph";
import BackButton from "../components/BackButton";
import { fetchAllCases, fetchCaseNetwork } from "../api/cases";
import { mergeNetworks, readWorkspace, saveWorkspace, searchRecords } from "../utils/investigatorWorkspace";
import { useTranslation } from "../i18n";
import formatInsight from "../utils/formatInsight";
import "./InvestigatorAnalysis.css";

export default function InvestigatorAnalysis() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [cases, setCases] = useState([]);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogRetry, setCatalogRetry] = useState(0);
  const [catalogError, setCatalogError] = useState(false);
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const [entries, setEntries] = useState([]);
  const [adding, setAdding] = useState(null);
  const [graphError, setGraphError] = useState("");
  const [selection, setSelection] = useState(null);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState(() => readWorkspace().messages);
  const [loading, setLoading] = useState(false);
  const [phase, setPhase] = useState("analysisThinking");
  const request = useRef(null);
  const graphRequest = useRef(null);
  const legacyLoaded = useRef(null);
  const restored = useRef(false);
  const messagesRef = useRef(null);
  const inputRef = useRef(null);
  const results = useMemo(() => searchRecords(cases, query, ["reference", "title", "id"]), [cases, query]);
  const network = useMemo(() => mergeNetworks(entries), [entries]);

  useEffect(() => {
    let active = true;
    fetchAllCases().then((data) => { if (active) setCases(data); })
      .catch(() => { if (active) setCatalogError(true); })
      .finally(() => { if (active) setCatalogLoading(false); });
    return () => { active = false; };
  }, [catalogRetry]);

  useEffect(() => () => { request.current?.abort(); graphRequest.current?.abort(); }, []);

  // Restore the cases added earlier in this browser session, then keep the session in step.
  useEffect(() => {
    if (restored.current) return;
    restored.current = true;
    void (async () => {
      for (const record of readWorkspace().records) await addCase(record);
    })();
    // Restoring runs once per mount; addCase is stable enough for this one-shot replay.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    saveWorkspace(entries.map((entry) => entry.record), messages);
  }, [entries, messages]);
  useEffect(() => {
    const panel = messagesRef.current;
    if (panel) panel.scrollTop = panel.scrollHeight;
  }, [messages, loading]);

  async function addCase(record) {
    if (graphRequest.current || entries.some((entry) => entry.record.id === record.id)) return;
    const controller = new AbortController();
    graphRequest.current = controller;
    setAdding(record.id); setGraphError("");
    try {
      const graph = await fetchCaseNetwork(record.id, { signal: controller.signal });
      if (controller.signal.aborted) return;
      setEntries((current) => [...current, { record, network: graph }]);
      setSelection(null); setQuery(""); setSearchOpen(false);
    } catch (error) {
      if (!controller.signal.aborted) setGraphError(error.message);
    } finally {
      if (graphRequest.current === controller) graphRequest.current = null;
      if (!controller.signal.aborted) setAdding(null);
    }
  }

  useEffect(() => {
    // Wait for a restore or another add to finish; this effect runs again on the next render.
    if (!id || !cases.length || graphRequest.current || legacyLoaded.current === id) return;
    legacyLoaded.current = id;
    const record = cases.find((item) => String(item.id) === id);
    if (record) void addCase(record);
  });

  async function ask(event) {
    event?.preventDefault();
    const text = question.trim();
    // Without a selection the question is answered from the whole workspace network.
    if (!text || request.current || (!selection && !entries.length)) return;
    const target = selection ? { ...selection }
      : { recordId: entries[0].record.id, label: t("analysisWholeNetwork"), whole: true };
    const contextKey = JSON.stringify([target.recordId, target.type ?? "network", target.id ?? entries.length]);
    const history = messages.filter((message) => message.contextKey === contextKey
      && ["user", "assistant"].includes(message.role)).slice(-6)
      .map((message) => ({ role: message.role, content: message.text.slice(0, 4000) }));
    const controller = new AbortController();
    request.current = controller;
    setQuestion(""); setLoading(true); setPhase("analysisThinking");
    const timer = window.setTimeout(() => setPhase("analysisReviewing"), 1600);
    setMessages((current) => [...current, { role: "user", text, context: target.label, contextKey }]);
    try {
      const response = await fetch(`/api/cases/${encodeURIComponent(target.recordId)}/explain`, {
        method: "POST", signal: controller.signal, headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          selection: target.whole ? null : { type: target.type, id: target.id },
          question: text, history,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || t("analysisFailed"));
      if (typeof data.explanation !== "string" || !data.explanation.trim()) throw new Error(t("analysisFailed"));
      if (!controller.signal.aborted) setMessages((current) => [...current, { role: "assistant", text: data.explanation, contextKey }]);
    } catch (error) {
      if (!controller.signal.aborted) setMessages((current) => [...current, { role: "error", text: error.message, retryQuestion: text, target }]);
    } finally {
      window.clearTimeout(timer);
      if (request.current === controller) request.current = null;
      if (!controller.signal.aborted) { setLoading(false); inputRef.current?.focus(); }
    }
  }

  return <main className="analysis-page">
    <BackButton />
    <header className="analysis-header"><p className="form-number">{t("investigatorWorkspace")}</p><h1>{t("investigatorAnalysis")}</h1><p>{t("analysisIntro")}</p></header>
    <section className="analysis-search" aria-label={t("analysisFind")}>
      <label htmlFor="analysis-search-input">{t("analysisFind")}</label>
      <div className="analysis-search-row">
        <input id="analysis-search-input" role="combobox" aria-expanded={searchOpen && !!query.trim()} aria-controls="analysis-results" aria-autocomplete="list" aria-activedescendant={searchOpen && results[highlight] ? `analysis-result-${highlight}` : undefined}
          autoComplete="off" placeholder={t("analysisSearchHint")} value={query} disabled={catalogLoading || catalogError}
          onFocus={() => setSearchOpen(true)} onBlur={() => setSearchOpen(false)}
          onChange={(event) => { setQuery(event.target.value.slice(0, 100)); setHighlight(0); setSearchOpen(true); }}
          onKeyDown={(event) => {
            if (event.key === "Escape") setSearchOpen(false);
            if (event.key === "ArrowDown" || event.key === "ArrowUp") {
              event.preventDefault(); setSearchOpen(true);
              setHighlight((current) => Math.max(0, Math.min(results.length - 1, current + (event.key === "ArrowDown" ? 1 : -1))));
            }
            if (event.key === "Enter" && searchOpen && results[highlight]) { event.preventDefault(); void addCase(results[highlight]); }
          }} />
        {catalogLoading && <span role="status">{t("loadingRecords")}</span>}
        {adding && <span role="status">{t("analysisAdding")}</span>}
      </div>
      {searchOpen && !!query.trim() && <ul className="analysis-results" id="analysis-results" role="listbox" aria-label={t("analysisFind")}>
        {results.map((record, index) => {
          const added = entries.some((entry) => entry.record.id === record.id);
          return <li id={`analysis-result-${index}`} key={record.id} role="option" aria-selected={highlight === index} aria-disabled={added || !!adding}
            onMouseDown={(event) => event.preventDefault()} onMouseEnter={() => setHighlight(index)} onClick={() => void addCase(record)}>
            <span><strong>{record.reference}</strong><small>{[record.title, record.crime, record.location?.city].filter(Boolean).join(" · ")}</small></span><span>{added ? t("analysisAdded") : t("analysisAdd")}</span>
          </li>;
        })}
        {!results.length && <li role="option" aria-disabled="true" aria-selected="false">{t("noSearchMatches")}</li>}
      </ul>}
      {catalogError && <p role="alert">{t("analysisCatalogError")} <button type="button" onClick={() => { setCatalogError(false); setCatalogLoading(true); setCatalogRetry((value) => value + 1); }}>{t("retry")}</button></p>}
      {graphError && <p className="analysis-error" role="alert">{t("analysisGraphError")} {graphError}</p>}
    </section>
    <div className="analysis-layout">
      <section className="analysis-connections" aria-label={t("connections")}>
        <div className="analysis-panel-heading"><h2>{t("connections")}</h2><span>{network.nodes.length} {t("analysisNodes")} · {network.edges.length} {t("analysisLinks")}</span></div>
        <div className="analysis-people">{entries.map(({ record }) => <span className="analysis-person" key={record.id}>{record.reference}<button type="button" aria-label={`${t("analysisRemove")} ${record.reference}`} onClick={() => { setEntries((current) => current.filter((entry) => entry.record.id !== record.id)); setSelection(null); }}>×</button></span>)}</div>
        {entries.length ? <RelationGraph key={entries.map((entry) => entry.record.id).join(":")} mainCriminal={{ id: "workspace", name: t("investigatorWorkspace") }} network={network} onSelectionChange={setSelection} onNodeClick={(caseId) => navigate(`/case/${encodeURIComponent(caseId)}`)} height={480} />
          : <div className="analysis-empty-workspace">
            <svg className="analysis-empty-icon" aria-hidden="true" viewBox="0 0 96 96" width="64" height="64" fill="none">
              <line x1="48" y1="18" x2="24" y2="62" stroke="var(--accent-dim)" strokeWidth="2" />
              <line x1="48" y1="18" x2="72" y2="62" stroke="var(--accent-dim)" strokeWidth="2" />
              <line x1="24" y1="62" x2="72" y2="62" stroke="var(--accent-dim)" strokeWidth="2" />
              <circle cx="48" cy="18" r="9" stroke="var(--btn)" strokeWidth="3" />
              <circle cx="24" cy="62" r="7" stroke="var(--accent-dim)" strokeWidth="3" />
              <circle cx="72" cy="62" r="7" stroke="var(--accent-dim)" strokeWidth="3" />
            </svg>
            <h3>{t("analysisStart")}</h3>
            <p>{t("analysisStartHint")}</p>
          </div>}
      </section>
      <section className="analysis-chat" aria-label={t("aiInvestigator")}>
        <div className="analysis-panel-heading"><h2>{t("aiInvestigator")}</h2><button type="button" disabled={loading || !messages.length} onClick={() => setMessages([])}>{t("analysisClearChat")}</button></div>
        <p className="analysis-selected">{selection
          ? `${t("analysisSelected")}: ${selection.label}`
          : entries.length ? t("analysisWholeNetworkHint") : t("analysisSelect")}</p>
        <div ref={messagesRef} className="analysis-messages" role="log" aria-live="polite" aria-label={t("analysisMessages")} tabIndex={0}>
          {!messages.length && <div className="analysis-empty"><h3>{t("analysisChatWelcome")}</h3><p>{t("analysisChatHint")}</p>{["analysisPrompt1", "analysisPrompt2"].map((key) => <button className="analysis-prompt" key={key} disabled={!selection && !entries.length} onClick={() => { setQuestion(t(key)); inputRef.current?.focus(); }}>{t(key)}</button>)}</div>}
          {messages.map((message, index) => <article key={index} className={`analysis-message ${message.role}`}><strong>{message.role === "user" ? t("analysisYou") : t("aiInvestigator")}</strong>{message.context && <small>{message.context}</small>}{message.role === "assistant" ? <div className="analysis-answer">{formatInsight(message.text)}</div> : <p>{message.text}</p>}{message.retryQuestion && <button disabled={loading} onClick={() => { const present = message.target.id && network.nodes.concat(network.edges).find((item) => item.id === message.target.id); if (present) setSelection({ ...message.target, recordId: present.originRecordId }); setQuestion(message.retryQuestion); inputRef.current?.focus(); }}>{t("analysisRetryQuestion")}</button>}</article>)}
          {loading && <p className="analysis-thinking" role="status"><span aria-hidden="true">•••</span> {t(phase)}</p>}
        </div>
        <form className="analysis-form" onSubmit={ask}>
          <label className="analysis-compose-label" htmlFor="analysis-question">{t("analysisQuestion")}</label>
          <textarea ref={inputRef} id="analysis-question" value={question} maxLength={2000} rows={3} disabled={!selection && !entries.length} onChange={(event) => setQuestion(event.target.value)} placeholder={t(selection || entries.length ? "analysisQuestionHint" : "analysisSelect")}
            onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void ask(); } }} />
          <div className="analysis-compose-footer"><small>{t("analysisEnterHint")}</small><button className="stamp-btn" disabled={(!selection && !entries.length) || !question.trim() || loading}>{loading ? t("analysisReviewing") : t("askAI")}</button></div>
        </form>
      </section>
    </div>
  </main>;
}