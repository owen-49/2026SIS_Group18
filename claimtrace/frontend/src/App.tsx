import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { AuditPage } from "./pages/AuditPage";
import { DocsPage } from "./pages/DocsPage";
import { ExtensionSetupPage } from "./pages/ExtensionSetupPage";
import { VerifyPage } from "./pages/VerifyPage";

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/audit" replace />} />
        <Route path="library" element={<Navigate to="/audit" replace />} />
        <Route path="upload" element={<Navigate to="/audit" replace />} />
        <Route path="audit" element={<AuditPage key="audit" example />} />
        <Route path="audit/example" element={<AuditPage key="audit-similar" example similarExample />} />
        <Route path="verify" element={<VerifyPage key="verify" example />} />
        <Route path="verify/example" element={<VerifyPage key="verify-similar" example similarExample />} />
        <Route path="extension-setup" element={<ExtensionSetupPage />} />
        <Route path="docs" element={<DocsPage />} />
      </Route>
    </Routes>
  );
}
