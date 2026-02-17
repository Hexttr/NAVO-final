import { Outlet, NavLink } from "react-router-dom";
import { useState, useEffect } from "react";
import { getStats } from "../../api";
import "./AdminLayout.css";

const NAV_ITEMS = [
  { path: "songs", label: "Песни / DJ" },
  { path: "news", label: "Новости" },
  { path: "weather", label: "Погода" },
  { path: "podcasts", label: "Подкасты" },
  { path: "intros", label: "ИНТРО" },
];

export default function AdminLayout() {
  const [stats, setStats] = useState(null);
  const [selectedDate, setSelectedDate] = useState(() => {
    const d = new Date();
    return d.toISOString().slice(0, 10);
  });
  useEffect(() => {
    const fetchStats = () => getStats().then(setStats).catch(() => setStats({}));
    fetchStats();
    const interval = setInterval(fetchStats, 10000); // обновление каждые 10 сек
    return () => clearInterval(interval);
  }, []);

  const today = new Date().toISOString().slice(0, 10);

  return (
    <div className="admin-layout">
      <header className="admin-header">
        <h1 className="admin-logo">NAVO RADIO</h1>
        <div className="admin-header-right">
          <input
            type="date"
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="date-picker"
          />
        </div>
      </header>

      <nav className="admin-dashboard">
        <NavLink to="/admin" end className={({ isActive }) => `nav-tile ${isActive ? "active" : ""}`}>
          <span className="nav-tile-label">Сетка эфира</span>
          <span className="nav-tile-count">—</span>
        </NavLink>
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.path}
            to={`/admin/${item.path}`}
            className={({ isActive }) => `nav-tile ${isActive ? "active" : ""}`}
          >
            <span className="nav-tile-label">{item.label}</span>
            <span className="nav-tile-count">{(stats && stats[item.path]) ?? "—"}</span>
          </NavLink>
        ))}
      </nav>

      <main className="admin-main">
        <Outlet context={{ selectedDate, setSelectedDate }} />
      </main>
    </div>
  );
}
