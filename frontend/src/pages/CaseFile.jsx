import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { fetchCaseById, fetchCaseNetwork, generateCaseSummary } from "../api/cases";
import {
  fetchWorkspace, pinCase, unpinCase,
  addToWorkingList, removeFromWorkingList,
} from "../api/workspace";
import BackButton from "../components/BackButton";
import RelationGraph from "../components/RelationGraph";
import CaseSummary from "../components/CaseSummary";
import DocumentViewer from "../components/DocumentViewer";
import { useTranslation } from "../i18n";
import "./CriminalProfile.css";
import "./CaseFile.css";

function CaseFile() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { t, language } = useTranslation();

  const [record, setRecord] = useState(null);
  const [network, setNetwork] = useState(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [pinnedId, setPinnedId] = useState(null);
  const [inList, setInList] = useState(false);
  const [summarising, setSummarising] = useState(false);
  const [summaryError, setSummaryError] = useState("");
  const [openPerson, setOpenPerson] = useState(null);
  const [viewing, setViewing] = useState(null);
  const summaryRequest = useRef(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setNotFound(false);
    setNetwork(null);
    setSummaryError("");

    Promise.all([fetchCaseById(id), fetchWorkspace()])
      .then(([data, workspace]) => {
        if (cancelled) return;
        if (!data) {
          setNotFound(true);
          return;
        }
        setRecord(data);
        setPinnedId(workspace.pinnedId);
        setInList(workspace.workingList.some((item) => item.id === data.id));
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

  // The graph loads on its own so a missing Neo4j network never hides the case file.
  useEffect(() => {
    const controller = new AbortController();
    fetchCaseNetwork(id, { signal: controller.signal })
      .then((data) => { if (!controller.signal.aborted) setNetwork(data); })
      .catch(() => {});
    return () => controller.abort();
  }, [id]);

  useEffect(() => () => summaryRequest.current?.abort(), []);

  if (loading) {
    return <div className="dossier-page"><p className="empty-note">{t("loading")}</p></div>;
  }

  if (notFound || !record) {
    return (
      <div className="dossier-page">
        <BackButton />
        <p className="empty-note">{t("caseMissing")}</p>
      </div>
    );
  }

  const isPinned = pinnedId === record.id;
  const place = [record.location?.city, record.location?.state].filter(Boolean).join(", ");

  const handlePinToggle = async () => {
    try {
      if (isPinned) {
        await unpinCase();
        setPinnedId(null);
      } else {
        await pinCase(record.id);
        setPinnedId(record.id);
      }
    } catch (err) {
      console.error("Failed to update pin", err);
    }
  };

  const handleListToggle = async () => {
    try {
      if (inList) {
        await removeFromWorkingList(record.id);
        setInList(false);
      } else {
        await addToWorkingList(record.id);
        setInList(true);
      }
    } catch (err) {
      console.error("Failed to update case list", err);
    }
  };

  const handleGenerateSummary = async () => {
    if (summarising) return;
    const controller = new AbortController();
    summaryRequest.current = controller;
    setSummarising(true);
    setSummaryError("");
    try {
      const summary = await generateCaseSummary(record.id, language, { signal: controller.signal });
      if (!controller.signal.aborted) setRecord((prev) => ({ ...prev, summary }));
    } catch (err) {
      if (!controller.signal.aborted) setSummaryError(err.message);
    } finally {
      if (summaryRequest.current === controller) summaryRequest.current = null;
      if (!controller.signal.aborted) setSummarising(false);
    }
  };

  return (
    <div className="dossier-page">
      <BackButton />

      <div className="dossier-grid">
        <div className="dossier-left">
          <div className="dossier-sheet">
            <div className="dossier-header case-header">
              <span className="form-number">{t("caseFileLabel")} {record.reference}</span>
              <h2>{record.title || record.crime || t("caseUntitled")}</h2>
            </div>

            <div className="dossier-row"><span>{t("caseReference")}</span><span>{record.reference}</span></div>
            <div className="dossier-row"><span>{t("caseCategory")}</span><span>{record.crime || t("locationNotRecorded")}</span></div>
            <div className="dossier-row"><span>{t("status")}</span><span>{record.status || t("locationNotRecorded")}</span></div>
            <div className="dossier-row"><span>{t("caseOpened")}</span><span>{record.openedOn || record.month || t("locationNotRecorded")}</span></div>
            <div className="dossier-row"><span>{t("caseLocation")}</span><span>{place || t("locationNotRecorded")}</span></div>

            <div className="dossier-section">
              <h4>{t("caseCategory")}</h4>
              <div className="tag-row">
                {record.crimeTags.length
                  ? record.crimeTags.map((tag) => <span key={tag} className="tag-stamp">{tag}</span>)
                  : <span className="empty-note">{t("locationNotRecorded")}</span>}
              </div>
            </div>

            {/* Person details live here now: a participant is part of the case record. */}
            <div className="dossier-section">
              <h4>{t("casePeople")} ({record.people.length})</h4>
              {record.people.length === 0 ? (
                <p className="empty-note">{t("caseNoPeople")}</p>
              ) : (
                <ul className="case-people">
                  {record.people.map((person) => (
                    <li key={person.id}>
                      <button
                        type="button"
                        className="case-person-head"
                        aria-expanded={openPerson === person.id}
                        onClick={() => setOpenPerson(openPerson === person.id ? null : person.id)}
                      >
                        <img src={person.photo} alt="" className="case-person-photo" />
                        <span className="case-person-name">
                          {person.name}
                          {person.alias ? <em> “{person.alias}”</em> : null}
                        </span>
                        <span className="case-person-roles">
                          {person.roles.length
                            ? person.roles.map((role) => (
                                <span key={role} className="tag-stamp small">{role}</span>
                              ))
                            : <span className="tag-stamp small tag-stamp-dim">{t("caseRoleUnrecorded")}</span>}
                        </span>
                      </button>
                      {openPerson === person.id && (
                        <div className="case-person-details">
                          <div className="dossier-row"><span>{t("dateBirth")}</span><span>{person.dob || t("locationNotRecorded")}</span></div>
                          <div className="dossier-row"><span>{t("age")}</span><span>{person.age ?? t("locationNotRecorded")}</span></div>
                          <div className="dossier-row"><span>{t("height")}</span><span>{person.heightCm ? `${person.heightCm} cm` : t("locationNotRecorded")}</span></div>
                          <div className="dossier-row"><span>{t("connectedLocation")}</span><span>{[person.location?.city, person.location?.state].filter(Boolean).join(", ") || t("locationNotRecorded")}</span></div>
                          <div className="dossier-row"><span>{t("status")}</span><span>{person.recordStatus || t("locationNotRecorded")}</span></div>
                          {person.familyKnown && (
                            <div className="dossier-row"><span>{t("familyKnown")}</span><span>{person.familyKnown}</span></div>
                          )}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="dossier-section">
              <h4>{t("caseDocuments")} ({record.documents.length})</h4>
              {record.documents.length === 0 ? (
                <p className="empty-note">{t("caseNoDocuments")}</p>
              ) : (
                <ul className="case-documents">
                  {record.documents.map((doc) => (
                    <li key={doc.id}>
                      <button type="button" className="case-document-name" onClick={() => setViewing(doc)}>
                        {doc.name}
                      </button>
                      <span className="case-document-actions">
                        <button type="button" className="link-remove" onClick={() => setViewing(doc)}>
                          {t("viewOriginal")}
                        </button>
                        <button type="button" className="link-remove"
                          onClick={() => navigate(`/documents/${doc.id}/review`)}>
                          {t("review")}
                        </button>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {record.relatedCases.length > 0 && (
              <div className="dossier-section">
                <h4>{t("caseRelated")}</h4>
                <p className="empty-note">{t("caseRelatedNote")}</p>
                {record.relatedCases.map((related) => (
                  <div className="dossier-row" key={related.id}>
                    <button type="button" className="case-related-link"
                      onClick={() => navigate(`/case/${encodeURIComponent(related.id)}`)}>
                      {related.reference}{related.crime ? ` — ${related.crime}` : ""}
                    </button>
                    <span>{related.sharedPeople.join(", ")}</span>
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
          <CaseSummary
            summary={record.summary}
            generating={summarising}
            error={summaryError}
            onGenerate={handleGenerateSummary}
            onOpenSource={(documentId) => {
              const doc = record.documents.find((item) => item.id === documentId);
              if (doc) setViewing(doc);
            }}
          />

          <div className="graph-toolbar">
            <button type="button" className="graph-analysis-btn" onClick={() => navigate(`/analysis/${encodeURIComponent(id)}`)}>
              {t("addToAnalysis")}
            </button>
          </div>

          <div className="graph-frame">
            {network ? (
              <RelationGraph
                key={id}
                mainCriminal={{ id: record.id, name: record.reference }}
                network={network}
                onNodeClick={(caseId) => navigate(`/case/${encodeURIComponent(caseId)}`)}
                height={520}
              />
            ) : (
              <p className="empty-note">{t("caseNoNetwork")}</p>
            )}
          </div>
        </div>
      </div>

      {viewing && (
        <DocumentViewer
          documentId={viewing.id}
          name={viewing.name}
          mimeType={viewing.mimeType}
          onClose={() => setViewing(null)}
        />
      )}
    </div>
  );
}

export default CaseFile;
