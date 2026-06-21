import { useState } from "react";

const FOOD = [
  ["vegetarian", "Vegetarian"], ["non_vegetarian", "Non-vegetarian"],
  ["vegan", "Vegan"], ["jain", "Jain"],
];
const HOTELS = [
  ["budget", "Budget"], ["standard", "Standard"],
  ["premium", "Premium"], ["luxury", "Luxury"],
];
const CURRENCIES = ["INR", "USD", "EUR", "GBP", "AED", "SGD", "THB", "JPY", "AUD", "CHF"];
const LANGS = [
  ["en", "English"], ["hi", "Hindi"], ["mr", "Marathi"], ["fr", "French"],
  ["de", "German"], ["es", "Spanish"], ["ja", "Japanese"], ["ar", "Arabic"],
];
const INTERESTS = [
  "nature", "adventure", "shopping", "food",
  "heritage", "nightlife", "family", "religious", "wildlife",
];

const DEFAULTS = {
  source_country: "India",
  source_city: "Pune",
  destination_country: "UAE",
  destination_city: "Dubai",
  start_date: "",
  duration_days: 4,
  travelers: 2,
  budget_amount: 120000,
  budget_currency: "INR",
  food_preference: "vegetarian",
  hotel_category: "premium",
  language: "en",
  interests: ["heritage", "food", "shopping"],
};

export default function TripForm({ onSubmit, loading }) {
  const [f, setF] = useState(DEFAULTS);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));

  const toggleInterest = (i) =>
    set("interests", f.interests.includes(i)
      ? f.interests.filter((x) => x !== i)
      : [...f.interests, i]);

  const submit = () => {
    const payload = {
      ...f,
      duration_days: Number(f.duration_days),
      travelers: Number(f.travelers),
      budget_amount: Number(f.budget_amount),
      start_date: f.start_date || null,
    };
    onSubmit(payload);
  };

  return (
    <aside className="panel form-panel">
      <h2>Plan a trip</h2>
      <p className="sub">Fill in the details — the planner builds a costed, day-wise itinerary with live weather, food, transport and visa guidance.</p>

      <div className="row">
        <div className="field">
          <label>From (country)</label>
          <input value={f.source_country} onChange={(e) => set("source_country", e.target.value)} />
        </div>
        <div className="field">
          <label>To (country)</label>
          <input value={f.destination_country} onChange={(e) => set("destination_country", e.target.value)} />
        </div>
      </div>

      <div className="row">
        <div className="field">
          <label>From (city)</label>
          <input value={f.source_city} placeholder="e.g. Pune"
                 onChange={(e) => set("source_city", e.target.value)} />
        </div>
        <div className="field">
          <label>To (city)</label>
          <input value={f.destination_city} placeholder="real city, e.g. Sydney"
                 onChange={(e) => set("destination_city", e.target.value)} />
        </div>
      </div>

      <div className="row">
        <div className="field">
          <label>Start date</label>
          <input type="date" value={f.start_date} onChange={(e) => set("start_date", e.target.value)} />
        </div>
        <div className="field">
          <label>Nights</label>
          <input type="number" min="1" max="60" value={f.duration_days} onChange={(e) => set("duration_days", e.target.value)} />
        </div>
      </div>

      <div className="row">
        <div className="field">
          <label>Travelers</label>
          <input type="number" min="1" max="20" value={f.travelers} onChange={(e) => set("travelers", e.target.value)} />
        </div>
        <div className="field">
          <label>Language</label>
          <select value={f.language} onChange={(e) => set("language", e.target.value)}>
            {LANGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
      </div>

      <div className="row-3">
        <div className="field">
          <label>Budget</label>
          <input type="number" min="1" value={f.budget_amount} onChange={(e) => set("budget_amount", e.target.value)} />
        </div>
        <div className="field">
          <label>Currency</label>
          <select value={f.budget_currency} onChange={(e) => set("budget_currency", e.target.value)}>
            {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
      </div>

      <div className="row">
        <div className="field">
          <label>Food</label>
          <select value={f.food_preference} onChange={(e) => set("food_preference", e.target.value)}>
            {FOOD.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div className="field">
          <label>Hotel</label>
          <select value={f.hotel_category} onChange={(e) => set("hotel_category", e.target.value)}>
            {HOTELS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
      </div>

      <div className="field">
        <label>Interests</label>
        <div className="chips">
          {INTERESTS.map((i) => (
            <span key={i} className="chip" data-on={f.interests.includes(i)} onClick={() => toggleInterest(i)}>
              {i}
            </span>
          ))}
        </div>
      </div>

      <button className="submit" onClick={submit} disabled={loading}>
        {loading ? "Building your plan…" : "Build itinerary"}
      </button>
    </aside>
  );
}
