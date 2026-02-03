import React from "react";
import "./App.css";

function App() {
  return (
    <div className="App">
      <header className="App-header">
        <h1>ChatPesa Dashboard</h1>
        <p>API Status: ONLINE ✅</p>
        <table>
          <thead>
            <tr>
              <th>Order ID</th>
              <th>Name</th>
              <th>Phone</th>
              <th>Amount</th>
              <th>Status</th>
              <th>Created At</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>CP123456</td>
              <td>WhatsApp User</td>
              <td>+254722275271</td>
              <td>10</td>
              <td className="paid">PAID</td>
              <td>2026-01-28</td>
            </tr>
            <tr>
              <td>CP654321</td>
              <td>Wyckyaustin</td>
              <td>+254722275272</td>
              <td>100</td>
              <td className="pending">PENDING</td>
              <td>2026-01-27</td>
            </tr>
          </tbody>
        </table>
      </header>
    </div>
  );
}

export default App;
