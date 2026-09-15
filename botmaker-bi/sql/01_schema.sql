/* Esquema base: se persiste el grano de sesion y los agregados salen de vistas. */
IF OBJECT_ID('dbo.botmaker_sesion', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.botmaker_sesion
    (
        session_id        VARCHAR(120)  NOT NULL PRIMARY KEY,
        chat_id           VARCHAR(60)   NOT NULL,
        contact_id        VARCHAR(60)   NULL,
        channel_id        VARCHAR(120)  NULL,
        plataforma        VARCHAR(40)   NULL,
        fecha_hora_utc    DATETIME2(0)  NOT NULL,
        fecha_local       DATE          NOT NULL,  -- dia en que ENTRO el chat
        fecha_cierre_local DATE         NULL,      -- dia en que cerro, NULL si sigue abierta
        /* Dia al que se imputa la derivacion: es el del CIERRE, porque es
           cuando el gestor tipifica. Un chat que entra el viernes y cierra el
           lunes deriva el lunes. NULL si la sesion no fue derivada. */
        fecha_derivacion  DATE          NULL,
        origen            VARCHAR(60)   NULL,   -- Organic / Referral / WhatsAppTemplate
        /* Sale del evento queue-set (info.queue). NO de chat.queueId, que
           GET /sessions no devuelve nunca y dejaba esta columna siempre NULL. */
        cola              VARCHAR(60)   NULL,   -- AsesoresWeb, SAC, Retail, ...
        /* Sale del evento conversation-close (info.typification): es la
           tipificacion de ESTA sesion, no el estado actual del chat. */
        tipificacion      VARCHAR(80)   NULL,
        /* UNA tienda por derivacion, o '(sin tienda identificada)'. Es lo que
           hace que el corte por tienda sume igual que derivado_tienda. */
        tienda            VARCHAR(80)   NULL,
        operador_cierre   VARCHAR(120)  NULL,
        agente_asignado   VARCHAR(120)  NULL,
        gestor            VARCHAR(120)  NULL,   -- quien la trabajo: cierre, si no asignacion
        tiendas           VARCHAR(400)  NULL,   -- todos los tags TDA*, solo para auditoria
        en_cola           BIT           NOT NULL DEFAULT 0,
        asignado          BIT           NOT NULL DEFAULT 0,  -- hubo assigned-to-agent
        cerrado_por_operador BIT        NOT NULL DEFAULT 0,  -- lo cerro una persona
        /* Criterio B: asignado O cerrado por un operador. Guardar las dos
           senales por separado permite recalcular el criterio A
           (solo asignado) sin volver a extraer de la API. */
        atendido          BIT           NOT NULL DEFAULT 0,
        derivado_tienda   BIT           NOT NULL DEFAULT 0,
        tag_contactado    BIT           NOT NULL DEFAULT 0,
        cerrado           BIT           NOT NULL DEFAULT 0,
        actualizado_en    DATETIME2(0)  NOT NULL DEFAULT SYSUTCDATETIME()
    );

    /* El dashboard filtra siempre por fecha local. */
    CREATE INDEX IX_botmaker_sesion_fecha ON dbo.botmaker_sesion (fecha_local)
        INCLUDE (en_cola, atendido, derivado_tienda, chat_id, cerrado);

    /* El corte por tienda y el diario agrupan por el dia de la derivacion. */
    CREATE INDEX IX_botmaker_sesion_derivacion ON dbo.botmaker_sesion (fecha_derivacion)
        INCLUDE (derivado_tienda, tienda, gestor);
END
GO
