import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../api/auth";
import { useTranslation } from "../i18n";
import "./LoginPage.css";

const STEPS = [
  { key: "username", label: "loginOfficerId", type: "text", prompt: "loginPromptId" },
  { key: "password", label: "loginPassword", type: "password", prompt: "loginPromptPassword" },
];

function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [form, setForm] = useState({ username: "" });
  const [officer, setOfficer] = useState(null); // set on successful login, shown on the back face
  const [stepIndex, setStepIndex] = useState(0);
  const [value, setValue] = useState("");
  const [status, setStatus] = useState("idle"); // "idle" | "checking" | "denied" | "flipped"

  const step = STEPS[stepIndex];
  const isLastStep = stepIndex === STEPS.length - 1;

  const handleChange = (e) => {
    setValue(e.target.value);
    if (status === "denied") setStatus("idle");
  };

  const handleSubmitStep = async (e) => {
    e.preventDefault();
    if (!value.trim() || status === "checking") return;

    if (isLastStep) {
      setStatus("checking");
      try {
        const result = await login(form.username, value);
        setOfficer(result);
        setStatus("flipped"); // triggers the page-turn reveal, waits for "Enter"
      } catch {
        setStatus("denied");
      } finally {
        setValue(""); // never keep the password around longer than needed
      }
      return;
    }

    setForm((f) => ({ ...f, [step.key]: value }));
    setValue("");
    setStepIndex((i) => i + 1);
  };

  const handleEnter = () => navigate(officer?.role === "admin" ? "/admin" : "/dashboard");
  const handleBack = () => navigate("/");

  const statusLabel =
    status === "denied"
      ? t("loginAccessDenied")
      : status === "checking"
        ? t("loginVerifyingCaps")
        : `${t("loginAwaiting")} ${t(step.label).toUpperCase()}`;

  // The hint line shown below the input — echoes the officer ID as it's
  // typed, or a character count while entering the password.
  const inputHint =
    step.key === "username"
      ? value
        ? `${t("loginIdLogged")}: ${value.toUpperCase()}`
        : t("loginAwaitingInput")
      : value
        ? `${value.length} ${t("loginCharsEntered")}`
        : t("loginAwaitingInput");

  return (
    <div className="login-page">
      <button type="button" className="back-btn" onClick={handleBack}>
        ← {t("back")}
      </button>

      <div className={`case-flip-wrapper ${status === "flipped" ? "is-flipped" : ""}`}>
        <div className="case-flip-inner">

          {/* FRONT — the unlock steps */}
          <div className={`case-face case-face-front ${status === "denied" ? "status-denied" : ""}`}>
            <div className="case-meta">
              <div className="case-meta-left">
                <div className="meta-row"><span>{t("loginCaseId")}</span><span>: {t("loginOfficerAccess")}</span></div>
                <div className="meta-row"><span>{t("loginClassification")}</span><span>: <em className="hot">{t("loginTopSecret")}</em> / LEVEL S</span></div>
                <div className="meta-row"><span>{t("loginPriority")}</span><span>: {t("loginAbsolute")}</span></div>
                <div className="meta-row">
                  <span>{t("loginStatus")}</span>
                  <span>: <em className={status === "denied" ? "hot" : "pending"}>{statusLabel}</em></span>
                </div>
                <div className="meta-row"><span>{t("loginFileType")}</span><span>: {t("loginOfficerAccess")}</span></div>
              </div>

              <div className="scales-box">
                <svg viewBox="0 0 64 64" width="32" height="32" fill="none" stroke="#d1453c" strokeWidth="2">
                  <path
                    d="M32 6v40M14 18h36M14 18l-8 16h16l-8-16zM50 18l-8 16h16l-8-16zM20 54h24"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                <p>{t("loginMotto")}</p>
              </div>
            </div>

            <div className="subject-block">
              <div className="subject-photo">
                <span className="tape" aria-hidden="true" />
                <svg viewBox="0 0 100 120" width="100%" height="100%">
                  <rect width="100" height="120" fill="#0c0c0c" />
                  <circle cx="50" cy="42" r="20" fill="#1c1c1c" />
                  <path d="M15 118c2-28 20-40 35-40s33 12 35 40z" fill="#1c1c1c" />
                </svg>
                <span className="stamp stamp-photo">{t(status === "denied" ? "loginDenied" : "loginUnverified")}</span>
              </div>

              <div className="subject-info">
                <p className="subject-label">{t("loginSubject")}</p>
                <p className="subject-name">{form.username ? form.username.toUpperCase() : t("loginUnknown")}</p>

                <p className="subject-line"><span>{t("loginOfficerId").toUpperCase()}</span>{form.username || t("loginUnknown")}</p>
                <p className="subject-line"><span>{t("loginClearance")}</span><em className="hot">{t("loginPending")}</em></p>
              </div>
            </div>

            <form className="unlock-form" onSubmit={handleSubmitStep}>
              <label className="unlock-label">
                {t(step.prompt)}
                <input
                  type={step.type}
                  value={value}
                  onChange={handleChange}
                  autoFocus
                  required
                  disabled={status === "checking"}
                />
              </label>

              <p className="input-hint">{inputHint}</p>

              <div className="button-row">
                <button type="submit" className="unlock-btn" disabled={status === "checking"}>
                  {status === "checking" ? t("loginVerifying") : isLastStep ? t("loginUnlock") : t("loginContinue")}
                </button>
              </div>

              {status === "denied" && <p className="denied-text">{t("loginDeniedNote")}</p>}
            </form>

            <div className="warning-strip">
              <span className="warn-icon">!</span>
              <p>{t("loginWarning")}</p>
              <span className="lock-icon" aria-hidden="true">🔒</span>
            </div>
          </div>

          {/* BACK — confirmation, revealed by the page turn. Everything here
              comes from the server's response, not from what was typed in. */}
          <div className="case-face case-face-back">
            <div className="seal" aria-hidden="true">
              <span>CNA</span>
            </div>
            <h2 className="back-title">Criminal Network Analysis</h2>
            <p className="back-subtitle">{t("loginConfirmed")}</p>

            <div className="back-summary">
              <div className="summary-row"><span>{t("loginOfficerName")}</span><span>{officer?.name}</span></div>
              <div className="summary-row"><span>{t("loginOfficerId")}</span><span>{officer?.username}</span></div>
              <div className="summary-row"><span>{t("loginOrganisation")}</span><span>{officer?.orgName}</span></div>
              <div className="summary-row"><span>{t("loginRole")}</span><span>{officer?.role}</span></div>
            </div>

            <div className="button-row">
              <button type="button" className="enter-btn" onClick={handleEnter}>
                {t("loginEnter")}
              </button>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}

export default LoginPage;