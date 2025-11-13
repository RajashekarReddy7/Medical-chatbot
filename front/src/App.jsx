import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Chat from "./pages/Chat";
import Login from "./pages/Login";
import Home from "./pages/Home";
import SummaryView from "./pages/SummaryView";

function App() {
  return (
    <BrowserRouter>
      <Routes>

        {/* 🔥 Default route should go to Home */}
        <Route path="/" element={<Navigate to="/home" replace />} />

        {/* Your pages */}
        <Route path="/home" element={<Home />} />
        <Route path="/login" element={<Login />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="/summary/:id" element={<SummaryView />} />

      </Routes>
    </BrowserRouter>
  );
}

export default App;
