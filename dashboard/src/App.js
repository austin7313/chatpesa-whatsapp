import React, { useEffect, useState } from "react";
import "./App.css";

function App() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);

  // Fetch orders from your Flask API
  const fetchOrders = async () => {
    try {
      const response = await fetch("/orders");
      const data = await response.json();
      setOrders(data.orders || []);
      setLoading(false);
    } catch (err) {
      console.error("Error fetching orders:", err);
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOrders();
    // Optional: refresh every 5 seconds
    const interval = setInterval(fetchOrders, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="App">
      <h1>ChatPesa Dashboard</h1>
      {loading ? (
        <p>Loading orders...</p>
      ) : orders.length === 0 ? (
        <p>No orders found.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Order ID</th>
              <th>Customer</th>
              <th>Phone</th>
              <th>Amount</th>
              <th>Service Requested</th>
              <th>Status</th>
              <th>Created At</th>
              <th>Paid At</th>
              <th>MPESA Receipt</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((order) => (
              <tr
                key={order.id}
                className={order.status === "PAID" ? "paid-row" : ""}
              >
                <td>{order.id}</td>
                <td>{order.customer_name}</td>
                <td>{order.phone}</td>
                <td>{order.amount}</td>
                <td>{order.service_requested || "-"}</td>
                <td>{order.status}</td>
                <td>{new Date(order.created_at).toLocaleString()}</td>
                <td>
                  {order.paid_at
                    ? new Date(order.paid_at).toLocaleString()
                    : "-"}
                </td>
                <td>{order.mpesa_receipt || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default App;
