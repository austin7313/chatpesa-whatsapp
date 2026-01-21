import React, { useEffect, useState } from "react";
import "./App.css"; // optional: your custom CSS

function App() {
  const [orders, setOrders] = useState([]);
  const [apiStatus, setApiStatus] = useState(false); // true = online
  const [loading, setLoading] = useState(true);

  const fetchOrders = async () => {
    try {
      const res = await fetch("https://chatpesa-whatsapp.onrender.com/orders");
      const data = await res.json();

      if (data.status === "ok") {
        setOrders(data.orders || []);
        setApiStatus(true);
      } else {
        setOrders([]);
        setApiStatus(false);
      }
    } catch (err) {
      console.error("Failed to fetch orders:", err);
      setOrders([]);
      setApiStatus(false);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOrders(); // initial load
    const interval = setInterval(fetchOrders, 5000); // refresh every 5 sec
    return () => clearInterval(interval);
  }, []);

  return (
    <div style={{ fontFamily: "Arial, sans-serif", padding: "20px" }}>
      <h1>💳 ChatPesa Dashboard</h1>

      {/* API Status */}
      <div style={{ marginBottom: "20px" }}>
        Status:{" "}
        <span
          style={{
            color: "white",
            padding: "5px 10px",
            borderRadius: "5px",
            backgroundColor: apiStatus ? "green" : "red",
          }}
        >
          {apiStatus ? "ONLINE" : "OFFLINE"}
        </span>
      </div>

      {loading ? (
        <p>Loading orders...</p>
      ) : orders.length === 0 ? (
        <p>No orders yet.</p>
      ) : (
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            boxShadow: "0 2px 8px rgba(0,0,0,0.1)",
          }}
        >
          <thead>
            <tr style={{ backgroundColor: "#f0f0f0" }}>
              <th style={{ padding: "10px", border: "1px solid #ddd" }}>
                Order ID
              </th>
              <th style={{ padding: "10px", border: "1px solid #ddd" }}>
                Name
              </th>
              <th style={{ padding: "10px", border: "1px solid #ddd" }}>
                Items
              </th>
              <th style={{ padding: "10px", border: "1px solid #ddd" }}>
                Amount (KES)
              </th>
              <th style={{ padding: "10px", border: "1px solid #ddd" }}>
                Status
              </th>
              <th style={{ padding: "10px", border: "1px solid #ddd" }}>
                Time
              </th>
            </tr>
          </thead>
          <tbody>
            {orders.map((order) => (
              <tr key={order.id}>
                <td style={{ padding: "10px", border: "1px solid #ddd" }}>
                  {order.id || "—"}
                </td>
                <td style={{ padding: "10px", border: "1px solid #ddd" }}>
                  {order.customer_name || "—"}
                </td>
                <td style={{ padding: "10px", border: "1px solid #ddd" }}>
                  {order.items || "—"}
                </td>
                <td style={{ padding: "10px", border: "1px solid #ddd" }}>
                  KES {order.amount?.toLocaleString() || 0}
                </td>
                <td style={{ padding: "10px", border: "1px solid #ddd" }}>
                  {order.status || "AWAITING_PAYMENT"}
                </td>
                <td style={{ padding: "10px", border: "1px solid #ddd" }}>
                  {new Date(order.created_at).toLocaleString() || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default App;
