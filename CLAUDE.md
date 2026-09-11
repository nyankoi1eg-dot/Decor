# Decor Center — repositorio de trabajo

## Análisis del canal Asesores Web (Botmaker)

Todo en `botmaker/asesores-web/`. **Leer `HANDOFF.md` antes de tocar nada**: documenta
el estado del análisis, las rarezas de la API y las decisiones ya tomadas con el canal.

- `HANDOFF.md` — estado, reglas de clasificación, hallazgos y preguntas abiertas
- `CONVERSACION.md` — la conversación completa que originó el análisis
- `scripts/` — descarga y clasificación reproducibles
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

### Al reportar sobre estos datos

El vocabulario real de tags y tipificaciones **no coincide con el manual del canal**:
faltan cinco de los siete tags, las variables `U.TDA.*` no existen y el 94% de las
tipificaciones está fuera de lo documentado. No mapear a las categorías del manual sin
verificar contra el inventario real, y no rellenar con estimaciones lo que el registro
no tiene: va a un cubo explícito de dato ciego.

## Otros

`.mcp.json` configura el servidor MCP de Google Analytics 4 para sesiones remotas.
