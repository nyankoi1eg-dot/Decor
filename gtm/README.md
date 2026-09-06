# Modo daltónico en GTM — reset para visitantes recurrentes

`md-reset-prelude.html` es un bloque que se pega **al principio de la etiqueta HTML
personalizada que ya existe** en GTM, antes del `<style>` de marca y antes del
script del widget. No es una etiqueta nueva ni requiere tocar el sitio.

## El problema

El widget guarda su estado en `localStorage`, y ese estado sobrevive a cualquier
despliegue:

| Clave | Valor | Efecto si viene de una visita anterior |
|---|---|---|
| `md_popup_seen` | `"1"` | **El popup de lanzamiento no se vuelve a mostrar.** Este es el problema. |
| `md_on` | `"1"` / `"0"` | El modo queda como lo dejó el usuario. |
| `md_type` | `deuteranopia` … | El filtro elegido. |
| `md_preview` | `"1"` | Vista previa pegajosa: la activa `?md-preview` y ya **no se quita nunca**, así que quien abrió una URL de pruebas ve el widget aunque no toque. |

O sea: cualquiera que entrara durante las pruebas, o que cerrara el popup una vez,
tiene `md_popup_seen = "1"` y no verá nada del relanzamiento.

## Lo que hace el prólogo

**Reset manual por URL** — `https://decorcenter.pe/?mdReset=1`

Borra las cuatro claves y recarga la página ya limpia, sin el parámetro. Funciona en
cualquier ruta (`https://decorcenter.pe/lo-que-sea?mdReset=1`). Es para probar tú y
para pasársela al equipo.

**Reset automático por versión** — sube `RELAUNCH`

Se aplica **una sola vez a cada visitante**, sin que nadie tenga que abrir ninguna
URL. Esto es lo que arregla de verdad a los usuarios recurrentes: publicas el
contenedor con la fecha nueva y el popup vuelve a salir a todo el mundo.

Por defecto es un reset conservador, no un borrado:

- `KEEP_PREFERENCE = true` respeta `md_on` y `md_type`. A quien eligió un filtro no
  se le desactiva el modo; solo se le limpia `md_popup_seen` y `md_preview`.
- `SKIP_IF_ACTIVE = true` no repite el popup a quien ya tiene el modo activado —
  ese ya está convertido, el popup solo estorba.

Pon `KEEP_PREFERENCE = false` si lo que quieres es que el navegador quede
exactamente como el de un visitante nuevo.

## Nunca `localStorage.clear()`

`decorcenter.pe` es una tienda: vaciar el `localStorage` entero se llevaría por
delante carrito y sesión. Por eso el prólogo borra las cuatro claves `md_*` por
nombre y nada más.

## Sin publicar nada en GTM

Para limpiar tu propio navegador ahora mismo, en la consola de `decorcenter.pe`:

```js
['md_on','md_type','md_popup_seen','md_preview','md_relaunch']
  .forEach(k => localStorage.removeItem(k));
location.reload();
```

Como marcador (arrastra a la barra de favoritos y púlsalo estando en la tienda):

```
javascript:['md_on','md_type','md_popup_seen','md_preview','md_relaunch'].forEach(function(k){localStorage.removeItem(k)});location.href=location.origin+location.pathname;
```

Un `javascript:` no se puede mandar por chat ni por correo: los navegadores lo
descartan al pegarlo en la barra de direcciones. Para compartir, usa `?mdReset=1`.

## Dos detalles de la etiqueta actual

1. **El `<script src="…/clients/decorcenter.js" defer>` está repetido.** El widget
   se protege con `window.__modoDaltonico`, así que no se inicializa dos veces,
   pero el fichero se descarga dos veces. Deja una sola copia.
2. **Si en la etiqueta conviven el widget en línea y el `<script src>`, uno de los
   dos sobra.** Gana el que se ejecute primero y el otro se descarta por la misma
   guarda; los arreglos que subas a Vercel no llegarían nunca. Elige una vía: o el
   código en línea en GTM, o el fichero externo. Si te quedas con el externo,
   añádele un `?v=2026-09-06` al `src` para invalidar la copia cacheada.

## Orden de ejecución

Dentro de una misma etiqueta de GTM el `<script>` en línea se ejecuta antes que
todo lo que venga después, así que el estado queda limpio antes de que el widget
llame a `buildUI()`. Con el activador recomendado (*DOM Ready · All Pages*) el
widget arranca inmediatamente al fireear la etiqueta, así que el prólogo tiene que
ir dentro de la misma etiqueta, no en una aparte: dos etiquetas distintas no
garantizan orden entre sí.
