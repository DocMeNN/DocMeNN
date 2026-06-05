export default function DashboardLayout({ children }) {
  return (
    <div>
      <header>Dashboard Header</header>
      <main>{children}</main>
    </div>
  );
}
