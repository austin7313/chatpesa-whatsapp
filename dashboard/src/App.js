import React, { useEffect, useState } from "react";
import "./App.css";

function App() {
  const [orders, setOrders] = useState([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  const fetchOrders = async () => {
    try {
      const res = await fetch(`${process.env.REACT_APP_API_URL || "http://localhost:5000"}/orders`);
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
    const interval = setInterval(fetchOrders, 5000); // refresh every 5 sec
    return () => clearInterval(interval);
  }, []);

  const filteredOrders = orders.filter(
    (o) =>
      o.id.toLowerCase().includes(search.toLowerCase()) ||
      o.customer_name?.toLowerCase().includes(search.toLowerCase()) ||
      o.phone?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="App">
      <h1>ChatPesa Dashboard</h1>
      {loading ? <p>Loading orders...</p> : null}
      <input
        type="text"
        placeholder="Search by Order ID, Name or Phone..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="search-input"
      />

      <table>
        <thead>
          <tr>
            <th>Order ID</th>
            <th>Name</th>
            <th>Phone</th>
            <th>Amount</th>
            <th>Status</th>
            <th>Receipt</th>
            <th>Created At</th>
          </tr>
        </thead>
        <tbody>
          {filteredOrders.map((order) => (
            <tr key={order.id}>
              <td>{order.id}</td>
              <td>{order.customer_name || "Unknown"}</td>
              <td>{order.phone}</td>
              <td>KES {order.amount}</td>
              <td>
                <span
                  className={`status-badge ${
                    order.status?.toLowerCase() === "paid" ? "paid" : "pending"
                  }`}
                >
                  {order.status}
                </span>
              </td>
              <td>{order.receipt || "-"}</td>
              <td>{new Date(order.created_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default App;
