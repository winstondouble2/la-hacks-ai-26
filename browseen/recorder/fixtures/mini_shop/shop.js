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

// A cookie wall for testing optional steps. It shows only with ?banner=1 and until
// consent is stored, and covers the page until a button is clicked.
function maybeShowCookieBanner() {
  if (new URLSearchParams(location.search).get("banner") !== "1" || localStorage.getItem("consent")) return;
  const wall = document.createElement("div");
  wall.id = "cookie-banner";
  wall.setAttribute("role", "dialog");
  wall.setAttribute("aria-modal", "true");
  wall.setAttribute("aria-label", "Cookie consent");
  wall.style.cssText =
    "position:fixed;inset:0;z-index:10;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.6)";
  wall.innerHTML =
    '<div style="background:#fff;padding:24px;max-width:360px">' +
    "<p>We use cookies to run this shop.</p>" +
    '<button type="button" data-choice="all">Accept all</button> ' +
    '<button type="button" data-choice="none">Reject all</button></div>';
  wall.addEventListener("click", (event) => {
    const choice = event.target.dataset && event.target.dataset.choice;
    if (!choice) return;
    localStorage.setItem("consent", choice);
    wall.remove();
  });
  document.body.appendChild(wall);
}

document.addEventListener("DOMContentLoaded", maybeShowCookieBanner);
