import { useAuth } from "../context/AuthContext";

export default function Header() {
  const { user, logout } = useAuth();

  return (
    <header className="bg-blue-600 text-white p-4 flex justify-between items-center">
      <h1 className="text-xl font-bold">Me-Medics Pharmacy</h1>

      {user ? (
        <div className="flex items-center gap-4">
          <span className="font-semibold">Role: {user.role}</span>
          <button
            onClick={logout}
            className="bg-red-500 px-3 py-1 rounded hover:bg-red-600"
          >
            Logout
          </button>
        </div>
      ) : (
        <span className="opacity-80">Not logged in</span>
      )}
    </header>
  );
}
