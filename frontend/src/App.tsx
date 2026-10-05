import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';

//Components
import { RequireAuth } from "./components/RequireAuth";

//Pages
import AuthDebug from "./pages/AuthDebug";
import Login from './pages/Login';
import AdminDashboardPage  from "./pages/Navigator";

function LegacyNavigatorRedirect() {
  const { pathname, search, hash } = useLocation();
  const destination = pathname.replace(/^\/navigator(?=\/|$)/, '') || '/';
  return <Navigate to={`${destination}${search}${hash}`} replace />;
}

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/login" element={<Login />} />        
        <Route path="/storage-browser" element={<Navigate to="/file-browser-bronze" replace />} />
        <Route path="/navigator/*" element={<LegacyNavigatorRedirect />} />
        <Route path="/*" element={
          <RequireAuth>
            <AdminDashboardPage />
          </RequireAuth>
        } />
        <Route path="/auth-debug" element={<RequireAuth><AuthDebug /></RequireAuth>} />
      </Routes>
    </Router>    
  );
}

export default App;
