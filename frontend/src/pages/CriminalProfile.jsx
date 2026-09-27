import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { fetchCriminalById } from "../api/criminals";
import {
  fetchWorkspace, pinCriminal, unpinCriminal,
  addToWorkingList, removeFromWorkingList,
} from "../api/workspace";
import BackButton from "../components/BackButton";
import "./CriminalProfile.css";
import RelationGraph from "../components/RelationGraph";
import { useTranslation } from "../i18n";

function CriminalProfile() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { t } = useTranslation();

  const [selection, setSelection] = useState(null);
  const [criminal, setCriminal] = useState(null);
  const [relations, setRelations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  const [pinnedId, setPinnedIdState] = useState(null);
  const [inList, setInList] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setSelection(null);
    setNotFound(false);

    Promise.all([fetchCriminalById(id), fetchWorkspace()])
      .then(([data, workspace]) => {
        if (cancelled) return;
        if (!data) {
          setNotFound(true);
          return;
        }
        setCriminal(data.criminal);
        setRelations(data.relations);
        setPinnedIdState(workspace.pinnedId);
        setInList(workspace.workingList.some((c) => c.id === data.criminal.id));
      })
      .catch(() => {
        if (!cancelled) setNotFound(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [id]);

  if (loading) {
    return <div className="dossier-page"><p className="empty-note">{t("loading")}</p></div>;
  }

  if (notFound || !criminal) {
    return (
      <div className="dossier-page">
        <BackButton />
        <p className="empty-note">{t("fileMissing")}</p>
      </div>
    );
  }

  const isPinned = pinnedId === criminal.id;
  const location = criminal.location;
  const profileLocation = [location?.city, location?.state].filter(Boolean).join(", ");
  const displayedCriminal = { ...criminal, location };

  const handlePinToggle = async () => {
    try {
      if (isPinned) {
        await unpinCriminal();
        setPinnedIdState(null);
      } else {
        await pinCriminal(criminal.id);
        setPinnedIdState(criminal.id);
      }
    } catch (err) {
      console.error("Failed to update pin", err);
    }
  };

  const handleListToggle = async () => {
    try {
      if (inList) {
        await removeFromWorkingList(criminal.id);
        setInList(false);
      } else {
        await addToWorkingList(criminal.id);
        setInList(true);
      }
    } catch (err) {
      console.error("Failed to update working list", err);
    }
  };

  return (
    <div className="dossier-page">
      <BackButton />

      <div className="dossier-grid">
        <div className="dossier-left">
          <div className="dossier-sheet">
            <div className="dossier-header">
              <img src={criminal.photo} alt={criminal.name} className="dossier-photo" />
              <span className="form-number">File {criminal.id}</span>
              <h2>{criminal.name}</h2>
            </div>

            <div className="dossier-row"><span>{t("dateBirth")}</span><span>{criminal.dob}</span></div>
            <div className="dossier-row"><span>Age</span><span>{criminal.age}</span></div>
            <div className="dossier-row"><span>{t("height")}</span><span>{criminal.heightCm} cm</span></div>
            <div className="dossier-row"><span>{t("connectedLocation")}</span><span>{profileLocation || t("locationNotRecorded")}</span></div>
            <div className="dossier-row"><span>{t("lastSeen")}</span><span>{criminal.lastSeenDate || t("locationNotRecorded")}</span></div>
            <div className="dossier-row"><span>{t("status")}</span><span>{criminal.recordStatus}</span></div>

            {criminal.familyKnown && (
              <div className="dossier-section">
                <h4>{t("familyKnown")}</h4>
                <p>{criminal.familyKnown}</p>
              </div>
            )}

            <div className="dossier-section">
              <h4>{t("crimesCommitted")}</h4>
              <div className="tag-row">
                {criminal.crimeTags.map((tag) => <span key={tag} className="tag-stamp">{tag}</span>)}
              </div>
            </div>

            {criminal.cases && criminal.cases.length > 0 && (
              <div className="dossier-section">
                <h4>{t("caseHistory")}</h4>
                {criminal.cases.map((c) => (
                  <div className="dossier-row" key={c.caseId}>
                    <span>{c.caseId} — {c.crime}, {c.location}</span>
                    <span>{c.status}</span>
                  </div>
                ))}
              </div>
            )}

            <div className="dossier-actions">
              <button className={`stamp-btn small ${isPinned ? "stamp-btn-active" : ""}`} onClick={handlePinToggle}>
                {isPinned ? t("unpinFromDashboard") : t("pinToDashboard")}
              </button>
              <button className={`stamp-btn small ${inList ? "stamp-btn-active" : ""}`} onClick={handleListToggle}>
                {t(inList ? "removeFromList" : "addToList")}
              </button>
            </div>
          </div>

          <button className="stamp-btn full-width" onClick={() => navigate("/dashboard")}>{t("closeFile")}</button>
        </div>

        <div className="dossier-right">

          <div className="graph-toolbar">
            <button type="button" className="graph-analysis-btn" onClick={() => navigate(`/analysis/${id}`)}>
              {t("addToAnalysis")}
            </button>
          </div>

          <div
            className="graph-frame"
          >
            <RelationGraph
              key={id}
              onSelectionChange={setSelection}
              mainCriminal={displayedCriminal}
              onNodeClick={(relatedId) => navigate(`/criminal/${relatedId}`)}
              height={520}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

export default CriminalProfile;
