import React, { useEffect, useState } from "react";

function App() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadOrders = async () => {
    try {
      const res = await fetch("/orders");
      if (!res.ok) throw new Error("Failed to fetch orders");
      const data = await res.json();
      setOrders(data.orders || []);
      setLoading(false);
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  };

  useEffect(() => {
    loadOrders();
    const interval = setInterval(loadOrders, 5000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return <div style={styles.center}>Loading dashboard…</div>;
  }

  if (error) {
    return <div style={{ ...styles.center, color: "red" }}>{error}</div>;
  }

  return (
    <div style={styles.container}>
      <h1 style={styles.title}>ChatPesa Dashboard</h1>

      <table style={styles.table}>
        <thead>
          <tr>
            <th>ID</th>
            <th>Phone</th>
            <th>Amount</th>
            <th>Status</th>
            <th>Mpesa Receipt</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {orders.length === 0 && (
            <tr>
              <td colSpan="6" style={styles.empty}>
                No orders yet
              </td>
            </tr>
          )}

          {orders.map((o) => (
            <tr key={o.id}>
              <td>{o.id}</td>
              <td>{o.phone}</td>
              <td>KES {o.amount}</td>
              <td
                style={{
                  color:
                    o.status === "PAID"
                      ? "green"
                      : o.status === "FAILED"
                      ? "red"
                      : "orange",
                }}
              >
                {o.status}
              </td>
              <td>{o.mpesa_receipt || "-"}</td>
              <td>{new Date(o.created_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const styles = {
  container: {
    padding: "20px",
    fontFamily: "Arial, sans-serif",
  },
  title: {
    marginBottom: "20px",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
  },
  empty: {
    textAlign: "center",
    padding: "20px",
  },
  center: {
    padding: "40px",
    textAlign: "center",
    fontFamily: "Arial, sans-serif",
  },
};

export default App;
