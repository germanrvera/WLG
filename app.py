# app.py
import streamlit as st
from optimizador_logic import optimizar_cortes_para_un_largo_rollo
import math
import pandas as pd
import collections
from PIL import Image

# --- FUNCIÓN PARA CALCULAR LA FUENTE MÁS ADECUADA (sin cambios) ---
def obtener_fuente_adecuada(consumo_requerido_watts, fuentes_disponibles_watts, factor_seguridad=1.2):
    consumo_ajustado = consumo_requerido_watts * factor_seguridad
    fuentes_suficientes = [f for f in fuentes_disponibles_watts if f >= consumo_ajustado]
    
    if not fuentes_suficientes:
        if fuentes_disponibles_watts:
            return max(fuentes_disponibles_watts), f"¡Advertencia! El consumo de {consumo_requerido_watts:.2f}W (ajustado a {consumo_ajustado:.2f}W) excede todas las fuentes disponibles. Se asigna la fuente más grande disponible ({max(fuentes_disponibles_watts):.0f}W)."
        else:
            return None, "No hay fuentes disponibles para asignar."
    
    return min(fuentes_suficientes), "" 

def main():
    st.set_page_config(layout="wide") 
    
    # --- AGREGAR IMAGEN LOCAL ---
    try:
        imagen = Image.open("LOGO(1).png")
        st.image(imagen, width=200) 
    except FileNotFoundError:
        st.warning("No se encontró el archivo de imagen 'LOGO(1).png'.")
    
    st.title("✂️ Optimizador de Cortes de Material")
    st.markdown("Esta herramienta te ayuda a calcular la forma más eficiente de cortar material lineal para minimizar desperdicios y la cantidad de rollos.")

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
                # Si el largo ya existe, se suma la cantidad. Si no, se añade.
                st.session_state.solicitudes_cortes_ingresadas[largo_input] = \
                    st.session_state.solicitudes_cortes_ingresadas.get(largo_input, 0) + cantidad_input
                st.success(f"Se añadió {cantidad_input} cortes de {largo_input}m.")
            else:
                st.error("Por favor, ingresa valores positivos para largo y cantidad.")
    
    st.subheader("Cortes Actuales:")
    if st.session_state.solicitudes_cortes_ingresadas:
        # Convertir el diccionario a una lista de tuplas para poder iterar y eliminar
        cortes_list = sorted(st.session_state.solicitudes_cortes_ingresadas.items(), key=lambda item: item[0], reverse=True)
        
        # Usar st.columns para mostrar cada corte con un botón de eliminar
        for i, (largo, cantidad) in enumerate(cortes_list):
            col_l, col_c, col_del = st.columns([0.4, 0.4, 0.2])
            with col_l:
                st.write(f"**{largo:.2f} m**")
            with col_c:
                st.write(f"**{cantidad} unidades**")
            with col_del:
                # El key del botón debe ser único
                if st.button("🗑️ Eliminar", key=f"delete_cut_{largo}_{i}"):
                    del st.session_state.solicitudes_cortes_ingresadas[largo]
                    st.experimental_rerun() # Recargar la app para que la lista se actualice
        
        st.markdown("---") # Separador para el botón de limpiar todo
        if st.button("🗑️ Limpiar Todos los Cortes", key="clear_all_button"):
            st.session_state.solicitudes_cortes_ingresadas = {}
            st.experimental_rerun() 
    else:
        st.info("Aún no has añadido ningún corte.")

    # --- SECCIÓN PARA LA CONFIGURACIÓN DE FUENTES DE PODER (sin cambios sustanciales aquí) ---
    st.header("4. Configuración de Fuentes LED")
    st.markdown("Ingresa el consumo de la tira LED y las potencias de las fuentes disponibles.")

    watts_por_metro_tira = st.number_input(
        "Consumo de la Tira LED (Watts por metro - W/m)",
        min_value=1.0, value=10.0, step=0.5,
        help="Ej. 10 W/m, 14.4 W/m, 20 W/m"
    )

    st.markdown("Ingresa las potencias de las fuentes disponibles (en Watts), separadas por comas. Ej: `30, 36, 40, 60, 100, 120, 150, 240, 320, 360`")
    fuentes_disponibles_str = st.text_input(
        "Potencias de Fuentes de Poder Disponibles (Watts)", 
        value="30, 36, 40, 60, 100, 120, 150, 240, 320, 360", 
        help="Las fuentes se eligen con un 20% de factor de seguridad por encima del consumo real."
    )
    
    fuentes_disponibles_watts = []
    try:
        fuentes_disponibles_watts = sorted([float(w.strip()) for w in fuentes_disponibles_str.split(',') if w.strip()])
        if not fuentes_disponibles_watts:
            st.warning("Por favor, introduce al menos una potencia de fuente disponible.")
    except ValueError:
        st.error("Formato de fuentes inválido. Asegúrate de usar números y comas (ej: 60, 100, 150).")
        fuentes_disponibles_watts = [] 

    factor_seguridad_fuentes = st.slider(
        "Factor de Seguridad para Fuentes (%)",
        min_value=5, max_value=50, value=20, step=5,
        help="El consumo real de la tira se multiplicará por este porcentaje extra para elegir una fuente que no trabaje al límite. Ej: 20% significa Consumo * 1.20"
    ) / 100 + 1

    # --- SLIDER PARA CONTROLAR EL LÍMITE DE PATRONES (sin cambios) ---
    st.header("5. Opciones Avanzadas de Optimización")
    max_items_per_pattern = st.slider(
        "Máximo de piezas por patrón de corte (para rendimiento)",
        min_value=5, max_value=25, value=15, step=1,
        help="Controla la complejidad de los patrones de corte. Un número más bajo (ej. 5-10) es más rápido pero podría ser menos óptimo. Un número más alto (ej. 20-25) es más lento pero puede encontrar mejores soluciones para muchos cortes pequeños. Si la aplicación se cuelga, reduce este valor."
    )


    st.header("6. Ejecutar Optimización y Cálculo de Fuentes") 
    if st.button("🚀 Optimizar Cortes y Calcular Fuentes", key="optimize_button"):
        if not st.session_state.solicitudes_cortes_ingresadas:
            st.warning("Por favor, añade al menos un corte antes de optimizar.")
        elif not fuentes_disponibles_watts:
            st.warning("Por favor, configura las fuentes disponibles antes de optimizar.")
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
                    
                # --- CÁLCULO Y ASIGNACIÓN DE FUENTES (sin cambios sustanciales) ---
                st.subheader("--- Cálculo de Fuentes de Poder por Corte ---")
                st.markdown("Se asigna una fuente de poder por cada corte solicitado.")
                
                total_fuentes_requeridas = collections.defaultdict(int)
                detalles_fuentes = []
                
                for largo_corte, cantidad_corte in st.session_state.solicitudes_cortes_ingresadas.items():
                    consumo_corte = largo_corte * watts_por_metro_tira
                    
                    fuente_asignada, advertencia_fuente = obtener_fuente_adecuada(
                        consumo_corte, fuentes_disponibles_watts, factor_seguridad_fuentes
                    )
                    
                    if fuente_asignada:
                        total_fuentes_requeridas[fuente_asignada] += cantidad_corte 
                        detalles_fuentes.append({
                            "Largo Corte (m)": largo_corte,
                            "Cantidad de Cortes": cantidad_corte,
                            "Consumo Total p/Corte (W)": f"{consumo_corte:.2f}",
                            "Consumo Ajustado (W)": f"{consumo_corte * factor_seguridad_fuentes:.2f}",
                            "Fuente Asignada (W)": f"{fuente_asignada:.0f}",
                            "Advertencia": advertencia_fuente
                        })
                    else:
                        detalles_fuentes.append({
                            "Largo Corte (m)": largo_corte,
                            "Cantidad de Cortes": cantidad_corte,
                            "Consumo Total p/Corte (W)": f"{consumo_corte:.2f}",
                            "Consumo Ajustado (W)": f"{consumo_corte * factor_seguridad_fuentes:.2f}",
                            "Fuente Asignada (W)": "N/A",
                            "Advertencia": advertencia_fuente if advertencia_fuente else "No se pudo asignar fuente."
                        })

                if detalles_fuentes:
                    df_fuentes = pd.DataFrame(detalles_fuentes)
                    st.dataframe(df_fuentes, use_container_width=True)

                    st.subheader("Resumen de Fuentes de Poder Necesarias:")
                    for fuente_w, cantidad in sorted(total_fuentes_requeridas.items()):
                        st.write(f"- Fuentes de **{fuente_w:.0f}W**: **{cantidad} unidades**")
                else:
                    st.info("No se pudieron calcular las fuentes de poder.")
                
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

if __name__ == "__main__":
    main()
