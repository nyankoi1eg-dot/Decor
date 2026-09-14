'use strict';
/* Capa de datos de la versión servida: el backend habla con Botmaker. */
async function obtenerDatos({ desde, hasta, token, apikey }) {
  const headers = {};
  if (token) headers['X-Botmaker-Token'] = token;
  if (apikey) headers['X-API-Key'] = apikey;
  const r = await fetch(`/funnel/summary?desde=${desde}&hasta=${hasta}`, { headers });
  const cuerpo = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(cuerpo.detail || `El servidor respondió ${r.status}.`);
  return cuerpo;
}
