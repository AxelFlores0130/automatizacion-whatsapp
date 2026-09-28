CREATE TABLE IF NOT EXISTS envios_resumen_ventas (
    id_envio BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    fecha DATE NOT NULL,
    horario TIME NOT NULL,
    chat_destino VARCHAR(255) NOT NULL,
    cantidad_ventas INT NOT NULL,
    total_vendido DECIMAL(12,2) NOT NULL,
    mensaje TEXT NOT NULL,
    estado ENUM('EN_PROCESO', 'ENVIADO', 'ERROR') NOT NULL,
    intentos INT UNSIGNED NOT NULL DEFAULT 1,
    fecha_intento DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_envio DATETIME NULL,
    PRIMARY KEY (id_envio),
    UNIQUE KEY uq_resumen_fecha_horario_destino (
        fecha,
        horario,
        chat_destino
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
