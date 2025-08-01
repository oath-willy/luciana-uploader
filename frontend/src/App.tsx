import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';

//Components
import { RequireAuth } from "./components/RequireAuth";

//Pages
import Home from './pages/Home';
import StorageBrowser from './pages/FileBrowser';
import AuthDebug from "./pages/AuthDebug";
import Login from './pages/Login';
import AdminDashboardPage  from "./pages/Navigator";

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<RequireAuth><Home /></RequireAuth>} />        
        <Route path="/login" element={<Login />} />        
        <Route path="/storage-browser" element={<RequireAuth><StorageBrowser /></RequireAuth>} />
        <Route path="/navigator/*" element={
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
