import { Outlet, NavLink } from "react-router-dom";
import { useState, useEffect } from "react";
import { Radio, Calendar, LayoutGrid, Music, Newspaper, CloudSun, Podcast, Mic } from "lucide-react";
import { getStats } from "../../api";
import "./AdminLayout.css";

const NAV_ITEMS = [
  { path: "", label: "Сетка эфира", icon: LayoutGrid, countKey: null },
  { path: "songs", label: "Песни / DJ", icon: Music, countKey: "songs" },
  { path: "news", label: "Новости", icon: Newspaper, countKey: "news" },
  { path: "weather", label: "Погода", icon: CloudSun, countKey: "weather" },
  { path: "podcasts", label: "Подкасты", icon: Podcast, countKey: "podcasts" },
  { path: "intros", label: "Интро", icon: Mic, countKey: "intros" },
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
    const interval = setInterval(fetchStats, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="admin-layout">
      <header className="admin-header">
        <div className="admin-comets">
          <span className="comet" style={{ animationDelay: "0s" }} />
          <span className="comet" style={{ animationDelay: "3s" }} />
          <span className="comet" style={{ animationDelay: "6s" }} />
          <span className="comet" style={{ animationDelay: "2s" }} />
          <span className="comet" style={{ animationDelay: "5s" }} />
        </div>
        <div className="admin-header-logo">
          <div className="admin-logo-icon">
            <Radio size={20} color="#fff" />
          </div>
          <div>
            <h1 className="admin-logo-text">NAVO RADIO</h1>
            <span className="admin-logo-sub">Admin Panel</span>
          </div>
        </div>

        <div className="admin-date-wrap">
          <Calendar size={16} className="admin-date-icon" />
          <input
            type="date"
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="admin-date-picker"
          />
        </div>
      </header>

      <nav className="admin-nav-tabs">
        {NAV_ITEMS.map((item) => {
          const to = `/admin${item.path ? `/${item.path}` : ""}`;
          const count = item.countKey ? (stats?.[item.countKey] ?? "—") : null;
          const Icon = item.icon;

          return (
            <NavLink
              key={item.path || "grid"}
              to={to}
              end={item.path === ""}
              className={({ isActive }) =>
                `admin-nav-tab ${isActive ? "active" : ""}`
              }
            >
              <Icon size={16} />
              <span>{item.label}</span>
              {count !== null && (
                <span className="admin-nav-tab-count">{count}</span>
              )}
            </NavLink>
          );
        })}
      </nav>

      <main className="admin-main">
        <Outlet context={{ selectedDate, setSelectedDate }} />
      </main>
    </div>
  );
}
