// src/pages/ConsultationPage.jsx
import { useState, useEffect } from "react";
import { apiClient } from "../lib/apiClient";

export default function ConsultationPage() {
  const [patients, setPatients] = useState([]);
  const [form, setForm] = useState({
    patient_id: "",
    symptoms: "",
    diagnosis: "",
    treatment: "",
  });

  useEffect(() => {
    async function loadPatients() {
      try {
        const data = await apiClient("/patients/");
        setPatients(data);
      } catch (err) {
        alert("Failed to load patients.");
      }
    }
    loadPatients();
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    try {
      await apiClient("/consultations/create/", {
        method: "POST",
        body: JSON.stringify(form),
      });
      alert("Consultation saved!");
      setForm({ patient_id: "", symptoms: "", diagnosis: "", treatment: "" });
    } catch (err) {
      alert("Failed to save consultation.");
    }
  };

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h1 className="text-xl font-bold mb-4">Consultation</h1>

      <form className="space-y-4" onSubmit={submit}>
        <select
          name="patient_id"
          className="w-full border p-2 rounded"
          value={form.patient_id}
          onChange={(e) => setForm({ ...form, patient_id: e.target.value })}
        >
          <option value="">Select Patient</option>
          {patients.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} - {p.unique_id}
            </option>
          ))}
        </select>

        <textarea
          name="symptoms"
          className="w-full border p-2 rounded"
          placeholder="Symptoms..."
          value={form.symptoms}
          onChange={(e) => setForm({ ...form, symptoms: e.target.value })}
        />

        <textarea
          name="diagnosis"
          className="w-full border p-2 rounded"
          placeholder="Diagnosis..."
          value={form.diagnosis}
          onChange={(e) => setForm({ ...form, diagnosis: e.target.value })}
        />

        <textarea
          name="treatment"
          className="w-full border p-2 rounded"
          placeholder="Prescriptions / Treatment..."
          value={form.treatment}
          onChange={(e) => setForm({ ...form, treatment: e.target.value })}
        />

        <button className="bg-blue-600 w-full text-white py-2 rounded">
          Save Consultation
        </button>
      </form>
    </div>
  );
}
