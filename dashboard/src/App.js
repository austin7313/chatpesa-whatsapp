import React, { useState, useEffect } from "react";
import "./App.css";

function App() {
  const [orders, setOrders] = useState([]);

  const fetchOrders = async () => {
    try {
      const res = await fetch("/orders");
      const data = await res.json();
      if (data.status === "ok") {
        setOrders(data.orders);
      }
    } catch (err) {
      console.error("Failed to fetch orders:", err);
    }
  };

  useEffect(() => {
    fetchOrders();
    const interval = setInterval(fetchOrders, 5000); // refresh every 5s
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="App">
      <h1>ChatPesa Dashboard</h1>
      <table>
        <thead>
          <tr>
            <th>Order ID</th>
            <th>Customer</th>
            <th>Phone</th>
            <th>Service 🎯</th>
            <th>Amount (KES)</th>
            <th>Receipt 🧾</th>
            <th>Status</th>
            <th>Paid At</th>
          </tr>
        </thead>
        <tbody>
          {orders.length === 0 ? (
            <tr>
              <td colSpan="8" style={{ textAlign: "center" }}>
                No orders yet
              </td>
            </tr>
          ) : (
            orders.map((order) => (
              <tr
                key={order.id}
                className={order.status === "PAID" ? "paid-row" : ""}
              >
                <td>{order.id}</td>
                <td>{order.customer_name || "—"}</td>
                <td>{order.phone}</td>
                <td>{order.service_requested || "—"}</td>
                <td>{order.amount}</td>
                <td>{order.mpesa_receipt || "—"}</td>
                <td>{order.status}</td>
                <td>
                  {order.paid_at
                    ? new Date(order.paid_at).toLocaleString()
                    : "—"}
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
