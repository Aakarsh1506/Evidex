import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import DocumentActions from "../components/DocumentActions";
import IdentityReviewDialog from "../components/IdentityReviewDialog";
import DocumentProgress from "../components/DocumentProgress";
import { confirmDocument, fetchDocument, documentFileUrl, fetchIdentitySuggestions } from "../api/documents";
import { useTranslation } from "../i18n";
import { parseImportedRows } from "../utils/importedRows";
import "./CriminalProfile.css";
import "./DocumentReview.css";

const STATUS = {
  stored: "revStored", queued: "revQueued", processing: "revProcessing",
  awaiting_review: "revAwaiting", syncing: "revSyncing", complete: "revComplete",
  failed: "revFailed", sync_failed: "revSyncFailed", cancelled: "revCancelled",
};
const PENDING = new Set(["queued", "processing", "syncing"]);
const label = (value) => value.replaceAll("_", " ");

export default function DocumentReview() {
  const { t } = useTranslation();
  const { id } = useParams();
  const navigate = useNavigate();
  const [document, setDocument] = useState(null);
  const [error, setError] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const [identityReview, setIdentityReview] = useState(null);
  const [reload, setReload] = useState(0);
  const [selection, setSelection] = useState({ key: null, entities: {}, relationships: {} });
  const snapshot = JSON.stringify(document?.extraction || null);
  const selectionKey = `${id}:${snapshot}`;
  const choices = selection.key === selectionKey ? selection : { entities: {}, relationships: {} };
  const rejectedEntities = new Set(Object.keys(choices.entities).filter((key) => choices.entities[key] === false).map(Number));

  useEffect(() => {
    let active = true;
    let timer;
    async function refresh() {
      try {
        const next = await fetchDocument(id);
        if (!active) return;
        setDocument(next); setError(null);
        if (PENDING.has(next.status)) timer = setTimeout(refresh, 3000);
      } catch (err) { if (active) setError(err.message); }
    }
    refresh();
    return () => { active = false; clearTimeout(timer); };
  }, [id, reload]);

  async function confirm(personMatches = null) {
    if (!document || confirming || remaining > 0 || document.status !== "awaiting_review") return;
    setConfirming(true); setError(null);
    try {
      if (personMatches === null) {
        const result = await fetchIdentitySuggestions(document.id, document.extraction, [...rejected], [...rejectedEntities]);
        if (result.suggestions.length) {
          setIdentityReview({ key: selectionKey, suggestions: result.suggestions });
          return;
        }
      }
      const updated = await confirmDocument(document.id, document.extraction, [...rejected], [...rejectedEntities], personMatches || {});
      setIdentityReview(null);
      setDocument((current) => ({ ...current, ...updated }));
      setReload((value) => value + 1);
    } catch (err) { setError(err.message); }
    finally { setConfirming(false); }
  }

  const importedTables = useMemo(
    () => (document?.sourceType === "database" ? parseImportedRows(document.text) : []),
    [document]);
  const entities = document?.extraction?.entities || [];
  const relationships = document?.extraction?.relationships || [];
  const excluded = document?.extraction?.excluded_relationships || [];
  const excludedEntities = document?.extraction?.excluded_entities || [];
  const byRef = Object.fromEntries([...entities, ...excludedEntities].map((entity, index) => [entity.ref, { ...entity, index }]));
  const rejectedRefs = new Set(entities.filter((_, index) => rejectedEntities.has(index)).map((entity) => entity.ref));
  const endpointRejected = (relation) => rejectedRefs.has(relation.subject) || rejectedRefs.has(relation.object);
  const rejected = new Set(relationships.flatMap((relation, index) =>
    choices.relationships[index] === false || endpointRejected(relation) ? [index] : []));
  // Every extracted assertion starts selected for saving; reviewers can choose No.
  const remaining = 0;
  const acceptedEntityCount = entities.filter((_, index) => choices.entities[index] !== false).length;
  const acceptedRelationshipCount = relationships.filter((relation, index) =>
    choices.relationships[index] !== false && !endpointRejected(relation)).length;
  const reviewing = document?.status === "awaiting_review";
  const link = (ref) => byRef[ref] ? <a href={`#review-entity-${byRef[ref].index}`}>{byRef[ref].name}</a> : <span>{ref}</span>;
  function choose(kind, index, value) {
    setSelection((current) => {
      const next = current.key === selectionKey ? current : { entities: {}, relationships: {} };
      return { ...next, key: selectionKey, [kind]: { ...next[kind], [index]: value } };
    });
  }
  const reviewControl = (index, kind = "relationships") => {
    const blocked = kind === "relationships" && endpointRejected(relationships[index]);
    const value = blocked ? false : choices[kind][index] ?? true;
    return reviewing && <div className="review-relation-actions" role="group"
      aria-label={`Review ${kind === "entities" ? "entity" : "relationship"} ${index + 1}`}>
      <span>{t(kind === "entities" ? "revKeepEntity" : "revKeepRelationship")}</span>
      {[true, false].map((answer) => <button key={String(answer)} type="button"
        disabled={confirming || blocked} aria-pressed={value === answer}
        onClick={() => choose(kind, index, answer)}>{t(answer ? "revYes" : "revNo")}</button>)}
      <span>{t(blocked ? "revBlocked" : value === undefined ? "revChoose" : value ? "revWillSave" : "revWontSave")}</span>
    </div>;
  };

  return <main className="dossier-page document-review">
    {identityReview?.key === selectionKey && reviewing && <IdentityReviewDialog
      suggestions={identityReview.suggestions} busy={confirming} error={error}
      onConfirm={confirm} onClose={() => { setIdentityReview(null); setError(null); }} />}

    <header className="review-heading">
      <Link to="/upload" className="review-back">← Back to documents</Link>
      <p className="form-number">{t("revTitle")}</p>
      <h1>{document?.name || t("revLoadingDocument")}</h1>
      <p role="status">{document ? t(STATUS[document.status]) : t("revLoadingExtraction")}</p>
      <DocumentProgress document={document} />
      {error && <p role="alert" className="review-error">{error} <button onClick={() => setReload((value) => value + 1)}>{t("revReload")}</button></p>}
      {document?.processingError && <p role="alert" className="review-error">{document.processingError}</p>}
      {document && <DocumentActions document={document} disabled={confirming}
        onError={setError} onRemoved={() => navigate("/upload")}
        onUpdated={(updated) => {
          setDocument((current) => ({ ...current, ...updated }));
          setError(null); setReload((value) => value + 1);
        }} />}
      {reviewing && <p>{t("revInstructions")}</p>}
      {excluded.length > 0 && <p className="review-error">{excluded.length} {t("revExcludedNote")}</p>}
      {document?.confirmedAt && <p>{t("revConfirmedOn")} {new Date(document.confirmedAt).toLocaleString()}.</p>}
    </header>

    {document?.extraction ? <div className="review-layout">
      <aside className="dossier-sheet review-index">
        <h2>{t("revExtractedRecords")}</h2>
        <p>{entities.length} entities · {relationships.length} relationships</p>
        <nav aria-label={t("revExtractedRecords")} className="no-scrollbar" tabIndex={0}>
          {entities.map((entity, index) => <a key={entity.ref} href={`#review-entity-${index}`}>
            <span>{entity.name}</span><small>{entity.kind}</small>
          </a>)}
          <a href="#review-relationships">{t("revAllRelationships")} <small>{relationships.length}</small></a>
          {excluded.length > 0 && <a href="#review-excluded">{t("revExcludedRelationships")} <small>{excluded.length}</small></a>}
          {excludedEntities.length > 0 && <a href="#review-excluded-entities">{t("revExcludedEntities")} <small>{excludedEntities.length}</small></a>}
          <a href="#review-source">{t(importedTables.length ? "revImportedRows" : "revSourceText")}</a>
        </nav>
        <a href={documentFileUrl(document.id)} target="_blank" rel="noreferrer">{t("openOriginal")} ↗</a>
      </aside>

      <div className="review-records">
        {!entities.length && <section className="dossier-sheet"><h2>{t("revNoEntities")}</h2><p>{t("revNoEntitiesNote")}</p></section>}
        {entities.map((entity, index) => {
          const connected = relationships.map((relation, relationIndex) => ({ relation, relationIndex }))
            .filter(({ relation }) => relation.subject === entity.ref || relation.object === entity.ref);
          return <article key={entity.ref} id={`review-entity-${index}`} className={`dossier-sheet review-entity ${rejectedEntities.has(index) ? "review-relation-rejected" : ""}`}>
            <header className="review-entity-heading">
              <div className="review-initials" aria-hidden="true">{entity.name.split(/\s+/).slice(0, 2).map((part) => part[0]).join("")}</div>
              <div><span className="form-number">{entity.kind} · Entity {index + 1} of {entities.length}</span><h2>{entity.name}</h2></div>
              {reviewControl(index, "entities")}
            </header>
            <dl className="review-fields">
              <div><dt>{t("revEntityType")}</dt><dd>{entity.kind}</dd></div>
              <div><dt>{t("revSourceIdentifier")}</dt><dd>{entity.identifier || t("revNotProvided")}</dd></div>
              {entity.attributes.map((attribute, i) => <div key={`${attribute.key}-${i}`}><dt>{label(attribute.key)}</dt><dd>{attribute.value}</dd></div>)}
            </dl>
            <section className="dossier-section"><h3>{t("revSourceEvidence")}</h3><blockquote>{entity.evidence}</blockquote></section>
            <section className="dossier-section"><h3>{t("revRelationships")} ({connected.length})</h3>
              {connected.length ? connected.map(({ relation, relationIndex }) => <div className={`review-relation ${rejected.has(relationIndex) ? "review-relation-rejected" : ""}`} key={relationIndex}>
                <p>{link(relation.subject)} <span className="review-predicate">{label(relation.predicate)}</span> {link(relation.object)}</p>
                <blockquote>{relation.evidence}</blockquote>
                {reviewControl(relationIndex)}
              </div>) : <p>{t("revNoEntityRelationships")}</p>}
            </section>
          </article>;
        })}
        <section className="dossier-sheet" id="review-relationships">
          <h2>{t("revAllRelationships")} ({relationships.length})</h2>
          <p>{t("revDirectionNote")}</p>
          {relationships.map((relation, index) => <article key={index} className={`review-relation ${rejected.has(index) ? "review-relation-rejected" : ""}`}>
            <p>{link(relation.subject)} → <strong>{label(relation.predicate)}</strong> → {link(relation.object)}</p>
            <blockquote>{relation.evidence}</blockquote>
            {reviewControl(index)}
          </article>)}
          {!relationships.length && <p>{t("revNoRelationships")}</p>}
        </section>
        {excludedEntities.length > 0 && <section className="dossier-sheet" id="review-excluded-entities">
          <h2>{t("revExcludedEntities")} ({excludedEntities.length})</h2>
          {excludedEntities.map((entity, index) => <article key={entity.ref} id={`review-entity-${entities.length + index}`}>
            <h3>{entity.name} · {entity.kind}</h3><p className="review-error">{entity.reason}</p>
            <blockquote>{entity.evidence}</blockquote>
          </article>)}
        </section>}
        {excluded.length > 0 && <section className="dossier-sheet" id="review-excluded">
          <h2>{t("revExcludedRelationships")} ({excluded.length})</h2>
          <p>{t("revExcludedNote2")}</p>
          {excluded.map((relation, index) => <article key={index} className="review-relation">
            <p>{link(relation.subject)} → <strong>{label(relation.predicate)}</strong> → {link(relation.object)}</p>
            <p className="review-error">{relation.reason}</p>
            <blockquote>{relation.evidence}</blockquote>
          </article>)}
        </section>}
        <section className="dossier-sheet" id="review-source">
          <h2>{importedTables.length ? t("revImportedRows") : t("revExtractedSourceText")}</h2>
          {importedTables.length ? <div className="review-tables">
            {importedTables.map((table) => <details key={table.name} open={importedTables.length < 4}>
              <summary>{table.name} <small>{table.rows.length}</small></summary>
              <div className="review-table-scroll">
                <table className="review-table">
                  <thead><tr>{table.columns.map((column) => <th key={column}>{label(column)}</th>)}</tr></thead>
                  <tbody>
                    {table.rows.map((row, index) => <tr key={index}>
                      {table.columns.map((column) => <td key={column}>{row[column] || ""}</td>)}
                    </tr>)}
                  </tbody>
                </table>
              </div>
            </details>)}
          </div> : <pre className="review-source-text">{document.text || t("revNoSourceText")}</pre>}
        </section>
      </div>
    </div> : document && <section className="dossier-sheet review-placeholder">
      <p>{t(PENDING.has(document.status) ? "revPreparing" : "revNothingYet")}</p>
      <Link to="/upload">{t("revReturn")}</Link>
    </section>}

    {reviewing && <footer className="review-confirm-bar">
      <div><strong>{acceptedEntityCount} entities · {acceptedRelationshipCount} relationships selected to save · {rejected.size + rejectedEntities.size} rejected</strong>
        <p role="status">{t("revDefaultYes")}</p>
        <p>{t("revConfirmNote")}</p></div>
      <div className="review-confirm-actions"><Link to="/upload">{t("revLater")}</Link>
        <button className="stamp-btn" disabled={confirming || remaining > 0} onClick={() => confirm()}>{confirming ? t("revConfirming") : t("revConfirmSave")}</button></div>
    </footer>}
  </main>;
}
