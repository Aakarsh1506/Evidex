import { useState } from "react";
import { cancelDocument, retryDocument } from "../api/documents";
import RemoveDocumentButton from "./RemoveDocumentButton";
import { useTranslation } from "../i18n";
import "./DocumentActions.css";

export default function DocumentActions({ document, disabled, onUpdated, onRemoved, onError }) {
  const { t } = useTranslation();
  const [retrying, setRetrying] = useState(false);
  const [removing, setRemoving] = useState(false);
  const canProcess = ["stored", "failed", "sync_failed", "cancelled"].includes(document.status);
  const busy = ["queued", "processing", "syncing"].includes(document.status);

  async function process() {
    if (!canProcess || disabled || retrying || removing) return;
    setRetrying(true);
    try { onUpdated(await retryDocument(document.id)); }
    catch (error) { onError(error.message); }
    finally { setRetrying(false); }
  }

  async function stop() {
    if (!busy || disabled || retrying || removing) return;
    setRetrying(true);
    try { onUpdated(await cancelDocument(document.id)); }
    catch (error) { onError(error.message); }
    finally { setRetrying(false); }
  }

  return <div className="document-actions">
    <div className="document-action-buttons">
      {canProcess && <button type="button" className="stamp-btn" disabled={disabled || retrying || removing}
        onClick={process}>{retrying ? t("docQueuing") : document.status === "sync_failed" ? t("docRetrySaving") : document.status === "cancelled" ? t("docProcessAgain") : t("docProcess")}</button>}
      {busy && <button type="button" className="stamp-btn document-stop-button" disabled={disabled || retrying || removing}
        onClick={stop}>{retrying ? t("docStopping") : t("docStop")}</button>}
      <RemoveDocumentButton document={document} disabled={disabled || retrying}
        onBusyChange={setRemoving} onRemoved={onRemoved} onError={onError} />
    </div>
    {busy && <p>{t("docBusyNote")}</p>}
    {document.status === "awaiting_review" && <p>{t("docReviewNote")}</p>}
    {document.confirmedAt && <p>{t("docConfirmedNote")}</p>}
  </div>;
}
