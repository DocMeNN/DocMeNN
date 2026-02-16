// src/pages/Patients.jsx

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../lib/apiClient";

import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function Patients() {
  const [search, setSearch] = useState("");

  // ---------------------------------------------
  // Load patients from API using React Query
  // ---------------------------------------------
  const { data: patients = [], isLoading } = useQuery({
    queryKey: ["patients"],
    queryFn: async () => await apiClient("/patients/"),
  });

  const filtered = patients.filter((p) =>
    p.name.toLowerCase().includes(search.toLowerCase())
  );

  if (isLoading) return <p className="p-4">Loading patients...</p>;

  return (
    <div className="p-6 space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl font-bold">Patient Records</CardTitle>
        </CardHeader>

        <CardContent className="space-y-6">
          {/* Search + Register */}
          <div className="flex gap-4">
            <Input
              className="flex-1"
              placeholder="Search patient by name..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <Button
              className="w-[200px]"
              onClick={() => alert("Patient registration will be added next")}
            >
              + Register Patient
            </Button>
          </div>

          {/* Patient List */}
          <div className="grid gap-4">
            {filtered.map((p) => (
              <Card key={p.id} className="border-l-4 border-blue-600">
                <CardContent className="p-4 flex justify-between items-center">
                  <div>
                    <p className="font-bold text-lg">{p.name}</p>
                    <p className="text-sm text-gray-600">
                      Patient ID: {p.patient_id}
                    </p>
                  </div>

                  <div className="flex gap-2">
                    <Button variant="outline">View</Button>
                    <Button>Consult</Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          {filtered.length === 0 && (
            <p className="text-gray-500 text-sm">
              No matching patients found...
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
