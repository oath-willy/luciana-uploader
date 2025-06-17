import React from "react"; // <--- AGGIUNGI QUESTO
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";
import { MsalProvider, useIsAuthenticated } from "@azure/msal-react";
import { PublicClientApplication } from "@azure/msal-browser";
import { msalConfig } from "./auth/msalConfig";
import { LoginPage } from "./pages/LoginPage";
import { UploadPage } from "./pages/UploadPage";

const msalInstance = new PublicClientApplication(msalConfig);

const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const isAuthenticated = useIsAuthenticated();
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />;
};

const AppRoutes = () => (
  <Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route
      path="/upload"
      element={
        <ProtectedRoute>
          <UploadPage />
        </ProtectedRoute>
      }
    />
    <Route path="*" element={<Navigate to="/upload" />} />
  </Routes>
);

function App() {
  return (
    <MsalProvider instance={msalInstance}>
      <Router>
        <AppRoutes />
      </Router>
    </MsalProvider>
  );
}

export default App;