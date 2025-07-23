import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { createTheme, MantineProvider } from '@mantine/core';

//Components
import { RequireAuth } from "./components/RequireAuth";

//Pages
import Home from './pages/Home';
import StorageBrowser from './pages/FileBrowser';
import AuthDebug from "./pages/AuthDebug";
import Login from './pages/Login';
import DoubleNavbar from "./pages/AdminDashboardPage_old";

const theme = createTheme({
  /* opzionale: aggiungi qui le tue personalizzazioni */
});


function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<RequireAuth><Home /></RequireAuth>} />        
        <Route path="/login" element={<Login />} />        
        <Route path="/storage-browser" element={<RequireAuth><StorageBrowser /></RequireAuth>} />
        <Route path="/admin" element={
          <MantineProvider
            theme={theme}
            defaultColorScheme="light"
            withCssVariables
          >
            <RequireAuth>
              <DoubleNavbar />
            </RequireAuth>
          </MantineProvider>
          } />
        <Route path="/auth-debug" element={<RequireAuth><AuthDebug /></RequireAuth>} />
      </Routes>
    </Router>    
  );
}

export default App;
