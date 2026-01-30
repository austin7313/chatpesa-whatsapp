import React, { useEffect, useState } from "react";
import "./App.css";

const API_URL = "https://chatpesa-whatsapp.onrender.com"; // 🔹 Your Render backend

function App() {
  const [orders, setOrders] = useState([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  // Fetch orders
  const fetchOrders = async () => {
    try {
      const res = await fetch(`${API_URL}/orders`);
      const data = await res.json();
      setOrders(data);
      setLoading(false);
    } catch (err) {
      console.error("❌ Failed to fetch orders:", err);
      setOrders([]);
      setLoading(false);
    }
  };

  // Fetch initially and poll every 5s
  useEffect(() => {
    fetchOrders();
    const interval = setInterval(fetchOrders, 5000);
    return () => clearInterval(interval);
  }, []);

  // Filter orders
  const filteredOrders = orders.filter(
    (o) =>
      o.id.toLowerCase().includes(search.toLowerCase()) ||
      o.name.toLowerCase().includes(search.toLowerCase()) ||
      o.phone.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="App">
      <header>
        <h1>ChatPesa Dashboard</h1>
        <p className={`api-status ${loading ? "offline" : "online"}`}>
          API Status: {loading ? "OFFLINE ❌" : "ONLINE ✅"}
        </p>
        <input
          type="text"
          placeholder="Search by Order ID, Name or Phone..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </header>

      <main>
        <table>
          <thead>
            <tr>
              <th>Order ID</th>
              <th>Name</th>
              <th>Phone</th>
              <th>Amount</th>
              <th>Status</th>
              <th>Created At</th>
              <th>Receipt</th>
              <th>🎯 Service Requested</th>
            </tr>
          </thead>
          <tbody>
            {filteredOrders.length === 0 ? (
              <tr>
                <td colSpan="8">No orders found</td>
              </tr>
            ) : (
              filteredOrders.map((order) => (
                <tr key={order.id}>
                  <td>{order.id}</td>
                  <td>{order.name}</td>
                  <td>{order.phone}</td>
                  <td>{order.amount}</td>
                  <td>
                    <span
                      className={
                        order.status.toLowerCase() === "paid"
                          ? "status paid"
                          : "status pending"
                      }
                    >
                      {order.status.toUpperCase()}
                    </span>
                  </td>
                  <td>{new Date(order.created_at).toLocaleString()}</td>
                  <td>{order.receipt || "-"}</td>
                  <td>{order.service || "-"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </main>
    </div>
  );
}

export default App;
