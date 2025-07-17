import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Home from './pages/Home';
import Explorer from './pages/Explorer';
import StorageBrowser from './pages/FileBrowser';


function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/explorer" element={<Explorer />} />
        <Route path="/storage-browser" element={<StorageBrowser />} />
      </Routes>
    </Router>
  );
}

export default App;