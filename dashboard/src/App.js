import React, { useEffect, useState } from "react";
import axios from "axios";
import "./App.css";

const API_URL = "https://chatpesa-whatsapp.onrender.com"; // <-- Your Flask backend

function App() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);

  // Fetch orders from backend
  const fetchOrders = async () => {
    try {
      const res = await axios.get(`${API_URL}/orders`);
      if (res.data && res.data.orders) {
        setOrders(res.data.orders);
      }
      setLoading(false);
    } catch (error) {
      console.error("Error fetching orders:", error);
      setLoading(false);
    }
  };

  // Auto-refresh every 5 seconds
  useEffect(() => {
    fetchOrders();
    const interval = setInterval(fetchOrders, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="App">
      <header className="App-header">
        <h1>ChatPesa Dashboard</h1>
      </header>
      <main>
        {loading ? (
          <p>Loading orders...</p>
        ) : orders.length === 0 ? (
          <p>No orders found</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Customer</th>
                <th>Phone</th>
                <th>Amount</th>
                <th>Status</th>
                <th>MPESA Receipt</th>
                <th>Created At</th>
                <th>Paid At</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order) => (
                <tr key={order.id}>
                  <td>{order.id}</td>
                  <td>{order.customer_name}</td>
                  <td>{order.phone}</td>
                  <td>{order.amount}</td>
                  <td>{order.status}</td>
                  <td>{order.mpesa_receipt || "—"}</td>
                  <td>{order.created_at}</td>
                  <td>{order.paid_at || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </main>
    </div>
  );
}

export default App;
