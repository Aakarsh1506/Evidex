import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import BackButton from "../components/BackButton";
import DocumentActions from "../components/DocumentActions";
import DocumentProgress from "../components/DocumentProgress";
import DocumentViewer from "../components/DocumentViewer";
import { useTranslation } from "../i18n";
import {
  fetchDocuments, fetchDocument, fetchSourceTypes, uploadDocument,
} from "../api/documents";
import "./UploadDoc.css";

const STATUS = {
  awaiting_review: "upAwaiting", stored: "upStored", queued: "revQueued",
  processing: "upProcessing", syncing: "upSyncing", complete: "upComplete",
  failed: "revFailed", sync_failed: "upSyncFailed", cancelled: "revCancelled",
};
const BUSY = new Set(["queued", "processing", "syncing"]);

export default function UploadDoc() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const input = useRef(null);
  const [documents, setDocuments] = useState([]);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [types, setTypes] = useState({});
  const [extensions, setExtensions] = useState([]);
  const [sourceType, setSourceType] = useState("fir");
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(null);
  const [error, setError] = useState(null);
  const [viewing, setViewing] = useState(false);

  useEffect(() => {
    let active = true;
    Promise.all([fetchDocuments(), fetchSourceTypes()]).then(([docs, config]) => {
      if (!active) return;
      setDocuments(docs); setTypes(config.sourceTypes); setExtensions(config.extensions);
    }).catch((err) => { if (active) setError(err.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const processing = documents.some((doc) => BUSY.has(doc.status));
  useEffect(() => {
    if (!processing) return;
    let active = true;
    const timer = setInterval(() => {
      fetchDocuments().then((docs) => { if (active) setDocuments(docs); })
        .catch((err) => { if (active) setError(err.message); });
    }, 3000);
    return () => { active = false; clearInterval(timer); };
  }, [processing]);

  const selectedStatus = documents.find((doc) => doc.id === selected)?.status;
  const selectedProgress = JSON.stringify(documents.find((doc) => doc.id === selected)?.progress);
  useEffect(() => {
    if (selected === null) return;
    let active = true;
    fetchDocument(selected).then((doc) => { if (active) setDetail(doc); })
      .catch((err) => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [selected, selectedStatus, selectedProgress]);

  async function upload(event) {
    const files = [...(event.target.files || [])];
    event.target.value = "";
    if (!files.length) return;
    setError(null);
    // Upload one at a time: each document is queued and reviewed on its own.
    const added = [], failed = [];
    for (const [index, file] of files.entries()) {
      setUploading({ done: index, total: files.length, name: file.name });
      if (file.size > 20 * 1024 * 1024) {
        failed.push(`${file.name}: ${t("uploadTooLarge")}`);
        continue;
      }
      try {
        const doc = await uploadDocument(file, sourceType);
        added.push(doc);
        setDocuments((prev) => [doc, ...prev]);
      } catch (err) {
        failed.push(`${file.name}: ${err.message}`);
      }
    }
    setUploading(null);
    if (failed.length) setError(`${failed.length}/${files.length} ${t("uploadFailedSome")} ${failed.join(" · ")}`);
    // A single upload opens its review; a batch keeps the list in view while they process.
    if (added.length === 1 && !failed.length) navigate(`/documents/${added[0].id}/review`);
  }

  function updatedDocument(doc) {
    setDocuments((prev) => prev.map((item) => item.id === doc.id ? { ...item, ...doc } : item));
    setDetail((prev) => prev?.id === doc.id ? { ...prev, ...doc } : prev);
    setError(null);
  }

  function removedDocument(id) {
    setDocuments((prev) => prev.filter((doc) => doc.id !== id));
    if (selected === id) { setSelected(null); setDetail(null); }
    setError(null);
  }

  const entities = detail?.extraction?.entities || [];
  const relationships = detail?.extraction?.relationships || [];
  const names = Object.fromEntries(entities.map((entity) => [entity.ref, entity.name]));
  return <div className="upload-page">
    <BackButton />
    <section className="upload-top upload-controls">
      <h2>{t("uploadAnalyze")}</h2>
      <label htmlFor="source-type">{t("recordSource")}</label>
      <select id="source-type" value={sourceType} disabled={loading || uploading}
        onChange={(event) => setSourceType(event.target.value)}>
        {Object.entries(types).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
      <input ref={input} className="upload-input-hidden" type="file" multiple accept={extensions.join(",")}
        onChange={upload} />
      <button className="stamp-btn upload-btn-center" disabled={!!uploading || loading || !extensions.length}
        onClick={() => input.current?.click()}>
        {uploading ? `${t("upload")}… ${uploading.done + 1}/${uploading.total}` : `${t("upload")} ${t("upAndExtract")}`}
      </button>
      {uploading && <>
        <p className="upload-hint" role="status">{uploading.total > 1
          ? `${t("uploadingFile")} ${uploading.done + 1} / ${uploading.total}: ${uploading.name}`
          : uploading.name}</p>
        <DocumentProgress uploading />
      </>}
    </section>
    {error && <p role="alert" className="upload-error">{error}</p>}
    <div className={`doc-layout ${selected !== null ? "doc-layout-split" : ""}`}>
    {loading ? <p role="status" className="empty-note">{t("loadingRecords")}</p> :
      <div className="doc-grid">
        {documents.map((doc) => <article className="doc-card" key={doc.id}>
          <button type="button" className="doc-card-open"
          onClick={() => { if (doc.status === "awaiting_review") { navigate(`/documents/${doc.id}/review`); return; } if (selected !== doc.id) { setDetail(null); setSelected(doc.id); } }} aria-pressed={selected === doc.id}>
          <span className="doc-card-tag">{types[doc.sourceType] || t("upDocument")}</span>
          <h3>{doc.name}</h3>
          <p className="doc-card-meta">{(doc.size / 1024).toFixed(1)} KB · {new Date(doc.uploadedAt).toLocaleDateString()}</p>
          <p className="doc-status">{STATUS[doc.status] ? t(STATUS[doc.status]) : doc.status}</p>
          </button>
          <DocumentProgress document={doc} />
          <DocumentActions document={doc} onUpdated={updatedDocument}
            onRemoved={removedDocument} onError={setError} />
        </article>)}
        {!documents.length && <p className="empty-note">{t("noDocuments")}</p>}
      </div>}
    {selected !== null && <section className="doc-preview extraction-detail" aria-live="polite">
      <div className="doc-preview-header">
        <h2>{detail?.name || t("revLoadingExtraction")}</h2>
        <button className="doc-preview-close" onClick={() => { setSelected(null); setDetail(null); setViewing(false); }}>{t("close")}</button>
      </div>
      {detail && <>
        <p role="status">{STATUS[detail.status]}</p>
        <DocumentProgress document={detail} />
        <DocumentActions document={detail} onUpdated={updatedDocument}
          onRemoved={removedDocument} onError={setError} />
        {detail.processingError && <p role="alert" className="upload-error">{detail.processingError}</p>}
        <p className="doc-original-row">
          <button type="button" className="stamp-btn small" onClick={() => setViewing(true)}>{t("viewOriginal")}</button>
        </p>
        {viewing && <DocumentViewer documentId={detail.id} name={detail.name}
          mimeType={detail.type} onClose={() => setViewing(false)} />}
        {detail.extraction && <>
          <p><Link to={`/documents/${detail.id}/review`}>{t("upOpenReview")}</Link></p>
          <h3>{entities.length} entities · {relationships.length} relationships</h3>
          <p>{t("upCaution")}</p>
          {entities.map((entity) => <details key={entity.ref} className="extracted-item">
            <summary>{entity.kind}: {entity.name}</summary>
            {entity.identifier && <p>{t("revSourceIdentifier")}: {entity.identifier}</p>}
            <dl>{entity.attributes.map((attr, index) => <div key={`${attr.key}-${index}`}>
              <dt>{attr.key.replaceAll("_", " ")}</dt><dd>{attr.value}</dd>
            </div>)}</dl>
            <blockquote>{entity.evidence}</blockquote>
          </details>)}
          {relationships.map((relation, index) => <details key={index} className="extracted-item">
            <summary>{names[relation.subject]} → {relation.predicate} → {names[relation.object]}</summary>
            <blockquote>{relation.evidence}</blockquote>
          </details>)}
          {!entities.length && <p>{t("upNoEntities")}</p>}
        </>}
        {detail.text && <details className="extracted-item"><summary>{t("revExtractedSourceText")}</summary>
          <pre className="extracted-text">{detail.text}</pre></details>}
      </>}
    </section>}
    </div>
  </div>;
}
