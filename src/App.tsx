import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";
import { UploadPage } from "./pages/UploadPage";

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/upload" element={<UploadPage />} />
        <Route path="*" element={<Navigate to="/upload" />} />
      </Routes>
    </Router>
  );
}

export default App;
