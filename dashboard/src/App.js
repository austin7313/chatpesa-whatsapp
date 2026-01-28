import React, { useEffect, useState } from "react";
import "./App.css";

function App() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchOrders = async () => {
    try {
      const res = await fetch("/orders");
      const data = await res.json();
      if (data.status === "ok") {
        setOrders(data.orders);
      }
    } catch (err) {
      console.error("Error fetching orders:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOrders();

    // Poll every 5 seconds for live updates
    const interval = setInterval(fetchOrders, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="App">
      <h1>ChatPesa Dashboard</h1>
      {loading ? (
        <p>Loading orders...</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Customer</th>
              <th>Phone</th>
              <th>Amount</th>
              <th>Service Requested</th>
              <th>Status</th>
              <th>MPESA Receipt</th>
              <th>Created At</th>
              <th>Paid At</th>
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
                <td>{order.service_requested}</td>
                <td>{order.status}</td>
                <td>{order.mpesa_receipt || "-"}</td>
                <td>{new Date(order.created_at).toLocaleString()}</td>
                <td>
                  {order.paid_at
                    ? new Date(order.paid_at).toLocaleString()
                    : "-"}
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
