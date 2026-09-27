import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import Navbar from "./components/Navbar";
import RequireAuth from "./components/RequireAuth";
import LandingPage from "./pages/LandingPage";
import LoginPage from "./pages/LoginPage";
import Dashboard from "./pages/Dashboard";
import CaseRegister from "./pages/CaseRegister";
import CaseFile from "./pages/CaseFile";
import UploadDoc from "./pages/UploadDoc";
import DocumentReview from "./pages/DocumentReview";
import AdminPanel from "./pages/AdminPanel";
import InvestigatorAnalysis from "./pages/InvestigatorAnalysis";
import "./App.css";
import { LanguageProvider } from "./i18n";

const NO_NAVBAR_PATHS = ["/", "/login", "/admin"];

function AppLayout() {
  const location = useLocation();
  const showNavbar = !NO_NAVBAR_PATHS.includes(location.pathname);

  return (
    <>
      {showNavbar && <Navbar />}
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />

        <Route element={<RequireAuth />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/search" element={<CaseRegister />} />
          <Route path="/case/:id" element={<CaseFile />} />
          <Route path="/analysis/:id" element={<InvestigatorAnalysis />} />
          <Route path="/analysis" element={<InvestigatorAnalysis />} />
          <Route path="/upload" element={<UploadDoc />} />
          <Route path="/documents/:id/review" element={<DocumentReview />} />
          <Route path="/cases" element={<CaseRegister />} />
          <Route path="/admin" element={<AdminPanel />} />
        </Route>
      </Routes>
    </>
  );
}

function App() {
  return (
    <LanguageProvider><BrowserRouter><AppLayout /></BrowserRouter></LanguageProvider>
  );
}

export default App;
