import { useEffect, useRef, useState } from "react";
import { documentFileUrl } from "../api/documents";
import { useTranslation } from "../i18n";
import "./DocumentViewer.css";

// Which types the browser can render in place. Matches VIEWABLE_INLINE in
// backend/routes/documents.py — anything else is offered as a download instead.
const IMAGE = new Set(["image/png", "image/jpeg"]);
const TEXT = new Set(["text/plain", "text/csv", "application/json", "application/sql"]);

export default function DocumentViewer({ documentId, name, mimeType, onClose }) {
  const { t } = useTranslation();
  const [text, setText] = useState(null);
  const [error, setError] = useState("");
  const closeRef = useRef(null);
  const url = documentFileUrl(documentId);
  const isText = TEXT.has(mimeType);
  const isImage = IMAGE.has(mimeType);
  const isPdf = mimeType === "application/pdf";

  // Text is fetched and rendered as text, never as markup: a .json or .csv source
  // document must not be able to run anything in the officer's session.
  useEffect(() => {
    if (!isText) return;
    const controller = new AbortController();
    fetch(url, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error(t("viewerFailed"));
        return res.text();
      })
      .then((body) => { if (!controller.signal.aborted) setText(body); })
      .catch((err) => { if (!controller.signal.aborted) setError(err.message); });
    return () => controller.abort();
  }, [url, isText, t]);

  // Escape closes, and focus starts on the close button so the dialog is keyboard-usable.
  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (event) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="viewer-backdrop" onClick={onClose}>
      <div
        className="viewer-panel"
        role="dialog"
        aria-modal="true"
        aria-label={`${t("viewerTitle")}: ${name}`}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="viewer-head">
          <div>
            <h3>{name}</h3>
            <p className="viewer-note">{t("viewerNote")}</p>
          </div>
          <div className="viewer-actions">
            <a className="stamp-btn small" href={url} target="_blank" rel="noreferrer">
              {t("viewerNewTab")}
            </a>
            <button ref={closeRef} type="button" className="stamp-btn small" onClick={onClose}>
              {t("close")}
            </button>
          </div>
        </header>

        <div className="viewer-body">
          {error && <p className="viewer-error" role="alert">{error}</p>}

          {/* No sandbox attribute: a fully restrictive sandbox also disables Chrome's built-in
              PDF viewer, which then renders "This page has been blocked by Chrome" instead of
              the document. This is safe here because the file is same-origin from our own API,
              served with X-Content-Type-Options: nosniff, and the backend never serves HTML
              inline — only PDFs, images and plain text reach this component. */}
          {isPdf && <iframe className="viewer-frame" src={url} title={name} />}

          {isImage && <img className="viewer-image" src={url} alt={name} />}

          {isText && !error && (
            text === null
              ? <p className="empty-note" role="status">{t("loading")}</p>
              : <pre className="viewer-text">{text}</pre>
          )}

          {!isPdf && !isImage && !isText && (
            <p className="empty-note">{t("viewerUnsupported")}</p>
          )}
        </div>
      </div>
    </div>
  );
}
