import React, { useEffect, useState } from "react";

const API_URL = "https://chatpesa-whatsapp.onrender.com";

function App() {
  const [orders, setOrders] = useState([]);
  const [apiStatus, setApiStatus] = useState("CHECKING");
  const [error, setError] = useState("");

  const fetchOrders = async () => {
    try {
      const res = await fetch(`${API_URL}/orders`, {
        method: "GET",
        headers: { "Content-Type": "application/json" },
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const data = await res.json();
      setOrders(data);
      setApiStatus("ONLINE");
      setError("");
    } catch (err) {
      console.error("API FETCH ERROR:", err);
      setApiStatus("OFFLINE");
      setError("Backend not reachable");
    }
  };

  useEffect(() => {
    fetchOrders();
    const i = setInterval(fetchOrders, 5000);
    return () => clearInterval(i);
  }, []);

  const badge = (status) => {
    const map = {
      PAID: "#16a34a",
      FAILED: "#dc2626",
      PENDING: "#facc15",
    };
    return (
      <span
        style={{
          background: map[status] || "#facc15",
          padding: "4px 10px",
          borderRadius: 12,
          fontWeight: "bold",
          fontSize: 12,
        }}
      >
        {status || "PENDING"}
      </span>
    );
  };

  return (
    <div style={{ padding: 20, fontFamily: "Arial" }}>
      <h2>💳 ChatPesa Dashboard</h2>

      <p>
        API Status:{" "}
        <strong style={{ color: apiStatus === "ONLINE" ? "green" : "red" }}>
          {apiStatus}
        </strong>
      </p>

      {error && <p style={{ color: "red" }}>{error}</p>}

      <table width="100%" cellPadding="10" style={{ borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "#111", color: "#fff" }}>
            <th>ID</th>
            <th>Name</th>
            <th>Phone</th>
            <th>Amount</th>
            <th>Status</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {orders.length === 0 ? (
            <tr>
              <td colSpan="6" style={{ textAlign: "center" }}>
                No orders yet
              </td>
            </tr>
          ) : (
            orders.map((o) => (
              <tr key={o.id}>
                <td>{o.id}</td>
                <td>{o.name || "WhatsApp User"}</td>
                <td>{o.phone}</td>
                <td>KES {o.amount}</td>
                <td>{badge(o.status)}</td>
                <td>
                  {o.created_at
                    ? new Date(o.created_at).toLocaleString()
                    : "-"}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export default App;
