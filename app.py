# app.py
import streamlit as st
from optimizador_logic import optimizar_cortes_para_un_largo_rollo # Importa tu función desde el otro archivo
import math # También necesitas math para la parte de advertencias
import pandas as pd
from PIL import Image  # Importa la librería PIL

# --- SECCIÓN DE INTERFAZ DE USUARIO CON STREAMLIT ---
def main():
    st.set_page_config(layout="wide") # Para usar todo el ancho de la pantalla
    try:
        imagen = Image.open("LOGO (1).png")  # Esta línea y la siguiente deben estar indentadas
        st.image(imagen, width=100)
    except FileNotFoundError:
        st.warning("No se encontró el archivo de imagen 'LOGO (1).png'.")
    
        # ... el resto de tu código de la aplicación ...
    st.title("✂️ Optimizador de Cortes de tiras Jenny")
    st.markdown("Esta herramienta te ayuda a calcular la forma más eficiente de cortar tiras Jenny para minimizar desperdicios y la cantidad de rollos.")

    ROLLOS_DISPONIBLES = [5.0, 10.0, 40.0]

    st.header("1. Selecciona el Rollo de Material")
    largo_rollo_seleccionado = st.selectbox(
        "Elige el largo del rollo que vas a utilizar (en metros):",
        options=ROLLOS_DISPONIBLES,
        format_func=lambda x: f"{x:.1f} metros"
    )
    st.info(f"Has seleccionado rollos de **{largo_rollo_seleccionado:.1f} metros**.")

    st.header("2. Ingresa los Cortes Solicitados")
    st.markdown("Introduce cada corte con su **largo** y **cantidad** (ej: `1.2 5` para 5 piezas de 1.2 metros). Presiona **'Añadir Corte'** después de cada uno.")

    # Usamos st.session_state para mantener los cortes en la memoria de la app entre interacciones
    if 'solicitudes_cortes_ingresadas' not in st.session_state:
        st.session_state.solicitudes_cortes_ingresadas = {}

    col1, col2, col3 = st.columns([0.4, 0.4, 0.2])
    with col1:
        largo_input = st.number_input("Largo del Corte (metros)", min_value=0.01, value=0.1, step=0.1, key="largo_input")
    with col2:
        cantidad_input = st.number_input("Cantidad Solicitada", min_value=1, value=1, step=1, key="cantidad_input")
    with col3:
        st.write("") # Espacio para alinear el botón
        st.write("")
        if st.button("➕ Añadir Corte", key="add_button"):
            if largo_input > 0 and cantidad_input > 0:
                st.session_state.solicitudes_cortes_ingresadas[largo_input] = \
                    st.session_state.solicitudes_cortes_ingresadas.get(largo_input, 0) + cantidad_input
                st.success(f"Se añadió {cantidad_input} cortes de {largo_input}m.")
            else:
                st.error("Por favor, ingresa valores positivos para largo y cantidad.")

    st.subheader("Cortes Actuales:")
    if st.session_state.solicitudes_cortes_ingresadas:
        # Crear una lista de diccionarios para el dataframe
        data_for_df = []
        for largo, cantidad in st.session_state.solicitudes_cortes_ingresadas.items():
            data_for_df.append({"Largo (m)": largo, "Cantidad": cantidad})

        # Ordenar por largo para una mejor visualización
        import pandas as pd # Necesitas pandas para st.dataframe, se instala con streamlit
        df_cortes = pd.DataFrame(data_for_df).sort_values(by="Largo (m)", ascending=False)
        st.dataframe(df_cortes, use_container_width=True)

        if st.button("🗑️ Limpiar Todos los Cortes", key="clear_button"):
            st.session_state.solicitudes_cortes_ingresadas = {}
            st.experimental_rerun() # Reiniciar la app para reflejar el cambio
    else:
        st.info("Aún no has añadido ningún corte.")

    st.header("3. Ejecutar Optimización")
    if st.button("🚀 Optimizar Cortes", key="optimize_button"):
        if not st.session_state.solicitudes_cortes_ingresadas:
            st.warning("Por favor, añade al menos un corte antes de optimizar.")
        else:
            with st.spinner("Calculando la mejor optimización..."):
                estado, num_rollos_totales, desperdicio_total, detalles_cortes_por_rollo, advertencias_cortes_grandes = \
                    optimizar_cortes_para_un_largo_rollo(largo_rollo_seleccionado, st.session_state.solicitudes_cortes_ingresadas)

            st.subheader("--- Resumen Final de la Optimización ---")
            st.write(f"Largo de rollo seleccionado para el cálculo: **{largo_rollo_seleccionado:.1f} metros**")
            st.write(f"Estado de la solución: **{estado}**")

            if estado in ['Optimal', 'Optimal (Solo Cortes Mayores al Rollo Seleccionado)', 'No hay patrones válidos generados para cortes pequeños']:
                st.metric(label="Número TOTAL de rollos necesarios", value=f"{num_rollos_totales:.2f} unidades")
                st.metric(label="Desperdicio TOTAL de material", value=f"{desperdicio_total:.2f} metros")

                if advertencias_cortes_grandes:
                    st.warning("--- ¡INFORMACIÓN IMPORTANTE SOBRE CORTES GRANDES! ---")
                    st.markdown("Los siguientes cortes individuales son **más largos** que el rollo de material seleccionado.")
                    st.markdown("Esto significa que cada una de estas piezas finales se formará **uniendo segmentos de varios rollos**.")
                    st.markdown("El cálculo de rollos y desperdicio ya considera la suma total de estos cortes grandes.")
                    for adv in advertencias_cortes_grandes:
                        st.write(f"  - Solicitud: **{adv['cantidad']}x de {adv['largo']:.1f}m.**")


                st.subheader("--- Detalle de cómo se usarán los rollos ---")
                st.markdown("Cada línea representa un **rollo físico** y cómo se cortará.")
                if detalles_cortes_por_rollo:
                    detalles_cortes_por_rollo.sort(key=lambda x: (x.get('Tipo_Rollo', 0), x.get('Rollo_ID', '')))

                    for rollo_info in detalles_cortes_por_rollo:
                        tipo_rollo = rollo_info["Tipo_Rollo"]
                        cortes = rollo_info["Cortes_en_rollo"]
                        desperdicio_rollo = rollo_info["Desperdicio_en_rollo"]
                        metros_consumidos = rollo_info.get("Metros_Consumidos_en_este_rollo", tipo_rollo - desperdicio_rollo)

                        if "RESUMEN_PIEZAS_GRANDES" in rollo_info["Rollo_ID"]:
                            st.write(f"  - **{rollo_info['Rollo_ID']}** (Tipo Rollo: {tipo_rollo:.1f}m): {cortes[0]} (Rollos físicos asignados: {rollo_info['Rollos_Fisicos_Asignados']:.2f}, Desperdicio para estas piezas: {desperdicio_rollo:.2f}m)")
                        else:
                            st.write(f"  - **{rollo_info['Rollo_ID']}** (Tipo Rollo: {tipo_rollo:.1f}m): Cortes {cortes} (Usado: {metros_consumidos:.2f}m, Desperdicio en este rollo: {desperdicio_rollo:.2f}m)")
                else:
                    st.info("  No se generaron detalles de cortes por rollo.")

            elif estado == 'Infeasible':
                st.error("\nLa solución es **INFACTIBLE**.")
                st.warning("No es posible cumplir con todos los cortes solicitados usando rollos de este largo.")
                st.markdown("Esto puede ocurrir si la suma total de material solicitado (incluyendo cortes grandes y pequeños) excede lo que un número razonable de rollos puede proveer, o si no hay patrones de corte válidos.")
                if advertencias_cortes_grandes:
                    st.markdown("\nConsidera que los siguientes cortes individuales son más grandes que el rollo seleccionado:")
                    for corte_grande_info in advertencias_cortes_grandes:
                        st.write(f"  - Solicitud: **{corte_grande_info['cantidad']}x de {corte_grande_info['largo']:.1f}m.**")
            else:
                st.error(f"No se pudo encontrar una solución óptima para los cortes solicitados. Estado del optimizador: **{estado}**")
                st.markdown("Por favor, revisa tus entradas o la longitud del rollo seleccionado.")

if __name__ == "__main__":
    main()
