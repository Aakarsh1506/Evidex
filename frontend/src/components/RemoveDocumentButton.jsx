import { useState } from "react";
import { canRemoveDocument, deleteDocument } from "../api/documents";
import { useTranslation } from "../i18n";

export default function RemoveDocumentButton({ document, disabled, onRemoved, onError, onBusyChange }) {
  const { t } = useTranslation();
  const [removing, setRemoving] = useState(false);
  const allowed = canRemoveDocument(document);

  async function remove() {
    if (!allowed || removing || disabled) return;
    if (!window.confirm(`${t("docRemove")}: “${document.name}”?\n\n${t("docRemoveConfirm")}`)) return;
    setRemoving(true);
    onBusyChange?.(true);
    try {
      await deleteDocument(document.id);
      onRemoved(document.id);
    } catch (error) { onError(error.message); }
    finally { setRemoving(false); onBusyChange?.(false); }
  }

  return <button type="button" className="stamp-btn" onClick={remove}
    disabled={!allowed || disabled || removing}
    title={allowed ? t("docRemoveTitle") : t("docRemoveBlocked")}>
    {removing ? t("docRemoving") : t("docRemove")}
  </button>;
}
