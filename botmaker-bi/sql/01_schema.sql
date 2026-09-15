/* Esquema base: se persiste el grano de sesion y los agregados salen de vistas. */
IF OBJECT_ID('dbo.botmaker_sesion', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.botmaker_sesion
    (
        session_id       VARCHAR(120)  NOT NULL PRIMARY KEY,
        chat_id          VARCHAR(60)   NOT NULL,
        contact_id       VARCHAR(60)   NULL,
        channel_id       VARCHAR(120)  NULL,
        plataforma       VARCHAR(40)   NULL,
        fecha_hora_utc   DATETIME2(0)  NOT NULL,
        fecha_local      DATE          NOT NULL,
        origen           VARCHAR(60)   NULL,   -- Organic / Referral / WhatsAppTemplate
        cola             VARCHAR(60)   NULL,   -- AsesoresWeb, SAC, Retail, ...
        tipificacion     VARCHAR(80)   NULL,
        tiendas          VARCHAR(400)  NULL,   -- tags TDA* separados por coma
        en_cola          BIT           NOT NULL DEFAULT 0,
        atendido         BIT           NOT NULL DEFAULT 0,
        derivado_tienda  BIT           NOT NULL DEFAULT 0,
        tag_contactado   BIT           NOT NULL DEFAULT 0,
        cerrado          BIT           NOT NULL DEFAULT 0,
        actualizado_en   DATETIME2(0)  NOT NULL DEFAULT SYSUTCDATETIME()
    );

    /* El dashboard filtra siempre por fecha local. */
    CREATE INDEX IX_botmaker_sesion_fecha ON dbo.botmaker_sesion (fecha_local)
        INCLUDE (en_cola, atendido, derivado_tienda, chat_id);
END
GO
