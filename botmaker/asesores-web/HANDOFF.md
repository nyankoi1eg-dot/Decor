# Canal Asesores Web — reporte de leads (Botmaker)

Estado del análisis al 11-sep-2026, para retomar en una sesión nueva.

Reporte publicado: https://claude.ai/code/artifact/fcc35ab3-c51b-4e63-8a45-e3274a875293

## Para retomar

```bash
cd botmaker/asesores-web/scripts
python descargar.py 2026-09-01 2026-09-10 3   # 3 pasadas: la paginación no es determinística
python clasificar.py 2026-09-01 2026-09-10
```

La credencial la inyecta el proxy en la cabecera `access-token`. **El campo Prefijo
debe estar vacío**: si tiene `Bearer`, la API devuelve 401 y el `Reason-Phrase` de la
respuesta muestra el token con `Bearer` adelante. Se corrige en
claude.ai/code → selector de entorno → engranaje → Credenciales de API.

## Cómo consultar la API

- Endpoint `GET /v2.0/chats`, parámetros `from` / `to` **más** `long-term-search=true`
  (sin ese último devuelve 400). Se pagina siguiendo `nextPage` hasta que venga vacío;
  hay páginas intermedias con 0 items que **no** significan el final.
- Filtrar por `lastSessionCreationTime`, **no** por `creationTime`: este último es la
  fecha de alta del contacto y llega hasta 2022 para clientes que ya habían escrito.
- Perú es UTC−5 fijo. Se descarga una ventana UTC más amplia y se recorta en local.
- **La paginación no es determinística.** Dos recorridos completos e independientes
  devolvieron conjuntos distintos: 4 chats en uno y ausentes del otro, 1 al revés.
  Por eso se descarga varias veces y se une por `chatId`.

## Alcance

- Denominador: **todos** los chats del período, no solo los que traen tag.
- El número retirado **+51 993 313 227** (`channelId` `decorcenter-whatsapp-51993313227`)
  se separa del funnel y se reporta aparte.
- Los chats sin `queueId` **sí son** de Asesores Web: llevan `Asesores_Venta`,
  `CONTACTADO` y `ABANDONO_DE_COMPRA`. Excluirlos sería un error — `queueId` no
  siempre se persiste.

## Regla de desenlace

El tag define la etapa; la tipificación explica el desenlace y lo determina cuando no
hay tag de estado. Orden de prioridad:

1. **Compró** — gana sobre cualquier otro estado, y ahí termina
2. **Solicita ubicación** — prioridad sobre el tag, salvo que haya comprado
3. **Derivado**
4. **Abandono de compra** — se desglosa por tipificación en una subsección
5. Resto de tipificaciones
6. Solo contactado
7. Sin tag ni tipificación — dato ciego

## Resultados del período 1–10 sep 2026

Cifras completas en `datos/resultados-2026-09-01_10.json`.

| | |
|---|---|
| Total recuperado | 825 |
| Número vigente | 791 |
| Número antiguo | 34 |
| **Cuadre** | **exacto** |

Desenlaces: Abandono 504 · Derivado 137 · Compró 15 · Solicita ubicación 22 ·
Sin tag ni tipificación 39 · resto 74.

**Hallazgo principal — la pauta no convierte.** De los leads comerciales, 316 vienen de
click-to-WhatsApp y 268 son orgánicos:

| | Pauta | Orgánico |
|---|---|---|
| Derivación | 4.7% | 47.8% |
| Cierre | **0%** | 11.7% |
| Abandono | 95.3% | 48.9% |

Las 15 compras del período son **todas orgánicas**. No es artefacto de medición: ambos
grupos tienen operador asignado casi por igual (362/390 contra 395/401) y el referral
aparece los diez días. La diferencia está en la tipificación — 289 de 390 chats con
referral cierran como `Lead_NO_calificado`.

## Lo que el registro no permite medir

- **Cinco de los siete tags del manual no existen.** `EN_ATENCIÓN`,
  `DERIVADO_PERO_NO_COMPRO` y `RECOMPRA` tienen cero ocurrencias — por eso dos de las
  seis tasas de la sección 9 no se pueden calcular. `DERIVADOS_A_TIENDA` y
  `CLIENTE_COMPRO` aparecen solo como `DERIVADOS` y `Cliente compro`.
- **Las variables `U.TDA.*` no existen.** Las tiendas se marcan como tags
  (`TDAMOLINA`, `TDASALAVERRY`…). `UTDACORPORATIVO` no está en el manual.
- **El 94% de las tipificaciones está fuera del manual**: 548 de 584 leads cierran con
  `Lead_Calificado` o `Lead_NO_calificado`, que no figuran en las diez documentadas.
- **13 derivaciones sin tag.** Chats con tag de tienda, operador y notas pero sin
  `DERIVADOS`: la tasa de derivación es un piso.
- **9 de las 15 compras no tienen tag de derivación** — venta registrada sin el paso previo.
- **3 chats con `Sin_respuesta`**, que es exclusiva de la cola SAC y no debe aparecer acá.
- **Hueco del 5 de septiembre**: 5 chats contra 43–159 los demás días. Sin resolver.
- **825 es un piso, no un total certificado** (ver paginación no determinística).

## Preguntas abiertas

1. **¿Qué significa `Lead_NO_calificado`?** Explica 400 de los 504 abandonos y no está
   documentado. Si es "sin intención de compra", "sin presupuesto" o "fuera del público
   objetivo" cambia la lectura del canal, sobre todo la del tráfico pago. Lo sabe el
   equipo de gestores, no la API.
2. **`NOPRODUCTO` es ambiguo** — ¿"producto sin stock" o "no tenemos ese producto"?
   Son cosas distintas para el hallazgo de catálogo.
3. **¿Las tipificaciones de no-lead deben ganarle al tag, como `SolicitaUbicación`?**
   Hoy 38 `CATEGORIIA` + 30 `Consulta_atendida` + 3 `Propaganda` caen dentro de los 504
   abandonos porque llevan el tag `ABANDONO_DE_COMPRA`. Son 71 chats.
4. **Nombres oficiales de las tipificaciones.** Los de este análisis son una lectura de
   los slugs, no el nombre de la consola.

## Nota sobre los datos

Este directorio guarda **solo cifras agregadas y scripts**. Los chats crudos incluyen
teléfonos y nombres de clientes y no se versionan: se vuelven a descargar con
`descargar.py`. El `.gitignore` cubre `raw_*.json`.
