import streamlit as st
from optimizador_logic import optimizar_cortes_para_un_largo_rollo
import math
import pandas as pd
import collections
from PIL import Image # Necesario para cargar la imagen

# --- La función obtener_fuente_adecuada ha sido eliminada ---

def main():
    st.set_page_config(layout="wide") # Para usar todo el ancho de la pantalla
    
    # --- AGREGAR IMAGEN LOCAL ---
    try:
        imagen = Image.open("LOGO (1).png")
        st.image(imagen, width=200) # Ajusta el ancho según sea necesario
    except FileNotFoundError:
        st.warning("No se encontró el archivo de imagen 'LOGO (1).png'.")
    
    st.title("✂️ Optimizador de Cortes de Material")
    st.markdown("Esta herramienta te ayuda a calcular la forma más eficiente de cortar material lineal para minimizar desperdicios y la cantidad de rollos.")

    ROLLOS_DISPONIBLES = [5.0, 10.0, 40.0]

    st.header("1. Selecciona el Rollo de Material")
    largo_rollo_seleccionado = st.selectbox(
        "Elige el largo del rollo que vas a utilizar (en metros):",
        options=ROLLOS_DISPONIBLES,
        format_func=lambda x: f"{x:.1f} metros",
        key="largo_rollo_selector" 
    )
    st.info(f"Has seleccionado rollos de **{largo_rollo_seleccionado:.1f} metros**.")

    st.header("2. Ingresa los Cortes Solicitados")
    st.markdown("Introduce cada corte con su **largo** y **cantidad** (ej: `1.2 5` para 5 piezas de 1.2 metros). Presiona **'Añadir Corte'** después de cada uno.")

    if 'solicitudes_cortes_ingresadas' not in st.session_state:
        st.session_state.solicitudes_cortes_ingresadas = {}

    col1, col2, col3 = st.columns([0.4, 0.4, 0.2])
    with col1:
        largo_input = st.number_input("Largo del Corte (metros)", min_value=0.01, value=0.1, step=0.1, key="largo_input")
    with col2:
        cantidad_input = st.number_input("Cantidad Solicitada", min_value=1, value=1, step=1, key="cantidad_input")
    with col3:
        st.write("") 
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
        cortes_list = sorted(st.session_state.solicitudes_cortes_ingresadas.items(), key=lambda item: item[0], reverse=True)
        
        for i, (largo, cantidad) in enumerate(cortes_list):
            col_l, col_c, col_del = st.columns([0.4, 0.4, 0.2])
            with col_l:
                st.write(f"**{largo:.2f} m**")
            with col_c:
                st.write(f"**{cantidad} unidades**")
            with col_del:
                if st.button("🗑️ Eliminar", key=f"delete_cut_{largo}_{i}"):
                    del st.session_state.solicitudes_cortes_ingresadas[largo]
                    st.experimental_rerun() 
        
        st.markdown("---") 
        if st.button("🗑️ Limpiar Todos los Cortes", key="clear_all_button"):
            st.session_state.solicitudes_cortes_ingresadas = {}
            st.experimental_rerun() 
    else:
        st.info("Aún no has añadido ningún corte.")

    # --- La sección "4. Configuración de Fuentes LED" ha sido eliminada ---

    # --- SLIDER PARA CONTROLAR EL LÍMITE DE PATRONES ---
    st.header("3. Opciones Avanzadas de Optimización") # <--- NUMERACIÓN AJUSTADA
    max_items_per_pattern = st.slider(
        "Máximo de piezas por patrón de corte (para rendimiento)",
        min_value=5, max_value=25, value=15, step=1,
        help="Controla la complejidad de los patrones de corte. Un número más bajo (ej. 5-10) es más rápido pero podría ser menos óptimo. Un número más alto (ej. 20-25) es más lento pero puede encontrar mejores soluciones para muchos cortes pequeños. Si la aplicación se cuelga, reduce este valor.",
        key="max_pattern_items_slider" 
    )

    st.header("4. Ejecutar Optimización") # <--- NUMERACIÓN Y TEXTO AJUSTADOS
    if st.button("🚀 Optimizar Cortes", key="optimize_button"): # <--- TEXTO DEL BOTÓN AJUSTADO
        if not st.session_state.solicitudes_cortes_ingresadas:
            st.warning("Por favor, añade al menos un corte antes de optimizar.")
        else:
            with st.spinner("Calculando la mejor optimización..."):
                estado, num_rollos_totales, desperdicio_total, detalles_cortes_por_rollo, advertencias_cortes_grandes = \
                    optimizar_cortes_para_un_largo_rollo(
                        largo_rollo_seleccionado, 
                        st.session_state.solicitudes_cortes_ingresadas, 
                        max_items_per_pattern=max_items_per_pattern 
                    )
            
            st.subheader("--- Resumen Final de la Optimización de Material ---")
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
                    
                # --- La sección de Cálculo de Fuentes ha sido eliminada ---
                
                st.markdown("---") 

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
