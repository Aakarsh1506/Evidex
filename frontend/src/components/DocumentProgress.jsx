import { useTranslation } from "../i18n";
import "./DocumentProgress.css";

export default function DocumentProgress({ document, uploading = false }) {
  const { t } = useTranslation();
  if (!uploading && (!document || document.status === "stored")) return null;
  const status = uploading ? "uploading" : document.status;
  const busy = ["uploading", "queued", "processing", "syncing"].includes(status);
  const failed = ["failed", "sync_failed"].includes(status);
  const stopped = status === "cancelled";
  const done = ["awaiting_review", "complete", "cancelled"].includes(status);
  const progress = document?.progress;
  const percent = done ? 100 : status === "queued" ? 0
    : Math.min(99, Math.max(0, Number(progress?.percent) || 0));
  const fallback = {
    uploading: t("progUploading"), queued: t("progQueued"),
    processing: t("progProcessing"), syncing: t("progSyncing"),
    awaiting_review: t("progAwaitingReview"), complete: t("progComplete"),
    cancelled: t("progCancelledBy"),
    failed: t("progFailed"), sync_failed: t("progSyncFailed"),
  };
  const label = done || ["queued", "uploading"].includes(status) ? fallback[status]
    : failed ? `${fallback[status]}${progress?.label ? ` · ${progress.label}` : ""}`
    : progress?.label || fallback[status];
  const indeterminate = uploading || (busy && !progress);

  return <span className={`document-progress ${busy ? "is-busy" : ""} ${failed || stopped ? "is-failed" : ""}`}>
    <span className="document-progress-caption" role="status">
      <span>{label}</span>{!indeterminate && <span>{percent}%</span>}
    </span>
    <span className={`document-progress-track ${indeterminate ? "is-indeterminate" : ""}`}
      role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100}
      aria-valuenow={indeterminate ? undefined : percent} aria-valuetext={label}>
      <span className="document-progress-fill" style={{ width: indeterminate ? "35%" : `${percent}%` }} />
    </span>
  </span>;
}
