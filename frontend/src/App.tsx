import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Home from './pages/Home';
import Explorer from './pages/Explorer';
import FluentUI from './pages/FluentUI';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/explorer" element={<Explorer />} />
        <Route path="/fluentui" element={<FluentUI />} />
      </Routes>
    </Router>
  );
}

export default App;