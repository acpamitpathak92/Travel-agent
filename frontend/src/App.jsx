import { useState } from "react";
import TripForm from "./components/TripForm.jsx";
import Results from "./components/Results.jsx";
import { generatePlan } from "./api.js";

export default function App() {
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [theme, setTheme] = useState("dark");

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
  };

  const onSubmit = async (payload) => {
    setLoading(true);
    setError("");
    try {
      const result = await generatePlan(payload);
      setPlan(result);
    } catch (e) {
      setError(e.message || "Something went wrong. Is the backend running on :8000?");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="mark">Voy<em>a</em>ge</span>
          <span className="tag">AI travel planner</span>
        </div>
        <button className="theme-toggle" onClick={toggleTheme}>
          {theme === "dark" ? "☼ Light" : "☾ Dark"}
        </button>
      </header>

      <div className="grid">
        <TripForm onSubmit={onSubmit} loading={loading} />

        <main className="results">
          {error && <div className="card" style={{ borderColor: "var(--coral)" }}>
            <strong style={{ color: "var(--coral)" }}>Couldn’t build the plan.</strong>
            <p className="narr" style={{ marginTop: 8 }}>{error}</p>
          </div>}

          {loading && (
            <div className="placeholder">
              <div className="loader">
                <span className="spinner" />
                Researching destination, pricing the trip, checking weather, food, transport & visa…
              </div>
            </div>
          )}

          {!loading && !plan && !error && (
            <div className="placeholder">
              <div className="big">Your itinerary appears here</div>
              Fill in the trip details and select “Build itinerary”.
            </div>
          )}

          {!loading && plan && <Results plan={plan} />}
        </main>
      </div>
    </div>
  );
}
