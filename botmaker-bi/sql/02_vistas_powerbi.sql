/* Vistas que consume Power BI. Al derivarse de la tabla de sesiones, los
   agregados nunca quedan desfasados respecto al detalle. */

/* Embudo diario.

   ATENCION CON DOS COSAS:

   1. Ingresos, cola y atendidos se cuentan el dia en que ENTRO el chat; las
      derivaciones, el dia en que CERRO. Por eso no salen de un solo GROUP BY:
      un dia puede tener derivaciones sin tener ingresos, y pct_atendido_a_tienda
      puede pasar de 100% en un dia suelto. En el periodo completo cierra.

   2. personas_unicas NO ES ADITIVA. Es un COUNT(DISTINCT) por dia: sumar la
      columna cuenta dos veces a quien escribe dos dias distintos. En Power BI
      hay que medirla con DISTINCTCOUNT(botmaker_sesion[chat_id]) sobre el
      filtro activo, nunca con SUM sobre esta vista. Se deja aca solo para el
      detalle diario. */
CREATE OR ALTER VIEW dbo.vw_botmaker_embudo_diario AS
WITH por_ingreso AS (
    SELECT
        s.fecha_local                              AS fecha,
        COUNT(*)                                   AS ingresos,
        COUNT(DISTINCT s.chat_id)                  AS personas_unicas,
        SUM(CAST(s.en_cola AS INT))                AS en_cola,
        SUM(CAST(s.atendido AS INT))               AS atendidos,
        SUM(1 - CAST(s.cerrado AS INT))            AS sin_cerrar
    FROM dbo.botmaker_sesion AS s
    GROUP BY s.fecha_local
),
por_derivacion AS (
    SELECT
        s.fecha_derivacion                         AS fecha,
        COUNT(*)                                   AS derivados_tienda
    FROM dbo.botmaker_sesion AS s
    WHERE s.derivado_tienda = 1 AND s.fecha_derivacion IS NOT NULL
    GROUP BY s.fecha_derivacion
),
dias AS (
    SELECT fecha FROM por_ingreso
    UNION
    SELECT fecha FROM por_derivacion
)
SELECT
    d.fecha,
    DATENAME(WEEKDAY, d.fecha)                     AS dia_semana,
    ISNULL(i.ingresos, 0)                          AS ingresos,
    ISNULL(i.personas_unicas, 0)                   AS personas_unicas,
    ISNULL(i.en_cola, 0)                           AS en_cola,
    ISNULL(i.atendidos, 0)                         AS atendidos,
    ISNULL(v.derivados_tienda, 0)                  AS derivados_tienda,
    ISNULL(i.sin_cerrar, 0)                        AS sin_cerrar,
    /* Los dias con sesiones abiertas son provisionales: las conversaciones
       siguen vivas y sus tipificaciones todavia pueden cambiar. */
    CAST(CASE WHEN ISNULL(i.sin_cerrar, 0) > 0 THEN 1 ELSE 0 END AS BIT) AS provisional,
    CAST(100.0 * ISNULL(i.en_cola, 0)
         / NULLIF(i.ingresos, 0) AS DECIMAL(5,1))  AS pct_ingreso_a_cola,
    CAST(100.0 * ISNULL(i.atendidos, 0)
         / NULLIF(i.en_cola, 0) AS DECIMAL(5,1))   AS pct_cola_a_atendido,
    CAST(100.0 * ISNULL(v.derivados_tienda, 0)
         / NULLIF(i.atendidos, 0) AS DECIMAL(5,1)) AS pct_atendido_a_tienda,
    CAST(100.0 * ISNULL(v.derivados_tienda, 0)
         / NULLIF(i.ingresos, 0) AS DECIMAL(5,1))  AS pct_conversion_global
FROM dias AS d
LEFT JOIN por_ingreso    AS i ON i.fecha = d.fecha
LEFT JOIN por_derivacion AS v ON v.fecha = d.fecha;
GO

/* Corte por punto de venta.

   UNA fila por sesion derivada, no una por tag. La columna tienda ya trae una
   sola tienda por derivacion (o '(sin tienda identificada)'), asi que
   SUM(derivaciones) == SUM(derivados_tienda) del embudo, exacto.

   Antes esto desnormalizaba los tags TDA* con STRING_SPLIT y contaba pares
   (sesion x tag): un chat con dos tiendas sumaba dos veces y el corte daba
   152 contra 117 derivados reales. */
CREATE OR ALTER VIEW dbo.vw_botmaker_derivacion_tienda AS
SELECT
    s.fecha_derivacion                 AS fecha,
    ISNULL(s.tienda, '(sin tienda identificada)') AS tienda,
    COUNT(*)                           AS derivaciones
FROM dbo.botmaker_sesion AS s
WHERE s.derivado_tienda = 1
GROUP BY s.fecha_derivacion, ISNULL(s.tienda, '(sin tienda identificada)');
GO

/* Corte por cola de atencion (AsesoresWeb, SAC, Retail, ...).

   La cola sale del evento queue-set. Cuando se leia de chat.queueId --que
   GET /sessions no devuelve-- esta vista agrupaba el 100% de las filas bajo
   SIN_COLA y no servia para nada. */
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

/* Corte por gestor: alimenta las pestanas por gestor del reporte.

   Solo sesiones ATENDIDAS: un chat que murio en el bot no tiene gestor a quien
   atribuirselo. Por eso SUM(atendidos) es el total del periodo pero
   SUM(ingresos) no lo es. */
CREATE OR ALTER VIEW dbo.vw_botmaker_embudo_gestor AS
SELECT
    s.fecha_local                            AS fecha,
    ISNULL(s.gestor, '(sin gestor identificado)') AS gestor,
    COUNT(*)                                 AS atendidos,
    SUM(CAST(s.derivado_tienda AS INT))      AS derivados_tienda,
    /* Separadas permiten reconstruir el criterio A sin reextraer. */
    SUM(CAST(s.asignado AS INT))             AS asignados,
    SUM(CASE WHEN s.cerrado_por_operador = 1 AND s.asignado = 0
             THEN 1 ELSE 0 END)              AS cerrados_sin_asignar,
    CAST(100.0 * SUM(CAST(s.derivado_tienda AS INT))
         / NULLIF(COUNT(*), 0) AS DECIMAL(5,1)) AS pct_atendido_a_tienda
FROM dbo.botmaker_sesion AS s
WHERE s.atendido = 1
GROUP BY s.fecha_local, ISNULL(s.gestor, '(sin gestor identificado)');
GO
