# Decor Center — repositorio de trabajo

## Análisis del canal Asesores Web (Botmaker)

Todo en `botmaker/asesores-web/`. **Leer `HANDOFF.md` antes de tocar nada**: documenta
el estado del análisis, las rarezas de la API y las decisiones ya tomadas con el canal.

- `HANDOFF.md` — estado, reglas de clasificación, hallazgos y preguntas abiertas
- `scripts/` — descarga, lectura de mensajes y clasificación reproducibles
- `datos/` — cifras agregadas por período

Reporte publicado: https://claude.ai/code/artifact/fcc35ab3-c51b-4e63-8a45-e3274a875293

### Cosas que cuestan horas si no se saben

- La credencial de Botmaker va en la cabecera `access-token` **sin prefijo**. Si el campo
  Prefijo tiene `Bearer`, la API responde 401 y el `Reason-Phrase` muestra el token
  contaminado. El token expira: un 401 a mitad de trabajo suele ser eso, no un error de código.
- `GET /v2.0/chats` exige `long-term-search=true` junto con `from`/`to`, o devuelve 400.
- **La paginación no es determinística.** Dos recorridos completos devuelven conjuntos
  distintos; hay que hacer varias pasadas y unir por `chatId`. Ninguna cifra de total es
  definitiva con una sola pasada.
- Filtrar por `lastSessionCreationTime`, nunca por `creationTime` (fecha de alta del
  contacto, llega hasta 2022).
- Perú es UTC−5 fijo.
- Los chats sin `queueId` igual son de Asesores Web.
- Al deduplicar entre pasadas, conservar la copia **más reciente**: los tags se
  siguen agregando después de la conversación.
- Para leer mensajes el parámetro es `chat-id`. `chatId` se acepta y **se ignora**,
  devolviendo el flujo global del período — error silencioso.
- Un 401 a mitad de trabajo no es expiración: el token vence en 2031. Es límite
  de volumen, y se recupera solo.

### Al reportar sobre estos datos

El vocabulario real **no coincide con el manual**: faltan cinco de los siete tags,
las variables `U.TDA.*` no existen y el 71% de los cierres usa tipificaciones que el
manual no define. Solo vale lo que está en el manual; lo demás no clasifica.

**La API no devuelve todos los tags que muestra la consola**, así que clasificar solo
por tags subestima. Donde el tag no explica el cierre, leer los mensajes del chat
(`scripts/leer_mensajes.py`).

No rellenar con estimaciones lo que el registro no tiene: va a un cubo explícito de
dato ciego.

## Otros

`.mcp.json` configura el servidor MCP de Google Analytics 4 para sesiones remotas.
