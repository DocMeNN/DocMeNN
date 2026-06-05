export default function CustomerLayout({ children }) {
  return (
    <div>
      <header>Storefront</header>
      <main>{children}</main>
    </div>
  );
}
