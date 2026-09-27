import { useEffect, useState } from "react";
import { useTranslation } from "../i18n";
import { useNavigate } from "react-router-dom";
import { fetchCurrentOfficer, logout } from "../api/auth";
import { fetchOfficers, createOfficer, deactivateOfficer } from "../api/officers";
import "./AdminPanel.css";

const EMPTY_FORM = { username: "", password: "", name: "", dob: "", orgName: "" };

function EyeIcon({ open }) {
  return open ? (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  ) : (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M17.94 17.94A10.94 10.94 0 0 1 12 19c-7 0-11-7-11-7a18.6 18.6 0 0 1 4.22-5.06M9.9 4.24A10.9 10.9 0 0 1 12 4c7 0 11 7 11 7a18.6 18.6 0 0 1-2.16 3.19M14.12 14.12a3 3 0 1 1-4.24-4.24" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  );
}

function AdminPanel() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [checking, setChecking] = useState(true);
  const [officers, setOfficers] = useState([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [showPassword, setShowPassword] = useState(false);
  const [status, setStatus] = useState("idle"); // idle | saving | error | success
  const [error, setError] = useState(null);

  const loadOfficers = () => {
    fetchOfficers().then(setOfficers).catch(() => setOfficers([]));
  };

  useEffect(() => {
    let cancelled = false;
    fetchCurrentOfficer().then((officer) => {
      if (cancelled) return;
      if (!officer || officer.role !== "admin") {
        navigate("/dashboard", { replace: true });
        return;
      }
      setChecking(false);
      loadOfficers();
    });
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((f) => ({ ...f, [name]: value }));
    if (status === "error" || status === "success") setStatus("idle");
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setStatus("saving");
    setError(null);
    try {
      await createOfficer(form);
      setForm(EMPTY_FORM);
      setShowPassword(false);
      setStatus("success");
      loadOfficers();
    } catch (err) {
      setError(err.message);
      setStatus("error");
    }
  };

  const handleDeactivate = async (officerId) => {
    try {
      await deactivateOfficer(officerId);
      loadOfficers();
    } catch (err) {
      console.error("Failed to deactivate officer", err);
    }
  };

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  if (checking) return null;

  return (
    <div className="admin-page">
      <header className="admin-top">
        <div>
          <span className="admin-badge">ADMIN</span>
          <h2>{t("adminAccounts")}</h2>
        </div>
        <button type="button" className="stamp-btn small" onClick={handleLogout}>
          Log out
        </button>
      </header>

      <div className="admin-grid">
        <form className="admin-form" onSubmit={handleSubmit}>
          <h3>{t("adminAddOfficer")}</h3>

          <label>
            {t("adminUsername")}
            <input name="username" value={form.username} onChange={handleChange} required />
          </label>

          <label>
            {t("loginPassword")}
            <div className="password-field">
              <input
                type={showPassword ? "text" : "password"}
                name="password"
                value={form.password}
                onChange={handleChange}
                required
                minLength={8}
              />
              <button
                type="button"
                className="eye-toggle"
                onClick={() => setShowPassword((s) => !s)}
                tabIndex={-1}
                aria-label={t(showPassword ? "adminHidePassword" : "adminShowPassword")}
              >
                <EyeIcon open={showPassword} />
              </button>
            </div>
          </label>

          <label>
            {t("adminFullName")}
            <input name="name" value={form.name} onChange={handleChange} required />
          </label>

          <label>
            {t("adminDob")}
            <input type="date" name="dob" value={form.dob} onChange={handleChange} />
          </label>

          <label>
            {t("loginOrganisation")}
            <input name="orgName" value={form.orgName} onChange={handleChange} required />
          </label>

          <button type="submit" className="stamp-btn full-width" disabled={status === "saving"}>
            {status === "saving" ? t("adminSaving") : t("adminCreate")}
          </button>

          {status === "success" && <p className="admin-success">{t("adminCreated")}</p>}
          {status === "error" && <p className="admin-error">{error}</p>}
        </form>

        <div className="admin-list">
          <h3>{t("adminExisting")}</h3>
          {officers.length === 0 ? (
            <p className="empty-note">{t("adminNoOfficers")}</p>
          ) : (
            <table className="admin-table">
              <thead>
                <tr>
                  <th>{t("adminId")}</th>
                  <th>{t("adminName")}</th>
                  <th>{t("adminOrg")}</th>
                  <th>{t("status")}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {officers.map((o) => (
                  <tr key={o.officer_id} className={o.is_active ? "" : "row-inactive"}>
                    <td>{o.username}</td>
                    <td>{o.name}</td>
                    <td>{o.org_name}</td>
                    <td>
                      <span className={`tag-stamp ${o.is_active ? "" : "tag-stamp-dim"}`}>
                        {t(o.is_active ? "adminActive" : "adminDeactivated")}
                      </span>
                    </td>
                    <td>
                      {o.is_active && (
                        <button type="button" className="link-remove" onClick={() => handleDeactivate(o.officer_id)}>
                          {t("adminDeactivate")}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

export default AdminPanel;