// src/pages/JournalEntriesPage.jsx

import { useEffect, useState } from "react";
import axiosClient from "../api/axiosClient";
import ReportLayout from "../components/layout/ReportLayout";

export default function JournalEntriesPage() {
  const [entries, setEntries] = useState([]);

  useEffect(() => {
    axiosClient
      .get("/accounting/journals/")
      .then((res) => setEntries(res.data));
  }, []);

  return (
    <ReportLayout>
      <h1 className="text-xl font-semibold mb-4">
        Journal Entries
      </h1>

      <table className="min-w-full border text-sm">
        <thead>
          <tr>
            <th className="border p-2">Date</th>
            <th className="border p-2">Description</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((j) => (
            <tr key={j.id}>
              <td className="border p-2">{j.created_at}</td>
              <td className="border p-2">{j.description}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </ReportLayout>
  );
}
