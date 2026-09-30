from datetime import date

from mysql.connector import Error

from resumen_ventas.ventas_service import get_db_connection, obtener_resumen_ventas


def main():
    connection = None

    try:
        connection = get_db_connection()
        resumen = obtener_resumen_ventas(connection, date(2026, 9, 14))

        print("RESUMEN DE VENTAS")
        print(f"Fecha: {resumen['fecha']:%d/%m/%Y}")
        print(f"Ventas no apartado: {resumen['cantidad_no_apartado']}")
        print(f"Total no apartado: ${resumen['total_no_apartado']:,.2f}")
        print(f"Apartados: {resumen['cantidad_apartados']}")
        print(f"Total apartados: ${resumen['total_apartados']:,.2f}")
        print(f"Ventas realizadas: {resumen['cantidad_ventas']}")
        print(f"Total vendido: ${resumen['total_vendido']:,.2f}")

        valores_esperados = {
            "cantidad_no_apartado": 45,
            "total_no_apartado": 348397,
            "cantidad_apartados": 3,
            "total_apartados": 22883,
            "cantidad_ventas": 48,
            "total_vendido": 371280,
        }
        diferencias = {
            clave: (esperado, resumen[clave])
            for clave, esperado in valores_esperados.items()
            if resumen[clave] != esperado
        }
        if diferencias:
            print("PRUEBA INCORRECTA: hay valores que no coinciden.")
            for clave, (esperado, obtenido) in diferencias.items():
                print(f"{clave}: esperado {esperado}, obtenido {obtenido}")
        else:
            print("PRUEBA CORRECTA: coincide con la consulta validada del ingeniero.")

    except Error as error:
        print(f"Error de MySQL: {error}")
    finally:
        if connection is not None and connection.is_connected():
            connection.close()


if __name__ == "__main__":
    main()
