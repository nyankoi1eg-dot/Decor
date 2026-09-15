'use strict';

/* ---------------------------------------------------------------- rangos */
function preset(nombre) {
  const hoy = new Date();
  let desde, hasta;
  if (nombre === 'semana') {
    // Lunes a domingo de la semana pasada.
    const dow = (hoy.getDay() + 6) % 7;
    hasta = new Date(hoy); hasta.setDate(hoy.getDate() - dow - 1);
    desde = new Date(hasta); desde.setDate(hasta.getDate() - 6);
  } else if (nombre === 'mes') {
    desde = new Date(hoy.getFullYear(), hoy.getMonth(), 1);
    hasta = hoy;
  } else {
    const n = Number(nombre);
    hasta = new Date(hoy); hasta.setDate(hoy.getDate() - 1);
    desde = new Date(hasta); desde.setDate(hasta.getDate() - (n - 1));
  }
  return [iso(desde), iso(hasta)];
}

function marcarPreset(activo) {
  document.querySelectorAll('[data-preset]').forEach((b) => {
    b.setAttribute('aria-pressed', String(b.dataset.preset === activo));
  });
}

document.querySelectorAll('[data-preset]').forEach((b) => {
  b.addEventListener('click', () => {
    const [d, h] = preset(b.dataset.preset);
    $('desde').value = d; $('hasta').value = h;
    marcarPreset(b.dataset.preset);
  });
});
['desde', 'hasta'].forEach((id) => $(id).addEventListener('input', () => marcarPreset(null)));

/* ----------------------------------------------------------------- envio */
$('form').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const token = $('token').value.trim();
  const apikey = $('apikey') ? $('apikey').value.trim() : '';
  const desde = $('desde').value, hasta = $('hasta').value;
  const err = $('error');
  err.hidden = true;

  if (desde > hasta) {
    err.textContent = 'La fecha "desde" no puede ser posterior a "hasta".';
    err.hidden = false;
    return;
  }

  sessionStorage.setItem('bm_recordar', $('recordar').checked ? '1' : '');
  try {
    if ($('recordar').checked) sessionStorage.setItem('bm_token', token);
    else sessionStorage.removeItem('bm_token');
  } catch (e) { /* almacenamiento bloqueado: seguimos sin recordar */ }

  const btn = $('btn');
  btn.disabled = true;
  btn.textContent = 'Consultando Botmaker…';
  $('reporte').classList.add('loading');

  try {
    // obtenerDatos lo define la capa de datos: api-servidor.js (vía el backend)
    // o api-botmaker.js (contra Botmaker directo, en el archivo suelto).
    render(await obtenerDatos({ desde, hasta, token, apikey, avisar: (t) => { btn.textContent = t; } }));
  } catch (e) {
    err.textContent = e.message || 'No se pudo generar el reporte.';
    err.hidden = false;
    $('reporte').hidden = true;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Generar reporte';
    $('reporte').classList.remove('loading');
  }
});

/* ---------------------------------------------------------------- inicio */
(function init() {
  const [d, h] = preset('semana');
  $('desde').value = d; $('hasta').value = h;
  marcarPreset('semana');
  try {
    const guardado = sessionStorage.getItem('bm_token');
    if (guardado) { $('token').value = guardado; $('recordar').checked = true; }
  } catch (e) { /* sessionStorage no disponible */ }
})();
