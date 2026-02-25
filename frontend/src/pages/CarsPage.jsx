import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { getCars } from "../lib/api";
import { clearToken, getToken } from "../lib/auth";

function formatPrice(value) {
  if (!Number.isFinite(value)) {
    return "-";
  }

  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0
  }).format(value);
}

export default function CarsPage() {
  const navigate = useNavigate();
  const [cars, setCars] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");

  const loadCars = async () => {
    setIsLoading(true);
    setError("");

    const token = getToken();
    if (!token) {
      navigate("/login", { replace: true });
      return;
    }

    try {
      const data = await getCars(token);
      setCars(Array.isArray(data) ? data : []);
    } catch (apiError) {
      if (apiError.status === 401) {
        clearToken();
        navigate("/login", { replace: true });
        return;
      }
      setError(apiError.message || "Unable to load cars.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadCars();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filteredCars = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) {
      return cars;
    }

    return cars.filter((car) => {
      return [car.brand, car.model, car.color, String(car.year)]
        .join(" ")
        .toLowerCase()
        .includes(term);
    });
  }, [cars, query]);

  const onLogout = () => {
    clearToken();
    navigate("/login", { replace: true });
  };

  return (
    <main className="page page-cars">
      <div className="dashboard fade-up">
        <header className="hero">
          <div>
            <p className="kicker">Protected Area</p>
            <h1>Car Inventory Console</h1>
            <p className="hero-subtitle">Review real API data, verify auth, and inspect seeded records instantly.</p>
          </div>

          <div className="hero-actions">
            <button className="secondary" onClick={loadCars} disabled={isLoading}>
              {isLoading ? "Refreshing..." : "Refresh"}
            </button>
            <button className="danger" onClick={onLogout}>
              Logout
            </button>
          </div>
        </header>

        <section className="stats-grid">
          <article>
            <span>Total Cars</span>
            <strong>{cars.length}</strong>
          </article>
          <article>
            <span>Visible Now</span>
            <strong>{filteredCars.length}</strong>
          </article>
          <article>
            <span>Most Common Brand</span>
            <strong>
              {cars.length
                ? Object.entries(
                    cars.reduce((acc, car) => {
                      acc[car.brand] = (acc[car.brand] || 0) + 1;
                      return acc;
                    }, {})
                  ).sort((a, b) => b[1] - a[1])[0]?.[0] || "-"
                : "-"}
            </strong>
          </article>
        </section>

        <section className="table-shell">
          <div className="table-toolbar">
            <label htmlFor="search">Search</label>
            <input
              id="search"
              placeholder="Brand, model, color, year"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>

          {error ? <p className="form-error">{error}</p> : null}

          {isLoading ? <p className="empty-state">Loading cars...</p> : null}
          {!isLoading && filteredCars.length === 0 ? <p className="empty-state">No cars found.</p> : null}

          {!isLoading && filteredCars.length > 0 ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Brand</th>
                    <th>Model</th>
                    <th>Year</th>
                    <th>Price</th>
                    <th>Color</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredCars.map((car, index) => (
                    <tr key={car.link} style={{ animationDelay: `${index * 55}ms` }}>
                      <td>{car.brand}</td>
                      <td>{car.model}</td>
                      <td>{car.year}</td>
                      <td>{formatPrice(car.price)}</td>
                      <td>{car.color}</td>
                      <td>
                        <a href={car.link} target="_blank" rel="noreferrer">
                          Open
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </section>
      </div>
    </main>
  );
}
