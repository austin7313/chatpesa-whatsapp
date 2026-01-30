import React, { useEffect, useState } from "react";
import "./App.css";

const BACKEND_URL = "https://chatpesa-whatsapp.onrender.com"; // Replace if different

function App() {
  const [orders, setOrders] = useState([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  const fetchOrders = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${BACKEND_URL}/orders`);
      const data = await res.json();
      setOrders(data);
      setLoading(false);
    } catch (err) {
      console.error("Error fetching orders:", err);
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOrders();
    const interval = setInterval(fetchOrders, 10000); // refresh every 10s
    return () => clearInterval(interval);
  }, []);

  const filteredOrders = orders.filter(
    (o) =>
      o.id.toLowerCase().includes(search.toLowerCase()) ||
      (o.name && o.name.toLowerCase().includes(search.toLowerCase())) ||
      (o.phone && o.phone.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <div className="App">
      <header>
        <h1>ChatPesa Dashboard</h1>
        {loading && <p style={{ color: "red" }}>API LOADING...</p>}
      </header>

      <div style={{ marginBottom: "1rem" }}>
        <input
          type="text"
          placeholder="Search by Order ID, Name or Phone..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ padding: "0.5rem", width: "300px" }}
        />
      </div>

      <table>
        <thead>
          <tr>
            <th>Order ID</th>
            <th>Name</th>
            <th>Phone</th>
            <th>Amount</th>
            <th>Status</th>
            <th>Receipt</th>
            <th>Service Requested</th>
            <th>Created At</th>
          </tr>
        </thead>
        <tbody>
          {filteredOrders.length === 0 && (
            <tr>
              <td colSpan="8" style={{ textAlign: "center" }}>
                {loading ? "Loading..." : "No orders found"}
              </td>
            </tr>
          )}
          {filteredOrders.map((order) => (
            <tr key={order.id}>
              <td>{order.id}</td>
              <td>{order.name}</td>
              <td>{order.phone}</td>
              <td>KES {order.amount}</td>
              <td>
                <span
                  style={{
                    padding: "0.25rem 0.5rem",
                    borderRadius: "4px",
                    color: "white",
                    backgroundColor:
                      order.status === "PAID" ? "green" : "orange",
                  }}
                >
                  {order.status}
                </span>
              </td>
              <td>{order.receipt || "—"}</td>
              <td>{order.service || "—"}</td>
              <td>{new Date(order.created_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default App;
