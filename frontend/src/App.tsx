import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Home from './pages/Home';
import Explorer from './pages/Explorer';
import StorageBrowser from './pages/FileBrowser';
import AuthDebug from "./pages/AuthDebug";
import Login from './pages/Login';
import { RequireAuth } from "./components/RequireAuth";



function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={ <RequireAuth><Home /></RequireAuth> } />
        <Route path="/explorer" element={ <RequireAuth><Explorer /></RequireAuth> } />
        <Route path="/storage-browser" element={ <RequireAuth><StorageBrowser /></RequireAuth> } />
        <Route path="/auth-debug" element={ <RequireAuth><AuthDebug /></RequireAuth> } />
        <Route path="/login" element={<Login />} />
      </Routes>
    </Router>
  );
}

export default App;