import React from "react"; // <--- AGGIUNGI QUESTO
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";
import { MsalProvider, useIsAuthenticated } from "@azure/msal-react";
import { PublicClientApplication } from "@azure/msal-browser";
import { msalConfig } from "./auth/msalConfig";
import { LoginPage } from "./pages/LoginPage";
import { UploadPage } from "./pages/UploadPage";
import { MantineProvider } from "@mantine/core";

const msalInstance = new PublicClientApplication(msalConfig);

console.log("App loaded");

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
      <MantineProvider>
        <Router>
          <AppRoutes />
        </Router>
      </MantineProvider>
    </MsalProvider>
  );
}

export default App;