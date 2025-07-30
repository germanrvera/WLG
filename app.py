import streamlit as st
from optimizador_logic import optimizar_cortes_para_un_largo_rollo
import math
import pandas as pd
import collections
from PIL import Image # Necesario para cargar la imagen

# --- FUNCIÓN PARA CALCULAR LA FUENTE MÁS ADECUADA (para modo individual) ---
def obtener_fuente_adecuada_individual(consumo_requerido_watts, fuentes_disponibles_watts, factor_seguridad=1.2):
    """
    Calcula la fuente de poder más pequeña que soporta el consumo requerido
    aplicando un factor de seguridad (modo individual).
    """
    consumo_ajustado = consumo_requerido_watts * factor_seguridad
    
    fuentes_suficientes = [f for f in fuentes_disponibles_watts if f >= consumo_ajustado]
    
    if not fuentes_suficientes:
        if fuentes_disponibles_watts:
            return max(fuentes_disponibles_watts), f"¡Advertencia! El consumo de {consumo_requerido_watts:.2f}W (ajustado a {consumo_ajustado:.2f}W) excede todas las fuentes disponibles. Se asigna la fuente más grande disponible ({max(fuentes_disponibles_watts):.0f}W)."
        else:
            return None, "No hay fuentes disponibles para asignar."
    
    return min(fuentes_suficientes), "" 

# --- NUEVA FUNCIÓN PARA OPTIMIZAR FUENTES (modo agrupado - First Fit Decreasing) ---
def optimizar_fuentes_para_cortes_agrupados(solicitudes_cortes, watts_por_metro_tira, fuentes_disponibles_watts, factor_seguridad):
    """
    Optimiza la asignación de fuentes de poder para agrupar cortes, minimizando el número total de fuentes.
    Utiliza un algoritmo First Fit Decreasing (FFD).
    
    Returns:
        tuple: (total_fuentes_requeridas_dict, detalles_fuentes_asignadas_list)
               - total_fuentes_requeridas_dict (defaultdict): Conteo de cada tipo de fuente usada.
               - detalles_fuentes_asignadas_list (list): Detalles de cada pieza y la fuente asignada.
    """
    
    # 1. Calcular el consumo ajustado para cada pieza individualmente y almacenar su largo original
    piezas_consumo_ajustado = []
    for largo_corte, cantidad_corte in solicitudes_cortes.items():
        consumo_individual_real = largo_corte * watts_por_metro_tira
        consumo_individual_ajustado = consumo_individual_real * factor_seguridad
        for _ in range(cantidad_corte): # Cada pieza individual se considera para la asignación
            piezas_consumo_ajustado.append({
                "largo_original": largo_corte,
                "consumo_real": consumo_individual_real,
                "consumo_ajustado": consumo_individual_ajustado
            })
    
    # Ordenar las piezas por consumo ajustado de mayor a menor (FFD)
    piezas_consumo_ajustado.sort(key=lambda x: x["consumo_ajustado"], reverse=True)

    # 2. Inicializar las "bandejas" (fuentes) en uso
    # Cada fuente_en_uso es un diccionario: {"tipo": potencia_W, "restante": capacidad_restante, "cortes_asignados": []}
    fuentes_en_uso = [] 
    
    # Para el resumen final de fuentes
    total_fuentes_requeridas_dict = collections.defaultdict(int)
    detalles_fuentes_asignadas_list = [] # Para la tabla de resultados detallados

    # 3. Asignar cada pieza a una fuente
    for pieza in piezas_consumo_ajustado:
        consumo_pieza = pieza["consumo_ajustado"]
        largo_original = pieza["largo_original"]
        consumo_real_pieza = pieza["consumo_real"]
        
        asignada_a_existente = False
        # Intentar asignar a una fuente existente que tenga suficiente capacidad
        for fuente_actual in fuentes_en_uso:
            if fuente_actual["restante"] >= consumo_pieza:
                fuente_actual["restante"] -= consumo_pieza
                fuente_actual["cortes_asignados"].append({"largo": largo_original, "consumo_real": consumo_real_pieza})
                asignada_a_existente = True
                break
        
        if not asignada_a_existente:
            # Si no se pudo asignar a una fuente existente, buscar una nueva fuente adecuada
            fuente_nueva_encontrada = False
            # Iterar por las fuentes disponibles en orden ascendente (First Fit)
            for fuente_disponible_w in sorted(fuentes_disponibles_watts): 
                if fuente_disponible_w >= consumo_pieza:
                    fuentes_en_uso.append({
                        "tipo": fuente_disponible_w,
                        "restante": fuente_disponible_w - consumo_pieza,
                        "cortes_asignados": [{"largo": largo_original, "consumo_real": consumo_real_pieza}]
                    })
                    total_fuentes_requeridas_dict[fuente_disponible_w] += 1 # Contar esta nueva fuente
                    fuente_nueva_encontrada = True
                    break
            
            if not fuente_nueva_encontrada:
                # Si la pieza es demasiado grande para CUALQUIER fuente disponible
                max_fuente_disponible = max(fuentes_disponibles_watts) if fuentes_disponibles_watts else None
                if max_fuente_disponible:
                    # Asignar la fuente más grande disponible y marcar con advertencia
                    fuentes_en_uso.append({
                        "tipo": max_fuente_disponible,
                        "restante": max_fuente_disponible - consumo_pieza, # Puede ser negativo si excede
                        "cortes_asignados": [{"largo": largo_original, "consumo_real": consumo_real_pieza}]
                    })
                    total_fuentes_requeridas_dict[max_fuente_disponible] += 1
                    detalles_fuentes_asignadas_list.append({
                        "Largo Corte (m)": largo_original,
                        "Consumo Real (W)": f"{consumo_real_pieza:.2f}",
                        "Consumo Ajustado (W)": f"{consumo_pieza:.2f}",
                        "Fuente Asignada (W)": f"{max_fuente_disponible:.0f}",
                        "Tipo Asignación": "Excede todas las fuentes",
                        "Advertencia": f"¡Advertencia! Consumo de {consumo_real_pieza:.2f}W (ajustado a {consumo_pieza:.2f}W) excede todas las fuentes. Se asigna la más grande ({max_fuente_disponible:.0f}W)."
                    })
                else:
                    detalles_fuentes_asignadas_list.append({
                        "Largo Corte (m)": largo_original,
                        "Consumo Real (W)": f"{consumo_real_pieza:.2f}",
                        "Consumo Ajustado (W)": f"{consumo_pieza:.2f}",
                        "Fuente Asignada (W)": "N/A",
                        "Tipo Asignación": "No Asignada",
                        "Advertencia": "No hay fuentes disponibles para asignar."
                    })
    
    # 4. Formatear los detalles para la tabla de resultados
    # Para el modo agrupado, la tabla mostrará qué cortes fueron asignados a qué fuente INSTANCIA
    # Esto puede ser muy verboso. Una opción es mostrar un resumen por fuente.
    # Por ahora, vamos a mostrar un resumen por CADA fuente física utilizada.
    
    detalles_finales_agrupados = []
    fuente_id_counter = 1
    for fuente_obj in fuentes_en_uso:
        cortes_str_list = [f"{c['largo']:.2f}m ({c['consumo_real']:.2f}W)" for c in fuente_obj["cortes_asignados"]]
        # CORRECCIÓN AQUÍ: Cambiado "type" a "tipo"
        total_consumo_fuente = fuente_obj["tipo"] - fuente_obj["restante"] # Consumo total real en esta fuente
        
        detalles_finales_agrupados.append({
            "ID Fuente": f"F-{fuente_id_counter}",
            "Potencia Fuente (W)": fuente_obj["tipo"],
            "Cortes Asignados": ", ".join(cortes_str_list),
            "Consumo Total en Fuente (W)": f"{total_consumo_fuente:.2f}",
            "Capacidad Restante (W)": f"{fuente_obj['restante']:.2f}",
            "Advertencia": "Consumo excede capacidad" if fuente_obj["restante"] < 0 else ""
        })
        fuente_id_counter += 1

    return total_fuentes_requeridas_dict, detalles_finales_agrupados


# --- Funciones de Callback para los botones de la UI ---
def add_cut_callback():
    largo = st.session_state.largo_input
    cantidad = st.session_state.cantidad_input

    if largo > 0 and cantidad > 0:
        st.session_state.solicitudes_cortes_ingresadas[largo] = \
            st.session_state.solicitudes_cortes_ingresadas.get(largo, 0) + cantidad
        st.success(f"Se añadió {cantidad} cortes de {largo}m.")
        
        st.session_state.current_largo_input_value = 0.1 
        st.session_state.current_cantidad_input_value = 1
    else:
        st.error("Por favor, ingresa valores positivos para largo y cantidad.")

def clear_all_cuts_callback():
    st.session_state.solicitudes_cortes_ingresadas = {}
    st.session_state.current_largo_input_value = 0.1
    st.session_state.current_cantidad_input_value = 1

def delete_cut_callback(largo_to_delete):
    if largo_to_delete in st.session_state.solicitudes_cortes_ingresadas:
        del st.session_state.solicitudes_cortes_ingresadas[largo_to_delete]

def main():
    st.set_page_config(layout="wide") 
    
    try:
        imagen = Image.open("LOGO (1).png") 
        st.image(imagen, width=200) 
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
    
    if 'current_largo_input_value' not in st.session_state:
        st.session_state.current_largo_input_value = 0.1
    if 'current_cantidad_input_value' not in st.session_state:
        st.session_state.current_cantidad_input_value = 1

    col1, col2, col3 = st.columns([0.4, 0.4, 0.2])
    with col1:
        largo_input = st.number_input(
            "Largo del Corte (metros)", 
            min_value=0.01, 
            value=st.session_state.current_largo_input_value, 
            step=0.1, 
            key="largo_input"
        )
    with col2:
        cantidad_input = st.number_input(
            "Cantidad Solicitada", 
            min_value=1, 
            value=st.session_state.current_cantidad_input_value, 
            step=1, 
            key="cantidad_input"
        )
    with col3:
        st.write("") 
        st.write("")
        st.button("➕ Añadir Corte", key="add_button", on_click=add_cut_callback)
    
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
                st.button("🗑️ Eliminar", key=f"delete_cut_{largo}_{i}", on_click=delete_cut_callback, args=(largo,))
        
        st.markdown("---") 
        st.button("🗑️ Limpiar Todos los Cortes", key="clear_all_button", on_click=clear_all_cuts_callback)
    else:
        st.info("Aún no has añadido ningún corte.")

    # --- SECCIÓN PARA LA CONFIGURACIÓN DE FUENTES DE PODER ---
    st.header("3. Configuración de Fuentes LED") 
    st.markdown("Ingresa el consumo de la tira LED y las potencias de las fuentes disponibles.")

    watts_por_metro_tira = st.number_input(
        "Consumo de la Tira LED (Watts por metro - W/m)",
        min_value=1.0, value=10.0, step=0.5,
        help="Ej. 10 W/m, 14.4 W/m, 20 W/m",
        key="watts_per_meter_input" 
    )

    st.markdown("Ingresa las potencias de las fuentes disponibles (en Watts), separadas por comas. Ej: `30, 36, 40, 60, 100, 120, 150, 240, 320, 360`")
    fuentes_disponibles_str = st.text_input(
        "Potencias de Fuentes de Poder Disponibles (Watts)", 
        value="30, 36, 40, 60, 100, 120, 150, 240, 320, 360", 
        help="Las fuentes se eligen con un 20% de factor de seguridad por encima del consumo real."
        ,key="available_sources_input" 
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
        ,key="safety_factor_slider" 
    ) / 100 + 1

    # --- NUEVA OPCIÓN PARA MODO DE ASIGNACIÓN DE FUENTES ---
    st.subheader("Modo de Asignación de Fuentes")
    modo_asignacion_fuentes = st.radio(
        "¿Cómo deseas asignar las fuentes de poder?",
        ("Una fuente por cada corte", "Optimizar fuentes para agrupar cortes"),
        key="modo_asignacion_fuentes_radio"
    )

    # --- SLIDER PARA CONTROLAR EL LÍMITE DE PATRONES ---
    st.header("4. Opciones Avanzadas de Optimización") 
    max_items_per_pattern = st.slider(
        "Máximo de piezas por patrón de corte (para rendimiento)",
        min_value=3, 
        max_value=20, 
        value=8,      
        step=1,
        help="Controla la complejidad de los patrones de corte. Un número más bajo (ej. 3-8) es mucho más rápido y estable para muchos cortes, pero podría ser ligeramente menos óptimo. Un número más alto (ej. 10-20) es más lento pero puede encontrar soluciones con menos desperdicio. Si la aplicación se cuelga, reduce este valor."
        ,key="max_pattern_items_slider" 
    )

    st.header("5. Ejecutar Optimización y Cálculo de Fuentes") 
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
                    
                # --- CÁLCULO Y ASIGNACIÓN DE FUENTES (Lógica condicional según el modo) ---
                st.subheader("--- Cálculo de Fuentes de Poder ---")
                
                if modo_asignacion_fuentes == "Una fuente por cada corte":
                    st.markdown("Se asigna una fuente de poder por cada corte solicitado.")
                    total_fuentes_requeridas_individual = collections.defaultdict(int)
                    detalles_fuentes_individual = []
                    
                    for largo_corte, cantidad_corte in st.session_state.solicitudes_cortes_ingresadas.items():
                        consumo_corte = largo_corte * watts_por_metro_tira
                        
                        fuente_asignada, advertencia_fuente = obtener_fuente_adecuada_individual(
                            consumo_corte, fuentes_disponibles_watts, factor_seguridad_fuentes
                        )
                        
                        if fuente_asignada:
                            total_fuentes_requeridas_individual[fuente_asignada] += cantidad_corte 
                            detalles_fuentes_individual.append({
                                "Largo Corte (m)": largo_corte,
                                "Cantidad de Cortes": cantidad_corte,
                                "Consumo Total p/Corte (W)": f"{consumo_corte:.2f}",
                                "Consumo Ajustado (W)": f"{consumo_corte * factor_seguridad_fuentes:.2f}",
                                "Fuente Asignada (W)": f"{fuente_asignada:.0f}",
                                "Advertencia": advertencia_fuente
                            })
                        else:
                            detalles_fuentes_individual.append({
                                "Largo Corte (m)": largo_corte,
                                "Cantidad de Cortes": cantidad_corte,
                                "Consumo Total p/Corte (W)": f"{consumo_corte:.2f}",
                                "Consumo Ajustado (W)": f"{consumo_corte * factor_seguridad_fuentes:.2f}",
                                "Fuente Asignada (W)": "N/A",
                                "Advertencia": advertencia_fuente if advertencia_fuente else "No se pudo asignar fuente."
                            })

                    if detalles_fuentes_individual:
                        st.dataframe(pd.DataFrame(detalles_fuentes_individual), use_container_width=True)
                        st.subheader("Resumen de Fuentes de Poder Necesarias (Individual):")
                        for fuente_w, cantidad in sorted(total_fuentes_requeridas_individual.items()):
                            st.write(f"- Fuentes de **{fuente_w:.0f}W**: **{cantidad} unidades**")
                    else:
                        st.info("No se pudieron calcular las fuentes de poder en modo individual.")

                elif modo_asignacion_fuentes == "Optimizar fuentes para agrupar cortes":
                    st.markdown("Se optimiza la asignación de fuentes para agrupar varios cortes en una misma fuente, minimizando el número total de fuentes.")
                    
                    total_fuentes_agrupadas, detalles_agrupados_por_fuente = \
                        optimizar_fuentes_para_cortes_agrupados(
                            st.session_state.solicitudes_cortes_ingresadas, 
                            watts_por_metro_tira, 
                            fuentes_disponibles_watts, 
                            factor_seguridad_fuentes
                        )
                    
                    if detalles_agrupados_por_fuente:
                        st.dataframe(pd.DataFrame(detalles_agrupados_por_fuente), use_container_width=True)
                        st.subheader("Resumen de Fuentes de Poder Necesarias (Agrupado):")
                        for fuente_w, cantidad in sorted(total_fuentes_agrupadas.items()):
                            st.write(f"- Fuentes de **{fuente_w:.0f}W**: **{cantidad} unidades**")
                    else:
                        st.info("No se pudieron calcular las fuentes de poder en modo agrupado.")
                
                st.markdown("---") # Separador visual entre secciones

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

