import { NavLink, useNavigate } from "react-router-dom";
import { logout } from "../api/auth";
import { clearWorkspace } from "../utils/investigatorWorkspace";
import logo from "../assets/evidex-logo.png";
import "./Navbar.css";
import { useTranslation } from "../i18n";
import LanguageToggle from "./LanguageToggle";

const NAV_LINKS = [
  { key: "home", path: "/dashboard" },
  { key: "caseRecords", path: "/cases" },
  { key: "uploadDoc", path: "/upload" },
  { key: "investigatorAnalysis", path: "/analysis" },
];

function Navbar() {
  const navigate = useNavigate();
  const { t, language, setLanguage } = useTranslation();

  const handleLogout = async () => {
    await logout();
    clearWorkspace();
    navigate("/login");
  };

  return (
    <nav className="navbar">
      <div className="navbar-brand">
        <img src={logo} alt="Evidex logo" className="navbar-logo" />
        <span className="navbar-title">EVIDEX</span>
          <LanguageToggle value={language} onChange={setLanguage} />
      </div>

      <ul className="navbar-links">
        {NAV_LINKS.map((link) => (
          <li key={link.path}>
            <NavLink
              to={link.path}
              className={({ isActive }) =>
                isActive ? "navbar-link active" : "navbar-link"
              }
            >
              {t(link.key)}
            </NavLink>
          </li>
        ))}
        <li>
          <button type="button" className="navbar-logout" onClick={handleLogout}>
            {t("logOut")}
          </button>
        </li>
        <li>

        </li>
      </ul>
    </nav>
  );
}

export default Navbar;
