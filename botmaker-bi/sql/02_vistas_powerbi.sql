/* Vistas que consume Power BI. Al derivarse de la tabla de sesiones, los
   agregados nunca quedan desfasados respecto al detalle. */

CREATE OR ALTER VIEW dbo.vw_botmaker_embudo_diario AS
SELECT
    s.fecha_local                                   AS fecha,
    DATENAME(WEEKDAY, s.fecha_local)                AS dia_semana,
    COUNT(*)                                        AS ingresos,
    COUNT(DISTINCT s.chat_id)                       AS personas_unicas,
    SUM(CAST(s.en_cola AS INT))                     AS en_cola,
    SUM(CAST(s.atendido AS INT))                    AS atendidos,
    SUM(CAST(s.derivado_tienda AS INT))             AS derivados_tienda,
    CAST(100.0 * SUM(CAST(s.en_cola AS INT))
         / NULLIF(COUNT(*), 0) AS DECIMAL(5,1))     AS pct_ingreso_a_cola,
    CAST(100.0 * SUM(CAST(s.atendido AS INT))
         / NULLIF(SUM(CAST(s.en_cola AS INT)), 0) AS DECIMAL(5,1))        AS pct_cola_a_atendido,
    CAST(100.0 * SUM(CAST(s.derivado_tienda AS INT))
         / NULLIF(SUM(CAST(s.atendido AS INT)), 0) AS DECIMAL(5,1))       AS pct_atendido_a_tienda,
    CAST(100.0 * SUM(CAST(s.derivado_tienda AS INT))
         / NULLIF(COUNT(*), 0) AS DECIMAL(5,1))     AS pct_conversion_global
FROM dbo.botmaker_sesion AS s
GROUP BY s.fecha_local;
GO

/* Una fila por sesion y tienda: sirve para el corte por punto de venta.
   Un chat puede llevar mas de un tag TDA*, por eso hace falta desnormalizar. */
CREATE OR ALTER VIEW dbo.vw_botmaker_derivacion_tienda AS
SELECT
    s.fecha_local                      AS fecha,
    LTRIM(RTRIM(t.value))              AS tienda,
    COUNT(*)                           AS derivaciones
FROM dbo.botmaker_sesion AS s
CROSS APPLY STRING_SPLIT(ISNULL(s.tiendas, ''), ',') AS t
WHERE s.derivado_tienda = 1 AND LTRIM(RTRIM(t.value)) <> ''
GROUP BY s.fecha_local, LTRIM(RTRIM(t.value));
GO

/* Corte por cola de atencion (AsesoresWeb, SAC, Retail, ...). */
CREATE OR ALTER VIEW dbo.vw_botmaker_embudo_cola AS
SELECT
    s.fecha_local                            AS fecha,
    ISNULL(s.cola, 'SIN_COLA')               AS cola,
    COUNT(*)                                 AS ingresos,
    SUM(CAST(s.atendido AS INT))             AS atendidos,
    SUM(CAST(s.derivado_tienda AS INT))      AS derivados_tienda
FROM dbo.botmaker_sesion AS s
GROUP BY s.fecha_local, ISNULL(s.cola, 'SIN_COLA');
GO
