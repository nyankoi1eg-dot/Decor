'use strict';
/* Capa de datos del archivo suelto: el navegador llama a Botmaker directo.
 *
 * Es el mismo cálculo que hace funnel.py en el servidor, portado a JS para que
 * el reporte funcione sin instalar nada. Si se cambia una definición de etapa,
 * hay que cambiarla en los dos sitios.
 */

const BM_BASE = 'https://api.botmaker.com/v2.0';
const OFFSET = -5;                       // Lima, UTC-5
const DIAS_SIN_LONG_TERM = 7;            // más allá, Botmaker exige long-term-search
const TIPIFICACIONES_DERIVACION = new Set(['Lead_Calificado', 'CORPORATIVO-LEAD-DERIVADO']);
const TAGS_DERIVACION = new Set(['DERIVADOS']);
const PREFIJO_TIENDA = 'TDA';
const REINTENTOS = new Set([429, 500, 502, 503, 504]);

const dormir = (ms) => new Promise((r) => setTimeout(r, ms));

/* La API sólo acepta UTC con sufijo Z; un offset tipo -05:00 devuelve 400. */
function aUtcZ(fechaLocal, diasExtra = 0) {
  const [a, m, d] = fechaLocal.split('-').map(Number);
  const t = Date.UTC(a, m - 1, d + diasExtra, -OFFSET, 0, 0);
  return new Date(t).toISOString().replace(/\.\d{3}Z$/, 'Z');
}

async function pedir(url, token, intento = 0) {
  let r;
  try {
    r = await fetch(url, { headers: { 'access-token': token, Accept: 'application/json' } });
  } catch (e) {
    // Fallo de red: puede ser corte real o el navegador bloqueando la petición.
    if (intento < 3) { await dormir(2000 * 2 ** intento); return pedir(url, token, intento + 1); }
    throw new Error('No se pudo contactar a api.botmaker.com. Revisá la conexión a internet.');
  }
  if (REINTENTOS.has(r.status) && intento < 3) {
    await dormir(2000 * 2 ** intento);
    return pedir(url, token, intento + 1);
  }
  if (r.status === 401 || r.status === 403) {
    throw new Error('Botmaker rechazó el token (HTTP ' + r.status + '). Verificá que sea el de Integraciones → API y que siga vigente.');
  }
  if (r.status === 204) return { items: [], nextPage: null };   // periodo sin registros
  if (!r.ok) {
    let det = '';
    try { det = (await r.json()).errors?.[0]?.message || ''; } catch (e) { /* cuerpo no JSON */ }
    throw new Error(`Botmaker respondió ${r.status}${det ? ': ' + det : ''}`);
  }
  if (r.status === 200 && r.headers.get('content-length') === '0') return { items: [], nextPage: null };
  return r.json();
}

async function traerSesiones(desde, hasta, token, avisar) {
  // Se comparan dias de calendario, no milisegundos: con horas de por medio
  // un rango de exactamente 7 dias activaria long-term-search sin necesidad,
  // y eso consume cuota BI de la cuenta. Igual que el calculo de cli.py.
  const hoyIso = new Date().toISOString().slice(0, 10);
  const dias = Math.round((Date.parse(hoyIso) - Date.parse(desde)) / 86400000);
  const largo = dias > DIAS_SIN_LONG_TERM;
  const q = new URLSearchParams({
    from: aUtcZ(desde), to: aUtcZ(hasta, 1),
    'include-events': 'true', 'include-variables': 'true', 'include-open-sessions': 'true',
  });
  if (largo) q.set('long-term-search', 'true');

  let url = `${BM_BASE}/sessions?${q}`;
  const items = [];
  for (let pagina = 1; pagina <= 500; pagina++) {
    if (avisar && pagina > 1) avisar(`Descargando… ${items.length} sesiones`);
    const d = await pedir(url, token);
    items.push(...(d.items || []));
    if (!d.nextPage) break;
    // Botmaker puede devolver la URL en http: forzamos https o el navegador
    // la bloquea por contenido mixto.
    url = d.nextPage.replace(/^http:/, 'https:');
  }
  return items;
}

/* --- mismo cálculo que funnel.py: etapas anidadas --- */
function sesionAFila(s) {
  const chat = s.chat || {};
  const ref = chat.chat || {};
  const eventos = new Set((s.events || []).map((e) => e.name));
  const tags = new Set(chat.tags || []);
  const tip = (chat.variables || {}).typification;
  const tiendas = [...tags].filter((t) => t.startsWith(PREFIJO_TIENDA)).sort();

  const utc = new Date(s.creationTime);
  const local = new Date(utc.getTime() + OFFSET * 3600000);
  const fechaLocal = local.toISOString().slice(0, 10);

  const enCola = eventos.has('queue-set') || eventos.has('assigned-to-agent');
  const atendido = enCola && eventos.has('assigned-to-agent');
  const derivado = atendido && (TIPIFICACIONES_DERIVACION.has(tip) ||
    [...tags].some((t) => TAGS_DERIVACION.has(t)) || tiendas.length > 0);

  return { id: s.id, chatId: ref.chatId || '', fechaLocal, enCola, atendido, derivado, tiendas };
}

function pctSeguro(a, b) { return b ? Math.round((a / b) * 1000) / 10 : null; }

function agregar(filas, desde, hasta) {
  const porDia = new Map();
  for (const f of filas) {
    if (!porDia.has(f.fechaLocal)) porDia.set(f.fechaLocal, []);
    porDia.get(f.fechaLocal).push(f);
  }
  const dias = [...porDia.keys()].sort().map((fecha) => {
    const g = porDia.get(fecha);
    const ing = g.length;
    const cola = g.filter((f) => f.enCola).length;
    const at = g.filter((f) => f.atendido).length;
    const der = g.filter((f) => f.derivado).length;
    return {
      fecha,
      dia_semana: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][new Date(fecha + 'T12:00:00Z').getUTCDay()],
      ingresos: ing, personas_unicas: new Set(g.map((f) => f.chatId)).size,
      en_cola: cola, atendidos: at, derivados_tienda: der,
      pct_ingreso_a_cola: pctSeguro(cola, ing), pct_cola_a_atendido: pctSeguro(at, cola),
      pct_atendido_a_tienda: pctSeguro(der, at), pct_conversion_global: pctSeguro(der, ing),
    };
  });

  const ing = filas.length;
  const cola = filas.filter((f) => f.enCola).length;
  const at = filas.filter((f) => f.atendido).length;
  const der = filas.filter((f) => f.derivado).length;
  const totales = {
    ingresos: ing, personas_unicas: new Set(filas.map((f) => f.chatId)).size,
    en_cola: cola, atendidos: at, derivados_tienda: der,
    pct_ingreso_a_cola: pctSeguro(cola, ing), pct_cola_a_atendido: pctSeguro(at, cola),
    pct_atendido_a_tienda: pctSeguro(der, at), pct_conversion_global: pctSeguro(der, ing),
  };

  const conteo = new Map();
  for (const f of filas) for (const t of f.tiendas) conteo.set(t, (conteo.get(t) || 0) + 1);
  const porTienda = [...conteo.entries()].sort((a, b) => b[1] - a[1])
    .map(([tienda, derivaciones]) => ({ tienda, derivaciones }));

  return { periodo: { desde, hasta }, totales, por_dia: dias, por_tienda: porTienda };
}

async function obtenerDatos({ desde, hasta, token, avisar }) {
  if (!token) throw new Error('Hace falta el token de acceso de Botmaker.');
  if (avisar) avisar('Consultando Botmaker…');
  const sesiones = await traerSesiones(desde, hasta, token, avisar);
  // Las ventanas solapadas pueden repetir sesiones: deduplicamos por id.
  const vistas = new Map();
  for (const s of sesiones) { const f = sesionAFila(s); vistas.set(f.id, f); }
  const filas = [...vistas.values()].filter((f) => f.fechaLocal >= desde && f.fechaLocal <= hasta);
  return agregar(filas, desde, hasta);
}
