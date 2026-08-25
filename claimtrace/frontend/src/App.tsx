import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { AuditPage } from "./pages/AuditPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DocsPage } from "./pages/DocsPage";
import { ExtensionSetupPage } from "./pages/ExtensionSetupPage";
import { LibraryPage } from "./pages/LibraryPage";
import { VerifyPage } from "./pages/VerifyPage";

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<DashboardPage />} />
        <Route path="library" element={<LibraryPage />} />
        <Route path="upload" element={<Navigate to="/library?upload=1" replace />} />
        <Route path="verify" element={<VerifyPage />} />
        <Route path="audit" element={<AuditPage />} />
        <Route path="extension-setup" element={<ExtensionSetupPage />} />
        <Route path="docs" element={<DocsPage />} />
      </Route>
    </Routes>
  );
}
