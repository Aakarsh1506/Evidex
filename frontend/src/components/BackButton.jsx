import { useNavigate } from "react-router-dom";
import { useTranslation } from "../i18n";
import "./BackButton.css";

function BackButton({ to = "/dashboard", label }) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  return (
    <button className="back-button" onClick={() => navigate(to)}>
      {label || `← ${t("backToDashboard")}`}
    </button>
  );
}

export default BackButton;