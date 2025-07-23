import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { createTheme } from '@mantine/core';

//Components
import { RequireAuth } from "./components/RequireAuth";

//Pages
import Home from './pages/Home';
import StorageBrowser from './pages/FileBrowser';
import AuthDebug from "./pages/AuthDebug";
import Login from './pages/Login';
import AdminDashboardPage  from "./pages/AdminDashboardPage";

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<RequireAuth><Home /></RequireAuth>} />        
        <Route path="/login" element={<Login />} />        
        <Route path="/storage-browser" element={<RequireAuth><StorageBrowser /></RequireAuth>} />
        <Route path="/admin/*" element={
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
