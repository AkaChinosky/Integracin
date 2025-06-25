const API_BASE = 'http://localhost:5000';

let productos = [];
let usdRate = 0;
const productosContainer = document.getElementById('productosContainer');
const currencySelect = document.getElementById('currencySelect');
const mensajesMostrados = new Set();

async function fetchUSD() {
  try {
    const res = await fetch('https://api.exchangerate.host/latest?base=CLP&symbols=USD');
    const data = await res.json();
    usdRate = data.rates.USD;
  } catch (error) {
    console.error('Error obteniendo tipo de cambio:', error);
    usdRate = 0.0011;
  }
}

function convertirPrecio(precioCLP) {
  return currencySelect.value === 'USD'
    ? `$${(precioCLP * usdRate).toFixed(2)} USD`
    : `$${precioCLP.toLocaleString()} CLP`;
}

async function fetchProductos() {
  const sucursalId = document.getElementById('sucursalSelect').value;
  const res = await fetch(`${API_BASE}/grpc/productos?sucursal_id=${sucursalId}`);
  productos = await res.json();
  await fetchUSD();
  renderProductos();
}

function renderProductos() {
  productosContainer.innerHTML = '';
  productos.forEach(p => {
    const col = document.createElement('div');
    col.className = 'col-md-4';
    col.innerHTML = `
      <div class="card shadow-sm">
        <div class="card-body">
          <h5 class="card-title">${p.nombre}</h5>
          <p class="card-text">Stock disponible: <strong>${p.stock}</strong></p>
          <p class="card-text">Precio: <strong>${convertirPrecio(p.precio)}</strong></p>
          <div class="input-group mb-2">
            <input type="number" class="form-control" min="0" max="${p.stock}" value="0" id="cantidad-${p.id}">
          </div>
        </div>
      </div>
    `;
    productosContainer.appendChild(col);
  });
}

currencySelect.addEventListener('change', renderProductos);

async function cargarSucursales() {
  const res = await fetch(`${API_BASE}/grpc/sucursales`);
  const sucursales = await res.json();
  const select = document.getElementById('sucursalSelect');
  select.innerHTML = '';
  sucursales.forEach(s => {
    const opt = document.createElement('option');
    opt.value = s.id;
    opt.textContent = `${s.nombre} - ${s.direccion}`;
    select.appendChild(opt);
  });
  select.addEventListener('change', fetchProductos);
}

async function simularCompra() {
  const sucursalId = document.getElementById('sucursalSelect').value;
  const compra = [];

  productos.forEach(p => {
    const cantidad = parseInt(document.getElementById(`cantidad-${p.id}`).value);
    if (cantidad > 0) {
      compra.push({
        producto_id: p.id,
        cantidad,
        nombre: p.nombre,
        precio: p.precio
      });
    }
  });

  if (compra.length === 0) {
    alert('Debes seleccionar al menos un producto');
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/ventas-simuladas`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sucursal_id: sucursalId, productos: compra })
    });

    const data = await res.json();

    if (res.ok) {
      const timestamp = new Date().toLocaleString();
      const totalCLP = compra.reduce((acc, item) => acc + item.precio * item.cantidad, 0);
      const totalUSD = totalCLP * usdRate;

      localStorage.setItem('ultima_compra', JSON.stringify({
        productos: compra,
        fecha: timestamp,
        totalCLP,
        totalUSD
      }));

      window.location.href = '/confirmacion.html';
    } else {
      alert(data.error || 'Error procesando venta');
    }
  } catch (e) {
    console.error(e);
    alert('Error de conexión con el servidor.');
  }
}

function escucharStockBajo() {
  const alertDiv = document.getElementById('alertasStock');
  const limpiarBtn = document.getElementById('limpiarAlertasBtn');
  const eventSource = new EventSource(`${API_BASE}/stock-alerta`);

  eventSource.onmessage = function(event) {
    if (!mensajesMostrados.has(event.data)) {
      mensajesMostrados.add(event.data);
      alertDiv.classList.remove('d-none');
      limpiarBtn.classList.remove('d-none');
      alertDiv.innerHTML += `<div>⚠️ ${event.data}</div>`;
    }
  };
}

function limpiarAlertas() {
  const alertDiv = document.getElementById('alertasStock');
  const limpiarBtn = document.getElementById('limpiarAlertasBtn');
  mensajesMostrados.clear();
  alertDiv.innerHTML = '';
  alertDiv.classList.add('d-none');
  limpiarBtn.classList.add('d-none');
}

cargarSucursales().then(fetchProductos);
escucharStockBajo();
