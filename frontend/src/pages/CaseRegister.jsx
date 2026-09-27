import { useEffect, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { fetchAllCases, fetchCases } from "../api/cases";
import { fetchWorkspace, addToWorkingList, removeFromWorkingList } from "../api/workspace";
import BackButton from "../components/BackButton";
import { useTranslation } from "../i18n";
import "./CriminalList.css";

// Serves both the full case register and a filtered search. With no query and no tags
// the backend returns nothing, so the register asks for everything explicitly.
function CaseRegister() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { t } = useTranslation();

  const [listedIds, setListedIds] = useState([]);
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const q = (searchParams.get("q") || "").trim();
  const tags = (searchParams.get("tags") || "").split(",").map((tag) => tag.trim()).filter(Boolean);
  const searching = !!q || !!tags.length;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([searching ? fetchCases({ q, tags }) : fetchAllCases(), fetchWorkspace()])
      .then(([data, workspace]) => {
        if (cancelled) return;
        setCases(data);
        setListedIds(workspace.workingList.map((item) => item.id));
      })
      .catch(() => {
        if (!cancelled) setError(t("dbUnreachable"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [q, tags.join(","), searching]);

  const handleToggleList = async (e, record) => {
    e.stopPropagation();
    try {
      if (listedIds.includes(record.id)) {
        await removeFromWorkingList(record.id);
        setListedIds((prev) => prev.filter((id) => id !== record.id));
      } else {
        await addToWorkingList(record.id);
        setListedIds((prev) => [...prev, record.id]);
      }
    } catch (err) {
      console.error("Failed to update case list", err);
    }
  };

  const heading = loading
    ? t("loadingCases")
    : `${cases.length} ${searching ? t("searchResults") : t("casesOnFile")}`;

  return (
    <div className="list-page">
      <BackButton />

      <header className="list-top">
        <h2>{heading}</h2>
      </header>

      <div className="folder-stack">
        {error && <p className="empty-note">{error}</p>}
        {!loading && !error && cases.length === 0 && (
          <p className="empty-note">{t(searching ? "noSearchMatches" : "noCaseRecords")}</p>
        )}

        {cases.map((record, i) => (
          <div
            key={record.id}
            className="folder case-folder"
            style={{ transform: `rotate(${i % 2 === 0 ? -0.5 : 0.5}deg)` }}
            onClick={() => navigate(`/case/${encodeURIComponent(record.id)}`)}
          >
            <span className="folder-tab">{record.reference}</span>
            <div className="folder-info">
              <h3>{record.title || record.crime || t("caseUntitled")}</h3>
              <p className="folder-alias">
                {[record.location?.city, record.status].filter(Boolean).join(" · ")}
              </p>
              <p className="case-folder-meta">
                {record.peopleCount} {t("casePeopleCount")} · {record.documentCount}{" "}
                {t("caseDocumentCount")}
                {record.month ? ` · ${record.month}` : ""}
                {record.hasSummary ? ` · ${t("caseSummarised")}` : ""}
              </p>
              <div className="tag-row">
                {record.crimeTags.map((tag) => (
                  <span key={tag} className="tag-stamp">{tag}</span>
                ))}
              </div>
            </div>
            <button
              className={`list-toggle-btn ${listedIds.includes(record.id) ? "list-toggle-active" : ""}`}
              onClick={(e) => handleToggleList(e, record)}
            >
              {listedIds.includes(record.id) ? t("removeFromList") : t("addToList")}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

export default CaseRegister;
