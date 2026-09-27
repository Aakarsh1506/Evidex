import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { fetchCaseById, fetchCaseNetwork, fetchCrimeTypes } from "../api/cases";
import { fetchStats } from "../api/stats";
import { fetchWorkspace, unpinCase, removeFromWorkingList } from "../api/workspace";
import RelationGraph from "../components/RelationGraph";
import "./Dashboard.css";
import { useTranslation } from "../i18n";

function Dashboard() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [selectedTags, setSelectedTags] = useState([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [presetTags, setPresetTags] = useState([]);

  const [stats, setStats] = useState(null);

  const [pinnedId, setPinnedIdState] = useState(null);
  const [pinnedCase, setPinnedCase] = useState(null);
  const [pinnedNetwork, setPinnedNetwork] = useState(null);
  const [workingList, setWorkingList] = useState([]);

  useEffect(() => {
    fetchStats().then(setStats).catch(() => setStats(null));
    fetchCrimeTypes().then(setPresetTags).catch(() => setPresetTags([]));
    fetchWorkspace()
      .then(({ pinnedId, workingList }) => {
        setPinnedIdState(pinnedId);
        setWorkingList(workingList);
      })
      .catch(() => {
        setPinnedIdState(null);
        setWorkingList([]);
      });
  }, []);

  useEffect(() => {
    if (!pinnedId) {
      setPinnedCase(null);
      setPinnedNetwork(null);
      return;
    }
    const controller = new AbortController();
    fetchCaseById(pinnedId).then((data) => {
      if (!controller.signal.aborted) setPinnedCase(data);
    });
    // The graph is optional: the pinned card still renders without Neo4j.
    fetchCaseNetwork(pinnedId, { signal: controller.signal })
      .then((data) => { if (!controller.signal.aborted) setPinnedNetwork(data); })
      .catch(() => {});
    return () => controller.abort();
  }, [pinnedId]);

  const toggleTag = (tag) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((item) => item !== tag) : [...prev, tag]
    );
  };

  const handleSearch = () => {
    const params = new URLSearchParams();
    if (query.trim()) params.set("q", query.trim());
    if (selectedTags.length) params.set("tags", selectedTags.join(","));
    navigate(`/search?${params.toString()}`);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter") handleSearch();
  };

  const handleUnpin = async () => {
    try {
      await unpinCase();
      setPinnedIdState(null);
    } catch (err) {
      console.error("Failed to unpin case", err);
    }
  };

  const handleRemoveFromList = async (id) => {
    try {
      await removeFromWorkingList(id);
      setWorkingList((prev) => prev.filter((item) => item.id !== id));
    } catch (err) {
      console.error("Failed to remove from list", err);
    }
  };

  const tagCounts = stats?.tagCounts || [];
  const cityCounts = stats?.cityCounts || [];
  const statusCounts = stats?.statusCounts || [];
  const maxTagCount = Math.max(...tagCounts.map((row) => row[1]), 1);

  return (
    <div className="board-page">
      <div className="search-tab-wrapper">
        <div className="search-tab">
          <input
            type="text"
            className="search-input"
            placeholder={t("searchPlaceholder")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => setShowDropdown(true)}
            onKeyDown={handleKeyDown}
          />
          <button className="stamp-btn small" onClick={handleSearch}>
            {t("search")}
          </button>
        </div>

        {showDropdown && (
          <div className="tag-note">
            <div className="tag-note-head">
              <span>{t("crimeFrequency")}</span>
              <button onClick={() => setShowDropdown(false)}>{t("close")}</button>
            </div>
            <div className="tag-chip-list">
              {presetTags.map((tag) => (
                <button
                  key={tag}
                  className={`tag-chip ${selectedTags.includes(tag) ? "tag-chip-active" : ""}`}
                  onClick={() => toggleTag(tag)}
                >
                  {tag}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="working-section">
        <h3 className="working-heading">{t("pinned")}</h3>

        <div className="working-grid">
          <div className="working-col working-map-col">
            {pinnedCase && pinnedNetwork ? (
              <div className="graph-frame mini">
                <RelationGraph
                  key={pinnedCase.id}
                  mainCriminal={{ id: pinnedCase.id, name: pinnedCase.reference }}
                  network={pinnedNetwork}
                  onNodeClick={(caseId) => navigate(`/case/${encodeURIComponent(caseId)}`)}
                  height={560}
                />
              </div>
            ) : (
              <div className="working-empty">
                <p className="empty-note">{t(pinnedCase ? "caseNoNetwork" : "noWorking")}</p>
              </div>
            )}
          </div>

          <div className="working-col working-side-col">
            <div className="working-side-top">
              {pinnedCase ? (
                <div className="mini-dossier">
                  <h4>{pinnedCase.title || pinnedCase.crime || t("caseUntitled")}</h4>
                  <div className="dossier-row"><span>{t("caseReference")}</span><span>{pinnedCase.reference}</span></div>
                  <div className="dossier-row"><span>{t("status")}</span><span>{pinnedCase.status || "—"}</span></div>
                  <div className="dossier-row"><span>{t("casePeople")}</span><span>{pinnedCase.people.length}</span></div>
                  <div className="dossier-row"><span>{t("caseDocuments")}</span><span>{pinnedCase.documents.length}</span></div>
                  <div className="tag-row">
                    {pinnedCase.crimeTags.map((tag) => (
                      <span key={tag} className="tag-stamp">{tag}</span>
                    ))}
                  </div>
                  <div className="mini-actions">
                    <button className="stamp-btn small" onClick={() => navigate(`/case/${encodeURIComponent(pinnedCase.id)}`)}>
                      {t("openFile")}
                    </button>
                    <button className="stamp-btn small" onClick={handleUnpin}>
                      {t("unpin")}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="working-empty">
                  <p className="empty-note">{t("noWorking")}</p>
                </div>
              )}
            </div>

            <div className="working-side-divider" />

            <div className="working-side-bottom">
              <h4 className="working-list-title">{t("onTheList")}</h4>
              {workingList.length === 0 ? (
                <p className="empty-note">{t("noCases")}</p>
              ) : (
                <ul className="working-list-items">
                  {workingList.map((item) => (
                    <li key={item.id}>
                      <div className="working-list-info" onClick={() => navigate(`/case/${encodeURIComponent(item.id)}`)}>
                        <strong>{item.reference}</strong>
                        {item.title ? <span className="working-list-sub">{item.title}</span> : null}
                        <div className="tag-row">
                          {item.crimeTags.map((tag) => (
                            <span key={tag} className="tag-stamp small">{tag}</span>
                          ))}
                        </div>
                      </div>
                      <button className="list-remove-btn" onClick={() => handleRemoveFromList(item.id)}>
                        ×
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="pinboard">
        <div className="pin-card card-1">
          <span className="pin" />
          <h3>{t("casesOnFileTitle")}</h3>
          <div className="pin-number">{stats ? stats.totalCases : "…"}</div>
          <p className="pin-note">{t("tracked")}</p>
        </div>
        <div className="pin-card card-4">
          <span className="pin" />
          <h3>{t("documentsOnFile")}</h3>
          <div className="pin-number">{stats ? stats.totalDocuments : "…"}</div>
          <p className="pin-note">{t("linksKnown")}</p>
        </div>
        <div className="pin-card card-2 wide">
          <span className="pin" />
          <h3>{t("crimeFrequency")}</h3>
          <div className="bar-list">
            {tagCounts.map(([tag, count]) => (
              <div className="bar-row" key={tag}>
                <span className="bar-label">{tag}</span>
                <div className="bar-track">
                  <div className="bar-fill" style={{ width: `${(count / maxTagCount) * 100}%` }} />
                </div>
                <span className="bar-count">{count}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="pin-card card-3">
          <span className="pin" />
          <h3>{t("caseStatusBreakdown")}</h3>
          <ul className="city-list">
            {statusCounts.map(([status, count]) => (
              <li key={status}>
                <span>{status}</span>
                <span>{count}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="pin-card card-3">
          <span className="pin" />
          <h3>{t("citiesWatch")}</h3>
          <ul className="city-list">
            {cityCounts.map(([city, count]) => (
              <li key={city}>
                <span>{city}</span>
                <span>{count}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
