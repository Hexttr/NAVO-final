import { Outlet, NavLink, useLocation } from "react-router-dom";
import { useState, useEffect, useRef } from "react";
import { Radio, Calendar, LayoutGrid, Music, Newspaper, CloudSun, Podcast, Mic, ArrowUp, Settings as SettingsIcon } from "lucide-react";
import { getStats, moscowDateStr } from "../../api";
import "./AdminLayout.css";

const NAV_ITEMS = [
  { path: "", label: "Сетка эфира", icon: LayoutGrid, countKey: null },
  { path: "songs", label: "Песни / DJ", icon: Music, countKey: "songs" },
  { path: "news", label: "Новости", icon: Newspaper, countKey: "news" },
  { path: "weather", label: "Погода", icon: CloudSun, countKey: "weather" },
  { path: "podcasts", label: "Подкасты", icon: Podcast, countKey: "podcasts" },
  { path: "intros", label: "Интро", icon: Mic, countKey: "intros" },
  { path: "settings", label: "Настройки", icon: SettingsIcon, countKey: null },
];

export default function AdminLayout() {
  const mainRef = useRef(null);
  const location = useLocation();
  const [stats, setStats] = useState(null);
  const [showScrollTop, setShowScrollTop] = useState(false);
  const [selectedDate, setSelectedDate] = useState(() => moscowDateStr());

  useEffect(() => {
    const fetchStats = () => getStats().then(setStats).catch(() => setStats({}));
    fetchStats();
    const interval = setInterval(fetchStats, 10000);
    return () => clearInterval(interval);
  }, []);

  const scrollToTop = () => {
    mainRef.current?.scrollTo({ top: 0, behavior: "smooth" });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  useEffect(() => {
    const el = mainRef.current;
    const check = () => {
      const mainCanScroll = el ? el.scrollHeight > el.clientHeight : false;
      const mainScrolled = el ? el.scrollTop > 50 : false;
      const docCanScroll = document.documentElement.scrollHeight > window.innerHeight;
      const docScrolled = window.scrollY > 50;
      const visible = (mainCanScroll && mainScrolled) || (docCanScroll && docScrolled);
      setShowScrollTop(visible);
    };

    const runCheck = () => requestAnimationFrame(check);
    runCheck();
    setTimeout(runCheck, 100);
    setTimeout(runCheck, 500);
    setTimeout(runCheck, 1500);

    el?.addEventListener("scroll", check);
    window.addEventListener("scroll", check, { passive: true });

    const ro = el ? new ResizeObserver(runCheck) : null;
    el && ro?.observe(el);

    const interval = setInterval(check, 1000);
    return () => {
      el?.removeEventListener("scroll", check);
      window.removeEventListener("scroll", check);
      ro?.disconnect();
      clearInterval(interval);
    };
  }, [location.pathname]);

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

      <main
        ref={mainRef}
        className="admin-main"
        onScroll={() => {
          const el = mainRef.current;
          if (!el) return;
          const canScroll = el.scrollHeight > el.clientHeight;
          const scrolled = el.scrollTop > 50;
          setShowScrollTop(canScroll && scrolled);
        }}
      >
        <Outlet context={{ selectedDate, setSelectedDate }} />
      </main>

      {showScrollTop && (
        <button
          type="button"
          className="scroll-to-top-btn"
          onClick={scrollToTop}
          aria-label="Наверх"
        >
          <ArrowUp size={22} />
        </button>
      )}
    </div>
  );
}
