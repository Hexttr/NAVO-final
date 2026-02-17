import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Player from "./pages/Player";
import AdminLayout from "./pages/admin/AdminLayout";
import SongsDj from "./pages/admin/SongsDj";
import News from "./pages/admin/News";
import Weather from "./pages/admin/Weather";
import Podcasts from "./pages/admin/Podcasts";
import Intros from "./pages/admin/Intros";
import Broadcast from "./pages/admin/Broadcast";
import "./App.css";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Player />} />
        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<Broadcast />} />
          <Route path="songs" element={<SongsDj />} />
          <Route path="news" element={<News />} />
          <Route path="weather" element={<Weather />} />
          <Route path="podcasts" element={<Podcasts />} />
          <Route path="intros" element={<Intros />} />
          <Route path="broadcast" element={<Broadcast />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
