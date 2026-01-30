import React, { useEffect, useState } from "react";

const API_URL = "https://chatpesa-whatsapp.onrender.com";

function App() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchOrders();
    const interval = setInterval(fetchOrders, 5000);
    return () => clearInterval(interval);
  }, []);

  const fetchOrders = async () => {
    try {
      const res = await fetch(`${API_URL}/orders`);
      const data = await res.json();
      setOrders(data);
    } catch (err) {
      console.error("Failed to fetch orders", err);
    } finally {
      setLoading(false);
    }
  };

  const statusStyle = (status) => {
    if (status === "PAID") {
      return { background: "#16a34a", color: "white" };
    }
    if (status === "FAILED") {
      return { background: "#dc2626", color: "white" };
    }
    return { background: "#facc15", color: "black" }; // PENDING
  };

  return (
    <div style={{ padding: 20, fontFamily: "Arial" }}>
      <h2>💳 ChatPesa Dashboard</h2>

      {loading ? (
        <p>Loading orders…</p>
      ) : (
        <table width="100%" cellPadding="10" style={{ borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "#111", color: "#fff" }}>
              <th>Order ID</th>
              <th>Name</th>
              <th>Phone</th>
              <th>Service</th>
              <th>Amount</th>
              <th>Mpesa Receipt</th>
              <th>Status</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((o) => (
              <tr key={o.id} style={{ borderBottom: "1px solid #ddd" }}>
                <td>{o.id}</td>
                <td>{o.name || "WhatsApp User"}</td>
                <td>{o.phone}</td>
                <td>{o.service || "-"}</td>
                <td>KES {o.amount}</td>
                <td style={{ fontWeight: "bold" }}>
                  {o.mpesa_receipt || "—"}
                </td>
                <td>
                  <span
                    style={{
                      ...statusStyle(o.status),
                      padding: "4px 10px",
                      borderRadius: 12,
                      fontSize: 12,
                      fontWeight: "bold",
                    }}
                  >
                    {o.status}
                  </span>
                </td>
                <td>{new Date(o.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default App;
