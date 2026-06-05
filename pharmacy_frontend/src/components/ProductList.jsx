export default function ProductList({ products, setSelectedProduct }) {
  return (
    <div className="bg-white rounded shadow p-4 h-[70vh] overflow-y-auto">
      <h2 className="font-semibold text-lg mb-3">Products</h2>

      <ul className="space-y-2">
        {products.map((p) => (
          <li
            key={p.id}
            onClick={() => setSelectedProduct(p)}
            className="p-3 bg-gray-100 rounded hover:bg-blue-100 cursor-pointer flex justify-between"
          >
            <span>{p.name}</span>
            <span className="font-bold">₦{p.price}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
