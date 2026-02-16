// src/layouts/CustomerLayout.jsx

import { Outlet, Link, useParams } from "react-router-dom";

export default function CustomerLayout() {
  const { storeId } = useParams();

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link to="/store" className="text-lg font-semibold">
              Online Store
            </Link>

            {storeId && (
              <span className="text-xs px-2 py-1 rounded-full border bg-gray-50 text-gray-700">
                Store: <span className="font-mono">{storeId}</span>
              </span>
            )}
          </div>

          <div className="flex items-center gap-3 text-sm">
            {/* ✅ Staff/Home entry point (public users will land on login/role redirect) */}
            <Link
              to="/"
              className="px-3 py-2 rounded-md border hover:bg-gray-50"
              title="Go to staff home / login"
            >
              Home
            </Link>

            {storeId ? (
              <>
                <Link
                  to={`/store/${storeId}/shop`}
                  className="px-3 py-2 rounded-md border hover:bg-gray-50"
                >
                  Shop
                </Link>
                <Link
                  to={`/store/${storeId}/cart`}
                  className="px-3 py-2 rounded-md border hover:bg-gray-50"
                >
                  Cart
                </Link>
              </>
            ) : (
              <Link
                to="/store"
                className="px-3 py-2 rounded-md border hover:bg-gray-50"
              >
                Choose Store
              </Link>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto p-6">
        <Outlet />
      </main>
    </div>
  );
}
