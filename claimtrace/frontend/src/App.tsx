import { Route, Routes } from "react-router-dom";
import { AuditPage } from "./pages/AuditPage";
import { UploadPage } from "./pages/UploadPage";
import { VerifyPage } from "./pages/VerifyPage";

export function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>ClaimTrace</h1>
        <nav>
          <a href="/">Upload</a>
          <a href="/verify">Verify</a>
          <a href="/audit">Audit</a>
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<UploadPage />} />
          <Route path="/verify" element={<VerifyPage />} />
          <Route path="/audit" element={<AuditPage />} />
        </Routes>
      </main>
    </div>
  );
}
