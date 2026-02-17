import { useOutletContext, useNavigate } from "react-router-dom";
import "./Dashboard.css";

export default function Dashboard() {
  const { selectedDate } = useOutletContext();
  const navigate = useNavigate();

  return (
    <div className="dashboard">
      <h2>Главная</h2>
      <p className="dashboard-desc">
        Выберите дату в шапке и перейдите в «Сетка эфира» для генерации расписания на день.
      </p>
      <button className="primary" onClick={() => navigate("/admin/broadcast")}>
        Перейти к сетке эфира
      </button>
    </div>
  );
}
