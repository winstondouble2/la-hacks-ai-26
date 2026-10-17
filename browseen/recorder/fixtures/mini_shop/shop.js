// Shared data and cart helpers for the mini shop fixture.
const PRODUCTS = [
  { id: "blue-mug", name: "Blue Mug", price: 12 },
  { id: "red-kettle", name: "Red Kettle", price: 35 },
  { id: "green-plate", name: "Green Plate", price: 9 },
];

function findProduct(id) {
  return PRODUCTS.find((p) => p.id === id);
}

function getCart() {
  return JSON.parse(localStorage.getItem("cart") || "[]");
}

function setCart(cart) {
  localStorage.setItem("cart", JSON.stringify(cart));
}
