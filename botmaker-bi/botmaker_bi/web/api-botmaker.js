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
const PREFIJO_TIENDA = 'TDA';
const SIN_TIENDA = '(sin tienda identificada)';
const SIN_GESTOR = '(sin gestor identificado)';
const EVENTO_COLA = 'queue-set';
const EVENTO_ASIGNACION = 'assigned-to-agent';
const EVENTO_CIERRE = 'conversation-close';
/* Botmaker no documenta con qué nombre viaja el operador dentro de info. */
const CLAVES_OPERADOR = ['operatorName', 'operator', 'agentName', 'agent',
  'userName', 'user', 'closedBy', 'by', 'email'];
const CLAVES_AGENTE = ['agentName', 'agent', 'operatorName', 'operator',
  'userName', 'user', 'assignedTo', 'to', 'email'];
const CLAVES_TIMESTAMP = ['creationTime', 'time', 'timestamp', 'date'];
/* Métricas que NO se pueden sumar entre días: una persona que escribe dos días
 * cuenta una vez por día y una sola vez en el período. */
const CAMPOS_NO_ADITIVOS = ['personas_unicas'];
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

/* --- mismo cálculo que funnel.py: etapas anidadas ---
 *
 * Cada señal sale de la propia sesión, nunca del estado actual del chat:
 * chat.tags y chat.variables describen el chat HOY y vienen repetidos en todas
 * las sesiones del mismo contacto, así que contaminan semanas anteriores.
 *   · derivación -> evento conversation-close, info.typification
 *   · cola       -> evento queue-set, info.queue  (chat.queueId no existe en
 *                   GET /sessions: leerlo dejaba la columna siempre vacía)
 * Los tags sólo se usan para atribuir la tienda TDA*.
 */
function marcaEvento(e) {
  for (const k of CLAVES_TIMESTAMP) if (typeof e[k] === 'string' && e[k]) return e[k];
  return '';
}

function eventosPorNombre(s) {
  const mapa = new Map();
  for (const e of s.events || []) {
    if (!e || typeof e !== 'object') continue;
    const n = e.name || '';
    if (!mapa.has(n)) mapa.set(n, []);
    mapa.get(n).push(e);
  }
  // Los eventos no siempre llegan ordenados y nos interesa el último.
  for (const g of mapa.values()) g.sort((a, b) => marcaEvento(a).localeCompare(marcaEvento(b)));
  return mapa;
}

/* info del último evento con ese nombre: una conversación puede re-encolarse o
 * cerrarse más de una vez, y lo que describe el desenlace es el último. */
function infoUltimo(eventos, nombre) {
  const g = eventos.get(nombre);
  if (!g || !g.length) return {};
  const info = g[g.length - 1].info;
  return info && typeof info === 'object' ? info : {};
}

function texto(v) { return typeof v === 'string' && v.trim() ? v.trim() : null; }

function persona(info, claves) {
  for (const k of claves) { const v = texto(info[k]); if (v) return v; }
  return null;
}

function aFechaLocal(iso) {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return new Date(t + OFFSET * 3600000).toISOString().slice(0, 10);
}

function fechaEvento(eventos, nombre) {
  const g = eventos.get(nombre);
  if (!g || !g.length) return null;
  const marca = marcaEvento(g[g.length - 1]);
  return marca ? aFechaLocal(marca) : null;
}

function sesionAFila(s) {
  const chat = s.chat || {};
  const ref = chat.chat || {};
  const eventos = eventosPorNombre(s);
  const tags = new Set(chat.tags || []);
  const fechaLocal = aFechaLocal(s.creationTime);

  const cola = texto(infoUltimo(eventos, EVENTO_COLA).queue);
  const infoCierre = infoUltimo(eventos, EVENTO_CIERRE);
  const tip = texto(infoCierre.typification);
  const operador = persona(infoCierre, CLAVES_OPERADOR);
  const agente = persona(infoUltimo(eventos, EVENTO_ASIGNACION), CLAVES_AGENTE);

  const cerrado = eventos.has(EVENTO_CIERRE);
  const asignado = eventos.has(EVENTO_ASIGNACION);
  // Criterio B: un operador que cierra la conversación la trabajó, aunque el
  // chat nunca se le asignara formalmente.
  const cerradoPorOperador = Boolean(operador);
  const enCola = eventos.has(EVENTO_COLA) || asignado;
  const atendido = enCola && (asignado || cerradoPorOperador);
  const derivado = atendido && TIPIFICACIONES_DERIVACION.has(tip);

  // Una sola tienda por derivación: así el corte por tienda suma igual que el
  // total de derivados. Contar pares (sesión x tag) lo inflaba.
  const tiendas = [...tags].filter((t) => t.startsWith(PREFIJO_TIENDA)).sort();
  const tienda = derivado ? (tiendas[0] || SIN_TIENDA) : null;

  // La derivación se imputa al día del CIERRE, que es cuando el gestor tipifica.
  const fechaCierre = fechaEvento(eventos, EVENTO_CIERRE);
  const fechaDerivacion = derivado ? (fechaCierre || fechaLocal) : null;
  let gestor = operador || agente;
  if (atendido && !gestor) gestor = SIN_GESTOR;

  return {
    id: s.id, chatId: ref.chatId || '', fechaLocal, fechaCierre, fechaDerivacion,
    cola, tipificacion: tip, operador, agente, gestor, tienda, tiendas,
    enCola, asignado, cerradoPorOperador, atendido, derivado, cerrado,
  };
}

function pctSeguro(a, b) { return b ? Math.round((a / b) * 1000) / 10 : null; }

/* Bloque de embudo. `derivados` se fuerza en el corte diario, donde las
 * derivaciones no son las de las sesiones que entraron ese día sino las que
 * cerraron. */
function bloqueEmbudo(filas, derivados) {
  const ing = filas.length;
  const cola = filas.filter((f) => f.enCola).length;
  const at = filas.filter((f) => f.atendido).length;
  // De los chats que ENTRARON en este grupo, cuántos terminaron derivando, sin
  // importar qué día cerraron. Es la única cifra que comparte población con
  // ingresos/cola/atendidos, así que es la que da porcentajes legibles.
  const cohorte = filas.filter((f) => f.derivado).length;
  const der = derivados === undefined ? cohorte : derivados;
  return {
    ingresos: ing,
    personas_unicas: new Set(filas.map((f) => f.chatId).filter(Boolean)).size,
    en_cola: cola, atendidos: at,
    // Imputadas al día del CIERRE: "cuánto derivamos ese día" (operativo).
    derivados_tienda: der,
    // Imputadas al día de INGRESO: "de lo que entró ese día, cuánto derivó"
    // (conversión). En el total del período las dos coinciden.
    derivados_cohorte: cohorte,
    sin_cerrar: filas.filter((f) => !f.cerrado).length,
    pct_ingreso_a_cola: pctSeguro(cola, ing), pct_cola_a_atendido: pctSeguro(at, cola),
    // Sobre la cohorte, no sobre los cierres del día: dividir derivaciones de
    // otros días por los atendidos de éste daba porcentajes de más de 100%.
    pct_atendido_a_tienda: pctSeguro(cohorte, at), pct_conversion_global: pctSeguro(cohorte, ing),
  };
}

function derivacionesPorDia(filas) {
  const m = new Map();
  for (const f of filas) {
    if (f.derivado && f.fechaDerivacion) m.set(f.fechaDerivacion, (m.get(f.fechaDerivacion) || 0) + 1);
  }
  return m;
}

/* Una fila por tienda, contando DERIVACIONES. La suma es exactamente
 * derivados_tienda del total. */
function porTienda(filas) {
  const conteo = new Map();
  for (const f of filas) {
    if (!f.derivado) continue;
    const k = f.tienda || SIN_TIENDA;
    conteo.set(k, (conteo.get(k) || 0) + 1);
  }
  return [...conteo.entries()]
    .sort((a, b) => (a[0] === SIN_TIENDA) - (b[0] === SIN_TIENDA)
      || b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([tienda, derivaciones]) => ({ tienda, derivaciones }));
}

function porDia(filas) {
  const grupos = new Map();
  for (const f of filas) {
    if (!grupos.has(f.fechaLocal)) grupos.set(f.fechaLocal, []);
    grupos.get(f.fechaLocal).push(f);
  }
  const derivs = derivacionesPorDia(filas);
  const fechas = [...new Set([...grupos.keys(), ...derivs.keys()])].filter(Boolean).sort();
  return fechas.map((fecha) => {
    const g = grupos.get(fecha) || [];
    const fila = {
      fecha,
      dia_semana: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][new Date(fecha + 'T12:00:00Z').getUTCDay()],
      ...bloqueEmbudo(g, derivs.get(fecha) || 0),
    };
    fila.provisional = fila.sin_cerrar > 0;
    return fila;
  });
}

/* Sólo sesiones ATENDIDAS: un chat que murió en el bot no tiene gestor a quien
 * atribuírselo. */
function porGestor(filas) {
  const grupos = new Map();
  for (const f of filas) {
    if (!f.atendido) continue;
    const k = f.gestor || SIN_GESTOR;
    if (!grupos.has(k)) grupos.set(k, []);
    grupos.get(k).push(f);
  }
  return [...grupos.entries()]
    .map(([gestor, g]) => ({
      gestor, ...bloqueEmbudo(g), por_tienda: porTienda(g), por_dia: porDia(g),
    }))
    .sort((a, b) => (a.gestor === SIN_GESTOR) - (b.gestor === SIN_GESTOR)
      || b.atendidos - a.atendidos || a.gestor.localeCompare(b.gestor));
}

function agregar(filas, desde, hasta) {
  const totales = bloqueEmbudo(filas);
  totales.campos_no_aditivos = CAMPOS_NO_ADITIVOS;
  totales.criterio_atendido = 'B';   // asignado o cerrado por un operador
  totales.asignados = filas.filter((f) => f.asignado).length;
  // Cuántas derivaciones cerraron un día distinto al del ingreso: es la
  // magnitud del desfase entre las dos lecturas de la tabla diaria.
  totales.derivaciones_diferidas =
    filas.filter((f) => f.derivado && f.fechaDerivacion !== f.fechaLocal).length;
  totales.cerrados_por_operador_sin_asignar =
    filas.filter((f) => f.cerradoPorOperador && !f.asignado).length;

  return {
    periodo: { desde, hasta },
    totales,
    por_dia: porDia(filas),
    por_tienda: porTienda(filas),
    por_gestor: porGestor(filas),
  };
}

async function obtenerDatos({ desde, hasta, token, avisar }) {
  if (!token) throw new Error('Hace falta el token de acceso de Botmaker.');
  if (avisar) avisar('Consultando Botmaker…');
  const sesiones = await traerSesiones(desde, hasta, token, avisar);
  // Las ventanas solapadas pueden repetir sesiones: deduplicamos por id.
  const vistas = new Map();
  const crudas = new Map();
  for (const s of sesiones) { const f = sesionAFila(s); vistas.set(f.id, f); crudas.set(s.id, s); }
  const filas = [...vistas.values()].filter((f) => f.fechaLocal >= desde && f.fechaLocal <= hasta);
  const datos = agregar(filas, desde, hasta);
  // El JSON crudo queda disponible para descargar: es la única vía de pasarle
  // estos datos a un entorno que no tenga salida de red hacia Botmaker.
  const vivas = new Set(filas.map((f) => f.id));
  const items = [...crudas.values()].filter((s) => vivas.has(s.id));
  datos.crudo = { desde, hasta, total: items.length, items };
  return datos;
}
