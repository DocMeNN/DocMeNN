// src/pages/Dashboard.jsx

import { useAuth } from "../context/AuthContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useNavigate } from "react-router-dom";

export default function Dashboard() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();

  if (loading) return <p className="p-4">Loading dashboard...</p>;
  if (!user) return <p className="p-4">Not authenticated</p>;

  const role = user.role;

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-3xl font-bold">
        Welcome, {user.username}{" "}
        <span className="text-blue-600 text-xl">({role})</span>
      </h1>

      {/* ================================
          ADMIN DASHBOARD (NAV HUB)
      ================================= */}
      {role === "admin" && (
        <div className="grid md:grid-cols-3 gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Admin Dashboard</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground mb-3">
                Overview of operations, finance, and system activity
              </p>
              {/* IMPORTANT: adjust route if your admin dashboard is different */}
              <Button className="w-full" onClick={() => navigate("/admin")}>
                Open Admin Overview
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>User Management</CardTitle>
            </CardHeader>
            <CardContent>
              <Button className="w-full" onClick={() => navigate("/admin/users")}>
                View Users
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Online Store</CardTitle>
            </CardHeader>
            <CardContent>
              {/* ✅ This is NOT inventory management; it is your storefront */}
              <Button className="w-full" onClick={() => navigate("/store")}>
                Open Store
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Reports</CardTitle>
            </CardHeader>
            <CardContent>
              <Button className="w-full" onClick={() => navigate("/accounting")}>
                View Reports
              </Button>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ================================
          PHARMACIST DASHBOARD
      ================================= */}
      {role === "pharmacist" && (
        <div className="grid md:grid-cols-3 gap-6">
          <Card>
            <CardHeader>
              <CardTitle>POS</CardTitle>
            </CardHeader>
            <CardContent>
              <Button className="w-full" onClick={() => navigate("/pos")}>
                Open POS
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Online Store</CardTitle>
            </CardHeader>
            <CardContent>
              <Button className="w-full" onClick={() => navigate("/store")}>
                Open Store
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Expired Products</CardTitle>
            </CardHeader>
            <CardContent>
              <Button className="w-full" disabled>
                Check Expiry
              </Button>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ================================
          CASHIER DASHBOARD
      ================================= */}
      {role === "cashier" && (
        <div className="grid md:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Point of Sale</CardTitle>
            </CardHeader>
            <CardContent>
              <Button className="w-full" onClick={() => navigate("/pos")}>
                Open POS
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Sales History</CardTitle>
            </CardHeader>
            <CardContent>
              <Button className="w-full" onClick={() => navigate("/sales")}>
                View Sales
              </Button>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ================================
          RECEPTION DASHBOARD
      ================================= */}
      {role === "reception" && (
        <div className="grid md:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Register Patient</CardTitle>
            </CardHeader>
            <CardContent>
              <Button
                className="w-full"
                onClick={() => navigate("/patients/register")}
              >
                New Patient
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Search Patient</CardTitle>
            </CardHeader>
            <CardContent>
              <Button className="w-full" onClick={() => navigate("/patients")}>
                Find Records
              </Button>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ================================
          MEDICAL STAFF DASHBOARD
      ================================= */}
      {role === "medical" && (
        <div className="grid md:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Consult Patient</CardTitle>
            </CardHeader>
            <CardContent>
              <Button className="w-full" onClick={() => navigate("/consult")}>
                Start Consultation
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Patient History</CardTitle>
            </CardHeader>
            <CardContent>
              <Button className="w-full" onClick={() => navigate("/patients")}>
                View History
              </Button>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
