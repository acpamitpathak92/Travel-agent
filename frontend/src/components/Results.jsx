// Renders a TravelPlan from the backend. Sections that carry a `source`
// ("live:*" vs "offline") show a badge so it's clear what is real-time.

const fmt = (n) =>
  n == null ? "—" : Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 });

function SourceBadge({ source }) {
  if (!source) return null;
  const live = source.startsWith("live");
  const label = live ? `live · ${source.split(":")[1] || "api"}` : "offline";
  return <span className={`src ${live ? "live" : ""}`}>{label}</span>;
}

function Pass({ plan }) {
  const r = plan.request;
  const c = plan.cost;
  const conf = Math.round((plan.evaluation?.confidence ?? 0) * 100);
  return (
    <div className="pass">
      <div className="route">
        <div>
          <div className="city">{r.source_country}</div>
          <div className="country">origin</div>
        </div>
        <div className="line"><span>✈</span></div>
        <div>
          <div className="city">{r.destination_city}</div>
          <div className="country">{r.destination_country}</div>
        </div>
      </div>
      <div className="meta">
        <div><span className="k">Dates</span><span className="v">{r.start_date || "Flexible"}</span></div>
        <div><span className="k">Nights</span><span className="v">{r.duration_days}</span></div>
        <div><span className="k">Travelers</span><span className="v">{r.travelers}</span></div>
        <div><span className="k">Total</span><span className="v">{fmt(c.total_source)} {c.source_currency}</span></div>
        <div><span className="k">≈ USD</span><span className="v">${fmt(c.total_usd)}</span></div>
      </div>
      <div className="stub">
        <span className={`pill ${c.within_budget ? "ok" : "over"}`}>
          {c.within_budget ? "within budget" : "over budget"}
        </span>
        <span className="pill prov">model · {plan.provider_used}</span>
        <div className="conf">
          <span className="num">confidence</span>
          <div className="bar"><i style={{ width: `${conf}%` }} /></div>
          <span className="num">{conf}%</span>
        </div>
      </div>
    </div>
  );
}

function CostCard({ cost }) {
  return (
    <div className="card wide">
      <h3><span className="ic">◈</span> Cost breakdown</h3>
      {cost.narrative && <p className="narr">{cost.narrative}</p>}
      <table className="cost-tbl">
        <thead>
          <tr><th>Item</th><th>{cost.dest_currency}</th><th>{cost.source_currency}</th><th>USD</th></tr>
        </thead>
        <tbody>
          {cost.lines.map((l) => (
            <tr key={l.label}>
              <td>{l.label}</td>
              <td className="num">{fmt(l.amount_dest)}</td>
              <td className="num">{fmt(l.amount_source)}</td>
              <td className="num">{fmt(l.amount_usd)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td>Total</td>
            <td className="num">—</td>
            <td className="num">{fmt(cost.total_source)}</td>
            <td className="num">{fmt(cost.total_usd)}</td>
          </tr>
        </tfoot>
      </table>
      <div className="fxnote">
        1 {cost.source_currency} = {cost.fx_source_to_dest} {cost.dest_currency} ·
        1 {cost.dest_currency} = {cost.fx_dest_to_usd} USD ·
        daily ≈ {fmt(cost.daily_budget_source)} {cost.source_currency}
      </div>
    </div>
  );
}

function Itinerary({ it }) {
  return (
    <div className="card wide">
      <h3><span className="ic">❖</span> Day-by-day itinerary</h3>
      {it.narrative && <p className="narr">{it.narrative}</p>}
      {it.days.map((d) => (
        <div className="day" key={d.day}>
          <h4>{d.title}</h4>
          <div className="slots">
            {["morning", "afternoon", "evening", "night"].map((s) =>
              d.slots[s]?.length ? (
                <div className="slot" key={s}>
                  <div className="t">{s}</div>
                  <ul>{d.slots[s].map((x, i) => <li key={i}>{x}</li>)}</ul>
                </div>
              ) : null
            )}
          </div>
          {d.est_walking_km ? <div className="walk">≈ {d.est_walking_km} km on foot</div> : null}
        </div>
      ))}
    </div>
  );
}

function Weather({ w }) {
  return (
    <div className="card wide">
      <h3><span className="ic">☼</span> Weather <SourceBadge source={w.source} /></h3>
      {w.narrative && <p className="narr">{w.narrative}</p>}
      <div className="wx">
        {w.days.map((d, i) => (
          <div className="d" key={i}>
            <div className="date">{d.date}</div>
            <div className="temp">{Math.round(d.temp_c)}°</div>
            <div className="rain">☂ {Math.round(d.rain_probability_pct)}%</div>
            <div className="sum">{d.summary}</div>
          </div>
        ))}
      </div>
      {w.aqi != null && <div className="aqi">Air quality index ≈ {w.aqi} (US AQI)</div>}
      {w.source?.includes("seasonal") && (
        <div className="aqi">Seasonal estimate from last year's actuals for these dates.</div>
      )}
    </div>
  );
}

function Visa({ v }) {
  return (
    <div className="card">
      <h3><span className="ic">⊙</span> Visa & advisory <SourceBadge source={v.advisory_source} /></h3>
      {v.narrative && <p className="narr">{v.narrative}</p>}
      <div className="kv"><span className="k">Requirement</span><span className="v">{v.required ? v.visa_type : "Not required"}</span></div>
      <div className="kv"><span className="k">eVisa</span><span className="v">{v.evisa_available ? "Yes" : "No"}</span></div>
      <div className="kv"><span className="k">Processing</span><span className="v">{v.processing_days} days</span></div>
      <div className="kv"><span className="k">Apply by</span><span className="v">{v.recommended_apply_by}</span></div>
      <div className="kv"><span className="k">Fee / traveler</span><span className="v">${fmt(v.fee_per_traveler_usd)}</span></div>
      <div className="kv"><span className="k">Total fee</span><span className="v">${fmt(v.total_fee_usd)}</span></div>
      <div className="sub-h">Documents</div>
      <div className="taglist">{v.required_documents.map((d, i) => <span key={i}>{d}</span>)}</div>
      <div className="sub-h">Advisories</div>
      <ul className="alerts" style={{ margin: 0, paddingLeft: 16 }}>
        {v.advisories.map((a, i) => <li key={i}>{a}</li>)}
      </ul>
    </div>
  );
}

function Food({ food }) {
  return (
    <div className="card">
      <h3><span className="ic">❦</span> Food <SourceBadge source={food.source} /></h3>
      {food.narrative && <p className="narr">{food.narrative}</p>}
      <div className="sub-h">Must try</div>
      <div className="taglist">{food.must_try_dishes.map((d, i) => <span key={i}>{d}</span>)}</div>
      {food.restaurants?.length ? (<>
        <div className="sub-h">Restaurants</div>
        <div className="taglist">{food.restaurants.map((d, i) => <span key={i}>{d}</span>)}</div>
      </>) : null}
      {food.street_food?.length ? (<>
        <div className="sub-h">Street food</div>
        <div className="taglist">{food.street_food.map((d, i) => <span key={i}>{d}</span>)}</div>
      </>) : null}
    </div>
  );
}

function Transport({ t }) {
  return (
    <div className="card">
      <h3><span className="ic">⇄</span> Getting around <SourceBadge source={t.source} /></h3>
      {t.narrative && <p className="narr">{t.narrative}</p>}
      <table className="modes">
        <tbody>
          {t.options.map((o, i) => (
            <tr key={i}>
              <td>{o.mode}</td>
              <td className="n">{o.approx_cost_dest ? `~${o.approx_cost_dest}` : "free"}</td>
              <td className="n">{o.typical_time_min ? `${o.typical_time_min} min` : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Journey({ j }) {
  return (
    <div className="card wide">
      <h3><span className="ic">✈</span> Getting there {j.domestic ? "· domestic" : "· international"}
        <SourceBadge source={j.source} /></h3>
      {j.narrative && <p className="narr">{j.narrative}</p>}
      <div className="meta" style={{ marginBottom: 10, fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--muted)" }}>
        {j.from_label} → {j.to_label}
      </div>
      <table className="modes">
        <thead>
          <tr><th style={{ textAlign: "left" }}>Mode</th><th style={{ textAlign: "left" }}>Option</th><th className="n">Per person</th><th className="n">Time</th><th className="n">Book</th></tr>
        </thead>
        <tbody>
          {j.options.map((o, i) => (
            <tr key={i}>
              <td><strong>{o.mode}</strong></td>
              <td style={{ color: "var(--muted)" }}>{o.name || o.note}</td>
              <td className="n">{o.approx_cost_source ? `~${fmt(o.approx_cost_source)}` : `~$${fmt(o.approx_cost_usd)}`}</td>
              <td className="n">{o.duration_hours ? `${o.duration_hours} h` : "—"}</td>
              <td className="n">{o.booking_url
                ? <a href={o.booking_url} target="_blank" rel="noopener noreferrer"
                     style={{ color: "var(--accent)", textDecoration: "none" }}>Book ↗</a>
                : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {j.airlines?.length ? (
        <div className="fxnote">Airlines: {j.airlines.join(", ")} · flight est. ${fmt(j.flight_estimate_usd)}/person</div>
      ) : null}
    </div>
  );
}

function Hotels({ h, selected }) {
  return (
    <div className="card">
      <h3><span className="ic">⌂</span> Stays {selected ? <span className="src">{selected} selected</span> : null}</h3>
      {h.narrative && <p className="narr">{h.narrative}</p>}
      {h.recommended.map((o, i) => (
        <div className="hotel" key={i}>
          <div className="top">
            <span className="name">{o.name}</span>
            <span className="price">{fmt(o.price_per_night_dest)}/night</span>
          </div>
          <div className="meta">★ {o.rating} · {o.distance_km_to_center} km to center ·
            <strong style={{ color: "var(--accent)", textTransform: "capitalize" }}> {o.category}</strong></div>
          <div className="proscons">
            <div className="p">{o.pros?.join(", ")}</div>
            <div className="c">{o.cons?.join(", ")}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function Packing({ p }) {
  const groups = [
    ["Clothing", p.clothing], ["Footwear", p.footwear], ["Accessories", p.accessories],
    ["Electronics", p.electronics], ["Medicines", p.medicines], ["Documents", p.documents],
  ];
  return (
    <div className="card">
      <h3><span className="ic">▣</span> Packing</h3>
      {p.narrative && <p className="narr">{p.narrative}</p>}
      {groups.map(([t, items]) => items?.length ? (
        <div key={t}>
          <div className="sub-h">{t}</div>
          <div className="taglist">{items.map((x, i) => <span key={i}>{x}</span>)}</div>
        </div>
      ) : null)}
    </div>
  );
}

function Destination({ d }) {
  const Block = ({ title, list }) => list?.length ? (<>
    <div className="sub-h">{title}</div>
    <div className="taglist">{list.map((p, i) => <span key={i}>{p.name || p}</span>)}</div>
  </>) : null;
  return (
    <div className="card">
      <h3><span className="ic">✦</span> Where to go</h3>
      {d.narrative && <p className="narr">{d.narrative}</p>}
      <Block title="Must visit" list={d.must_visit} />
      <Block title="Should visit" list={d.should_visit} />
      <Block title="Hidden gems" list={d.hidden_gems} />
    </div>
  );
}

function Evaluation({ e }) {
  const issues = [...(e.contradictions || []), ...(e.missing || [])];
  return (
    <div className="card wide">
      <h3><span className="ic">✓</span> Plan check</h3>
      {e.caveats?.map((c, i) => <div className="caveat" key={`c${i}`}>{c}</div>)}
      {issues.map((c, i) => <div className="caveat" key={`i${i}`}>{c}</div>)}
      {!e.caveats?.length && !issues.length && (
        <div className="good">No issues flagged. {Math.round(e.confidence * 100)}% confidence.</div>
      )}
    </div>
  );
}

export default function Results({ plan }) {
  return (
    <>
      <Pass plan={plan} />
      <div className="cards">
        <Journey j={plan.journey} />
        <Itinerary it={plan.itinerary} />
        <CostCard cost={plan.cost} />
        <Weather w={plan.weather} />
        <Visa v={plan.visa} />
        <Food food={plan.food} />
        <Transport t={plan.transport} />
        <Hotels h={plan.hotels} selected={plan.request?.hotel_category} />
        <Packing p={plan.packing} />
        <Destination d={plan.destination} />
        <Evaluation e={plan.evaluation} />
      </div>
    </>
  );
}
