import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchAllCriminals } from "../api/criminals";
import { fetchWorkspace, addToWorkingList, removeFromWorkingList } from "../api/workspace";
import BackButton from "../components/BackButton";
import { useTranslation } from "../i18n";
import "./CriminalList.css";

function CriminalListPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();

  const [listedIds, setListedIds] = useState([]);
  const [criminals, setCriminals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([fetchAllCriminals(), fetchWorkspace()])
      .then(([data, workspace]) => {
        if (cancelled) return;
        setCriminals(data);
        setListedIds(workspace.workingList.map((c) => c.id));
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
  }, []);

  const handleToggleList = async (e, criminal) => {
    e.stopPropagation();
    try {
      if (listedIds.includes(criminal.id)) {
        await removeFromWorkingList(criminal.id);
        setListedIds((prev) => prev.filter((id) => id !== criminal.id));
      } else {
        await addToWorkingList(criminal.id);
        setListedIds((prev) => [...prev, criminal.id]);
      }
    } catch (err) {
      console.error("Failed to update working list", err);
    }
  };

  return (
    <div className="list-page">
      <BackButton />

      <header className="list-top">
        <h2>{loading ? t("loadingRecords") : `${criminals.length} ${t("criminalsOnFile")}`}</h2>
      </header>

      <div className="folder-stack">
        {error && <p className="empty-note">{error}</p>}
        {!loading && !error && criminals.length === 0 && (
          <p className="empty-note">{t("noRecords")}</p>
        )}

        {criminals.map((c, i) => (
          <div
            key={c.id}
            className="folder"
            style={{ transform: `rotate(${i % 2 === 0 ? -0.5 : 0.5}deg)` }}
            onClick={() => navigate(`/criminal/${c.id}`)}
          >
            <span className="folder-tab">{c.id}</span>
            <img src={c.photo} alt={c.name} className="folder-photo" />
            <div className="folder-info">
              <h3>{c.name}</h3>
            <p className="folder-alias">{c.location?.city ? `${t("basedIn")} ${c.location.city}` : ""}</p>
              <div className="tag-row">
                {c.crimeTags.map((tag) => <span key={tag} className="tag-stamp">{tag}</span>)}
              </div>
            </div>
            <button
              className={`list-toggle-btn ${listedIds.includes(c.id) ? "list-toggle-active" : ""}`}
              onClick={(e) => handleToggleList(e, c)}
            >
              {listedIds.includes(c.id) ? t("removeFromList") : t("addToList")}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

export default CriminalListPage;
