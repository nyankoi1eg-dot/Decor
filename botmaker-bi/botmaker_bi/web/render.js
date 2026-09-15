'use strict';

const $ = (id) => document.getElementById(id);
const fmt = (n) => (n == null ? '—' : n.toLocaleString('es-PE'));
const pct = (n) => (n == null ? '—' : n.toFixed(1) + '%');
const iso = (d) => d.toISOString().slice(0, 10);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

const DIAS = { Mon: 'Lun', Tue: 'Mar', Wed: 'Mié', Thu: 'Jue', Fri: 'Vie', Sat: 'Sáb', Sun: 'Dom' };
const SERIES = [
  { clave: 'ingresos', nombre: 'Ingresaron', color: 'var(--series-1)' },
  { clave: 'atendidos', nombre: 'Atendidos', color: 'var(--series-2)' },
  { clave: 'derivados_tienda', nombre: 'Derivados a tienda', color: 'var(--series-3)' },
];

/* ------------------------------------------------------------ geometria */
// Barra con el extremo de dato redondeado (4px) y la base cuadrada.
function barraH(x, y, w, h, r = 4) {
  const rr = Math.min(r, Math.max(w, 0));
  if (w <= 0.5) return `M${x} ${y}h0`;
  return `M${x} ${y}h${w - rr}a${rr} ${rr} 0 0 1 ${rr} ${rr}v${h - 2 * rr}a${rr} ${rr} 0 0 1 ${-rr} ${rr}H${x}z`;
}
function barraV(x, yBase, w, h, r = 4) {
  const rr = Math.min(r, Math.max(h, 0), w / 2);
  if (h <= 0.5) return `M${x} ${yBase}h0`;
  const y = yBase - h;
  return `M${x} ${yBase}V${y + rr}a${rr} ${rr} 0 0 1 ${rr} ${-rr}h${w - 2 * rr}a${rr} ${rr} 0 0 1 ${rr} ${rr}V${yBase}z`;
}
function ticks(max, n = 4) {
  if (max <= 0) return [0];
  const bruto = max / n;
  const mag = Math.pow(10, Math.floor(Math.log10(bruto)));
  // Son conteos de sesiones: el paso nunca baja de 1, si no salen ticks repetidos.
  const paso = Math.max(1, [1, 2, 2.5, 5, 10].map((m) => m * mag).find((p) => p >= bruto) || mag * 10);
  const out = [];
  // Se generan pasos hasta cubrir el maximo: si el tope quedara por debajo,
  // la barra mas alta se dibujaria fuera del area del grafico.
  for (let v = 0; v < max - paso * 0.001; v += paso) out.push(Math.round(v));
  out.push(Math.round(Math.ceil(max / paso) * paso));
  return [...new Set(out)];
}

/* ------------------------------------------------------------- tooltips */
let tip;
function mostrarTip(ev, html) {
  if (!tip) {
    tip = document.createElement('div');
    tip.style.cssText = 'position:fixed;z-index:50;pointer-events:none;background:var(--surface-1);' +
      'color:var(--text-primary);border:1px solid var(--border);border-radius:7px;padding:8px 10px;' +
      'font:12px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;box-shadow:0 4px 14px rgba(0,0,0,.14);max-width:230px';
    document.body.appendChild(tip);
  }
  tip.innerHTML = html;
  tip.hidden = false;
  const m = 14, r = tip.getBoundingClientRect();
  let x = ev.clientX + m, y = ev.clientY + m;
  if (x + r.width > innerWidth - 8) x = ev.clientX - r.width - m;
  if (y + r.height > innerHeight - 8) y = ev.clientY - r.height - m;
  tip.style.left = Math.max(8, x) + 'px';
  tip.style.top = Math.max(8, y) + 'px';
}
const ocultarTip = () => { if (tip) tip.hidden = true; };

function conectarTips(raiz) {
  raiz.querySelectorAll('[data-tip]').forEach((el) => {
    el.style.cursor = 'default';
    el.addEventListener('mousemove', (ev) => mostrarTip(ev, el.dataset.tip));
    el.addEventListener('mouseleave', ocultarTip);
    el.addEventListener('focus', (ev) => {
      const r = el.getBoundingClientRect();
      mostrarTip({ clientX: r.left + r.width / 2, clientY: r.top }, el.dataset.tip);
    });
    el.addEventListener('blur', ocultarTip);
  });
}

/* ------------------------------------------------------ grafico: embudo */
function svgEmbudo(t) {
  const etapas = [
    { nom: 'Ingresaron al chat', v: t.ingresos, paso: 'var(--step-1)' },
    { nom: 'Pasaron a cola', v: t.en_cola, paso: 'var(--step-2)', conv: t.pct_ingreso_a_cola },
    { nom: 'Atendidos por asesor', v: t.atendidos, paso: 'var(--step-3)', conv: t.pct_cola_a_atendido },
    { nom: 'Derivados a tienda', v: t.derivados_tienda, paso: 'var(--step-4)', conv: t.pct_atendido_a_tienda },
  ];
  const W = 720, fila = 62, alto = 24, izq = 172, der = 68;
  const H = etapas.length * fila;
  const max = Math.max(...etapas.map((e) => e.v), 1);
  const ancho = W - izq - der;

  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Embudo por etapas">`;
  etapas.forEach((e, i) => {
    const y = i * fila + 10;
    const w = (e.v / max) * ancho;
    const tipo = `<strong>${esc(e.nom)}</strong><br>${fmt(e.v)} sesiones` +
      (e.conv != null ? `<br>${pct(e.conv)} de la etapa anterior` : '');
    s += `<text class="slab" x="0" y="${y + alto / 2 + 4}">${esc(e.nom)}</text>`;
    s += `<g tabindex="0" data-tip="${esc(tipo)}"><rect x="${izq}" y="${y - 6}" width="${ancho}" height="${alto + 12}" fill="transparent"/>` +
      `<path d="${barraH(izq, y, w, alto)}" fill="${e.paso}"/></g>`;
    s += `<text class="vlab" x="${izq + w + 8}" y="${y + alto / 2 + 4}">${fmt(e.v)}</text>`;
    // Conversion respecto de la etapa anterior, entre barra y barra.
    if (e.conv != null) {
      s += `<text class="conv" x="${izq}" y="${y - 12}">▼ ${pct(e.conv)}</text>`;
    }
  });
  return s + '</svg>';
}

/* ------------------------------------------- grafico: evolucion por dia */
function svgDiario(dias) {
  const W = 720, H = 240, izq = 40, der = 12, arr = 12, abj = 34;
  const pw = W - izq - der, ph = H - arr - abj;
  const max = Math.max(...dias.map((d) => d.ingresos), 1);
  const tks = ticks(max);
  const tope = tks[tks.length - 1];
  const y = (v) => arr + ph - (v / tope) * ph;
  const banda = pw / dias.length;
  const lineas = dias.length > 14;

  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Evolución diaria por etapa">`;
  tks.forEach((t) => {
    s += `<line x1="${izq}" x2="${W - der}" y1="${y(t)}" y2="${y(t)}" stroke="var(--grid)" stroke-width="1"/>` +
      `<text class="tick" x="${izq - 8}" y="${y(t) + 4}" text-anchor="end">${fmt(t)}</text>`;
  });

  if (lineas) {
    const px = (i) => izq + banda * (i + 0.5);
    SERIES.forEach((se) => {
      const pts = dias.map((d, i) => `${px(i)},${y(d[se.clave])}`).join(' ');
      s += `<polyline points="${pts}" fill="none" stroke="${se.color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
      const ult = dias.length - 1;
      s += `<circle cx="${px(ult)}" cy="${y(dias[ult][se.clave])}" r="4" fill="${se.color}" stroke="var(--surface-1)" stroke-width="2"/>`;
    });
    dias.forEach((d, i) => {
      const filas = SERIES.map((se) => `${esc(se.nombre)}: <strong>${fmt(d[se.clave])}</strong>`).join('<br>');
      s += `<g tabindex="0" data-tip="${esc(`<strong>${d.fecha}</strong><br>${filas}`)}">` +
        `<rect x="${izq + banda * i}" y="${arr}" width="${banda}" height="${ph}" fill="transparent"/></g>`;
    });
  } else {
    const hueco = 2, grupo = Math.min(banda * 0.72, 72);
    const bw = Math.max(3, (grupo - hueco * (SERIES.length - 1)) / SERIES.length);
    dias.forEach((d, i) => {
      const x0 = izq + banda * i + (banda - (bw * SERIES.length + hueco * 2)) / 2;
      const filas = SERIES.map((se) => `${esc(se.nombre)}: <strong>${fmt(d[se.clave])}</strong>`).join('<br>');
      s += `<g tabindex="0" data-tip="${esc(`<strong>${d.fecha}</strong><br>${filas}`)}">` +
        `<rect x="${izq + banda * i}" y="${arr}" width="${banda}" height="${ph}" fill="transparent"/>`;
      SERIES.forEach((se, j) => {
        const h = (d[se.clave] / tope) * ph;
        s += `<path d="${barraV(x0 + j * (bw + hueco), arr + ph, bw, h)}" fill="${se.color}"/>`;
      });
      s += `</g>`;
    });
  }

  dias.forEach((d, i) => {
    const paso = Math.ceil(dias.length / 10);
    if (i % paso) return;
    const et = dias.length > 10 ? d.fecha.slice(5) : (DIAS[d.dia_semana] || '') + ' ' + d.fecha.slice(8);
    s += `<text class="tick" x="${izq + banda * (i + 0.5)}" y="${H - 12}" text-anchor="middle">${esc(et)}</text>`;
  });
  return s + '</svg>';
}

/* ------------------------------------------ grafico: derivacion tienda */
function svgTiendas(lista) {
  const top = lista.slice(0, 12);
  const W = 720, fila = 30, alto = 16, izq = 132, der = 54;
  const H = Math.max(top.length * fila, fila);
  const max = Math.max(...top.map((t) => t.derivaciones), 1);
  const ancho = W - izq - der;
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Derivaciones por tienda">`;
  top.forEach((t, i) => {
    const y = i * fila + 5;
    const w = (t.derivaciones / max) * ancho;
    const nom = t.tienda.replace(/^TDA/, '');
    s += `<text class="slab" x="0" y="${y + alto / 2 + 4}">${esc(nom)}</text>`;
    s += `<g tabindex="0" data-tip="${esc(`<strong>${nom}</strong><br>${fmt(t.derivaciones)} derivaciones`)}">` +
      `<rect x="${izq}" y="${y - 5}" width="${ancho}" height="${alto + 10}" fill="transparent"/>` +
      `<path d="${barraH(izq, y, w, alto)}" fill="var(--series-1)"/></g>`;
    s += `<text class="vlab" x="${izq + w + 8}" y="${y + alto / 2 + 4}">${fmt(t.derivaciones)}</text>`;
  });
  return s + '</svg>';
}

/* ---------------------------------------------------------------- tabla */
function tablaDiaria(dias, t) {
  const cols = [
    ['Fecha', (d) => d.fecha], ['Día', (d) => DIAS[d.dia_semana] || d.dia_semana],
    ['Ingresaron', (d) => fmt(d.ingresos)], ['Únicas', (d) => fmt(d.personas_unicas)],
    ['A cola', (d) => fmt(d.en_cola)], ['Atendidos', (d) => fmt(d.atendidos)],
    ['A tienda', (d) => fmt(d.derivados_tienda)],
    ['% Ing→Cola', (d) => pct(d.pct_ingreso_a_cola)],
    ['% Cola→Aten', (d) => pct(d.pct_cola_a_atendido)],
    ['% Aten→Tda', (d) => pct(d.pct_atendido_a_tienda)],
    ['% Global', (d) => pct(d.pct_conversion_global)],
  ];
  const th = cols.map((c) => `<th>${esc(c[0])}</th>`).join('');
  const tb = dias.map((d) => {
    // Un día con sesiones abiertas todavía puede cambiar: se marca provisional.
    const marca = d.provisional ? `<span class="prov" title="${esc(fmt(d.sin_cerrar) + ' sesiones sin cerrar: la cifra puede cambiar')}">*</span>` : '';
    return '<tr>' + cols.map((c, i) =>
      `<td>${esc(c[1](d))}${i === 0 ? marca : ''}</td>`).join('') + '</tr>';
  }).join('');
  // personas_unicas NO se totaliza: sumar la columna cuenta dos veces a quien
  // escribe dos días. Se muestra el distinct del período, marcado.
  const sumaUnicas = dias.reduce((a, d) => a + d.personas_unicas, 0);
  const tf = '<tr><td>Total</td><td></td>' +
    `<td>${fmt(t.ingresos)}</td>` +
    `<td class="noadit" title="${esc('Distinto del período. No es la suma de la columna (' + fmt(sumaUnicas) + ').')}">${fmt(t.personas_unicas)}<span class="prov">†</span></td>` +
    [t.en_cola, t.atendidos, t.derivados_tienda].map((v) => `<td>${fmt(v)}</td>`).join('') +
    [t.pct_ingreso_a_cola, t.pct_cola_a_atendido, t.pct_atendido_a_tienda, t.pct_conversion_global]
      .map((v) => `<td>${pct(v)}</td>`).join('') + '</tr>';
  const notas = [];
  if (dias.some((d) => d.provisional)) {
    notas.push(`<strong>*</strong> Días con sesiones sin cerrar: provisionales, las tipificaciones todavía pueden cambiar.`);
  }
  notas.push(`<strong>†</strong> Personas únicas no es aditiva: el distinto del período es ${fmt(t.personas_unicas)}, la suma de la columna daría ${fmt(sumaUnicas)}. Quien escribe dos días cuenta una sola vez.`);
  return `<div class="scroll-x"><table><thead><tr>${th}</tr></thead><tbody>${tb}</tbody><tfoot>${tf}</tfoot></table></div>`
    + `<p class="nota">${notas.join('<br>')}</p>`;
}

/* Tabla de tiendas CON total: es la comprobación de que el corte por punto de
 * venta cuadra con el embudo. Antes se contaban pares (sesión x tag) y daba de
 * más; ahora cada derivación aporta a una sola tienda. */
function tablaTiendas(lista, totalDerivados) {
  const suma = lista.reduce((a, t) => a + t.derivaciones, 0);
  const tb = lista.map((t) => {
    const nom = t.tienda.replace(/^TDA/, '');
    const p = pct(totalDerivados ? Math.round((t.derivaciones / totalDerivados) * 1000) / 10 : null);
    return `<tr><td>${esc(nom)}</td><td>${fmt(t.derivaciones)}</td><td>${esc(p)}</td></tr>`;
  }).join('');
  const descuadre = suma !== totalDerivados
    ? `<span class="prov" title="${esc('No cuadra con los ' + fmt(totalDerivados) + ' derivados del embudo')}"> ⚠</span>` : '';
  const tf = `<tr><td>Total</td><td>${fmt(suma)}${descuadre}</td><td>${esc(pct(suma ? 100 : null))}</td></tr>`;
  return `<div class="scroll-x"><table><thead><tr><th>Tienda</th><th>Derivaciones</th><th>% del total</th></tr></thead>`
    + `<tbody>${tb}</tbody><tfoot>${tf}</tfoot></table></div>`;
}

/* --------------------------------------------------------------- render */
let ultimo = null;
let pestana = '__todos';

function bloqueVacio(periodo) {
  return `<div class="card"><h2>Sin datos</h2><p class="cap">No hubo sesiones entre ${esc(periodo.desde)} y ${esc(periodo.hasta)}.</p></div>`;
}

/* Cuerpo del reporte para un bloque de embudo: sirve igual para el total del
 * período y para una pestaña de gestor, porque tienen la misma forma. */
function cuerpo(b, periodo, gestor) {
  const dias = b.por_dia || [], tiendas = b.por_tienda || [];
  if (!b.ingresos) return bloqueVacio(periodo);
  const leyenda = SERIES.map((s) =>
    `<span><i class="dot" style="background:${s.color}"></i>${esc(s.nombre)}</span>`).join('');
  const etiquetaIngresos = gestor ? 'Sesiones que trabajó' : 'Ingresaron al chat';

  return `
    <div class="card">
      <div class="hero-row">
        <div>
          <div class="hero-num">${pct(b.pct_conversion_global)}</div>
          <div class="hero-lab">Conversión global<br>de ingreso a derivación a tienda</div>
        </div>
        <div class="tiles">
          <div><div class="tile-v">${fmt(b.ingresos)}</div><div class="tile-l">${esc(etiquetaIngresos)}</div></div>
          <div><div class="tile-v">${fmt(b.personas_unicas)}</div><div class="tile-l">Personas únicas</div></div>
          <div><div class="tile-v">${fmt(b.atendidos)}</div><div class="tile-l">Atendidos</div></div>
          <div><div class="tile-v">${fmt(b.derivados_tienda)}</div><div class="tile-l">Derivados a tienda</div></div>
        </div>
      </div>
      <p class="cap" style="margin:20px 0 0">Del ${esc(periodo.desde)} al ${esc(periodo.hasta)}.${
        gestor ? ` Sólo las sesiones atendidas por ${esc(gestor)}.` : ''}${
        b.sin_cerrar ? ` ${fmt(b.sin_cerrar)} sesiones siguen abiertas.` : ''}</p>
    </div>

    <div class="card">
      <h2>Embudo por etapas</h2>
      <p class="cap">Cada etapa exige haber pasado la anterior; el porcentaje es sobre la etapa previa.</p>
      <div class="chart">${svgEmbudo(b)}</div>
    </div>

    <div class="card">
      <h2>Evolución diaria</h2>
      <p class="cap">Sesiones por día en cada etapa. Las derivaciones se cuentan el día en que cerró el chat, no el día en que entró.</p>
      <div class="legend">${leyenda}</div>
      <div class="chart">${svgDiario(dias)}</div>
    </div>

    <div class="card">
      <h2>Detalle por día</h2>
      <p class="cap">Los mismos valores del gráfico, en tabla.</p>
      ${tablaDiaria(dias, b)}
      <button type="button" id="csv" style="margin-top:16px">Descargar CSV</button>
    </div>

    ${tiendas.length ? `<div class="card">
      <h2>Derivaciones por tienda</h2>
      <p class="cap">Una tienda por derivación: el total cuadra con los ${fmt(b.derivados_tienda)} derivados del embudo.</p>
      <div class="chart">${svgTiendas(tiendas)}</div>
      ${tablaTiendas(tiendas, b.derivados_tienda)}
    </div>` : ''}`;
}

function barraPestanas(data) {
  const ges = data.por_gestor || [];
  if (!ges.length) return '';
  const botones = [{ k: '__todos', lab: 'Todos', n: data.totales.atendidos }]
    .concat(ges.map((g) => ({ k: g.gestor, lab: g.gestor, n: g.atendidos })))
    .map((b) => `<button type="button" class="tab" data-gestor="${esc(b.k)}" `
      + `aria-pressed="${b.k === pestana}">${esc(b.lab)} <span class="tabn">${fmt(b.n)}</span></button>`)
    .join('');
  return `<div class="card"><h2>Por gestor</h2>`
    + `<p class="cap">Cada pestaña muestra sólo las sesiones que atendió esa persona. `
    + `Los atendidos de todas las pestañas suman el total del período.</p>`
    + `<div class="tabs">${botones}</div></div>`;
}

/* Sólo aparece en el archivo suelto, que es el único que tiene las sesiones
 * crudas: es la vía para llevarle estos datos a un entorno sin salida de red
 * hacia Botmaker (el pipeline de Python los lee con --crudo). */
function tarjetaCrudo(data) {
  if (!data.crudo) return '';
  return `<div class="card">
      <h2>Datos crudos</h2>
      <p class="cap">Las ${fmt(data.crudo.total)} sesiones tal cual las devuelve la API, sin procesar.
      Sirve para reprocesarlas con <code>--crudo</code> sin volver a consultar Botmaker.</p>
      <button type="button" id="crudo">Descargar JSON crudo</button>
    </div>`;
}

function descargarCrudo() {
  if (!ultimo || !ultimo.crudo) return;
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(ultimo.crudo)], { type: 'application/json;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = `botmaker_crudo_${ultimo.periodo.desde}_a_${ultimo.periodo.hasta}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function pintar(data) {
  const ges = (data.por_gestor || []).find((g) => g.gestor === pestana);
  const bloque = ges || data.totales;
  if (!ges) { bloque.por_dia = data.por_dia; bloque.por_tienda = data.por_tienda; }
  $('cuerpo').innerHTML = cuerpo(bloque, data.periodo, ges ? ges.gestor : null);
  conectarTips($('cuerpo'));
  const btnCsv = $('csv');
  if (btnCsv) btnCsv.addEventListener('click', descargarCsv);
}

function render(data) {
  ultimo = data;
  pestana = '__todos';
  const sinDatos = !data.totales.ingresos;
  $('reporte').innerHTML = sinDatos ? bloqueVacio(data.periodo)
    : barraPestanas(data) + '<div id="cuerpo"></div>' + tarjetaCrudo(data)
      + `<p class="foot">Datos de Botmaker · generado el ${new Date().toLocaleString('es-PE')}</p>`;
  $('reporte').hidden = false;

  if (sinDatos) return;
  pintar(data);
  const btnCrudo = $('crudo');
  if (btnCrudo) btnCrudo.addEventListener('click', descargarCrudo);
  $('reporte').querySelectorAll('.tab').forEach((b) => b.addEventListener('click', () => {
    pestana = b.dataset.gestor;
    $('reporte').querySelectorAll('.tab').forEach((o) =>
      o.setAttribute('aria-pressed', String(o.dataset.gestor === pestana)));
    pintar(ultimo);
  }));
}

function descargarCsv() {
  if (!ultimo) return;
  const ges = (ultimo.por_gestor || []).find((g) => g.gestor === pestana);
  const dias = ges ? ges.por_dia : ultimo.por_dia;
  const cols = ['fecha', 'dia_semana', 'ingresos', 'personas_unicas', 'en_cola', 'atendidos',
    'derivados_tienda', 'sin_cerrar', 'provisional', 'pct_ingreso_a_cola', 'pct_cola_a_atendido',
    'pct_atendido_a_tienda', 'pct_conversion_global'];
  const filas = [cols.join(','), ...dias.map((d) => cols.map((c) => d[c] ?? '').join(','))];
  const url = URL.createObjectURL(new Blob([filas.join('\n')], { type: 'text/csv;charset=utf-8' }));
  const a = document.createElement('a');
  const suf = ges ? '_' + ges.gestor.replace(/[^\w]+/g, '-') : '';
  a.href = url;
  a.download = `embudo_${ultimo.periodo.desde}_a_${ultimo.periodo.hasta}${suf}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}
