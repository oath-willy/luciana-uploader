import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Home from './pages/Home';
import Explorer from './pages/Explorer';
import StorageBrowser from './pages/FileBrowser';
import AuthDebug from "./pages/AuthDebug";


function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/explorer" element={<Explorer />} />
        <Route path="/storage-browser" element={<StorageBrowser />} />
        <Route path="/auth-debug" element={<AuthDebug />} />
      </Routes>
    </Router>
  );
}

export default App;