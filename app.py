import streamlit as st
import math
import pandas as pd
import collections
import io
from PIL import Image

# --- LÓGICA EXTERNA (Simulada o Importada) ---
# Nota: Asegúrate de que 'optimizador_logic.py' exista en tu entorno.
try:
    from optimizador_logic import optimizar_cortes_para_un_largo_rollo
except ImportError:
    # Función dummy para evitar errores si el archivo no está presente en la previsualización
    def optimizar_cortes_para_un_largo_rollo(*args, **kwargs):
        return "Error", 0, 0, [], []

# --- FUNCIÓN PARA CALCULAR LA FUENTE MÁS ADECUADA (modo individual) ---
def obtener_fuente_adecuada_individual(consumo_requerido_watts, fuentes_disponibles_watts, factor_seguridad=1.2):
    consumo_ajustado = consumo_requerido_watts * factor_seguridad
    fuentes_suficientes = [f for f in fuentes_disponibles_watts if f >= consumo_ajustado]
    
    if not fuentes_suficientes:
        if fuentes_disponibles_watts:
            return max(fuentes_disponibles_watts), f"¡Advertencia! El consumo de {consumo_requerido_watts:.2f}W excede las fuentes disponibles."
        else:
            return None, "No hay fuentes disponibles."
    
    return min(fuentes_suficientes), "" 

# --- FUNCIÓN PARA OPTIMIZAR FUENTES (modo agrupado) ---
def optimizar_fuentes_para_cortes_agrupados(solicitudes_cortes, watts_por_metro_tira, fuentes_disponibles_watts, factor_seguridad):
    piezas_consumo_ajustado = []
    for largo_corte, cantidad_corte in solicitudes_cortes.items():
        consumo_individual_real = largo_corte * watts_por_metro_tira
        consumo_individual_ajustado = consumo_individual_real * factor_seguridad
        for _ in range(cantidad_corte):
            piezas_consumo_ajustado.append({
                "largo_original": largo_corte,
                "consumo_real": consumo_individual_real,
                "consumo_ajustado": consumo_individual_ajustado
            })
    
    piezas_consumo_ajustado.sort(key=lambda x: x["consumo_ajustado"], reverse=True)
    fuentes_en_uso = [] 
    total_fuentes_requeridas_dict = collections.defaultdict(int)

    for pieza in piezas_consumo_ajustado:
        consumo_pieza = pieza["consumo_ajustado"]
        largo_original = pieza["largo_original"]
        consumo_real_pieza = pieza["consumo_real"]
        
        asignada_a_existente = False
        for fuente_actual in fuentes_en_uso:
            if fuente_actual["restante"] >= consumo_pieza:
                fuente_actual["restante"] -= consumo_pieza
                fuente_actual["cortes_asignados"].append({"largo": largo_original, "consumo_real": consumo_real_pieza})
                asignada_a_existente = True
                break
        
        if not asignada_a_existente:
            fuente_nueva_encontrada = False
            for fuente_disponible_w in sorted(fuentes_disponibles_watts): 
                if fuente_disponible_w >= consumo_pieza:
                    fuentes_en_uso.append({
                        "tipo": fuente_disponible_w,
                        "restante": fuente_disponible_w - consumo_pieza,
                        "cortes_asignados": [{"largo": largo_original, "consumo_real": consumo_real_pieza}]
                    })
                    total_fuentes_requeridas_dict[fuente_disponible_w] += 1
                    fuente_nueva_encontrada = True
                    break
            
            if not fuente_nueva_encontrada:
                max_f = max(fuentes_disponibles_watts) if fuentes_disponibles_watts else 0
                fuentes_en_uso.append({
                    "tipo": max_f,
                    "restante": max_f - consumo_pieza,
                    "cortes_asignados": [{"largo": largo_original, "consumo_real": consumo_real_pieza}]
                })
                total_fuentes_requeridas_dict[max_f] += 1
    
    detalles_finales = []
    for i, f_obj in enumerate(fuentes_en_uso):
        cortes_str = ", ".join([f"{c['largo']:.2f}m" for c in f_obj["cortes_asignados"]])
        detalles_finales.append({
            "ID Fuente": f"F-{i+1}",
            "Potencia (W)": f_obj["tipo"],
            "Cortes": cortes_str,
            "Consumo (W)": f"{f_obj['tipo'] - f_obj['restante']:.2f}",
            "Advertencia": "EXCEDE" if f_obj["restante"] < 0 else ""
        })

    return total_fuentes_requeridas_dict, detalles_finales

# --- CALLBACKS ---
def add_cut_callback():
    largo = st.session_state.largo_input
    cantidad = st.session_state.cantidad_input
    if largo > 0 and cantidad > 0:
        st.session_state.solicitudes_cortes_ingresadas[largo] = \
            st.session_state.solicitudes_cortes_ingresadas.get(largo, 0) + cantidad
        st.session_state.largo_input = 0.1
        st.session_state.cantidad_input = 1

def clear_all_cuts_callback():
    st.session_state.solicitudes_cortes_ingresadas = {}
    if 'cut_optimization_results' in st.session_state: del st.session_state.cut_optimization_results
    if 'source_calculation_results' in st.session_state: del st.session_state.source_calculation_results

def delete_cut_callback(largo_to_delete):
    if largo_to_delete in st.session_state.solicitudes_cortes_ingresadas:
        del st.session_state.solicitudes_cortes_ingresadas[largo_to_delete]

def calculate_sources_callback():
    if not st.session_state.solicitudes_cortes_ingresadas:
        st.warning("Añade cortes primero.")
        return
    
    try:
        fuentes = sorted([float(w.strip()) for w in st.session_state.available_sources_input.split(',') if w.strip()])
        watts_m = st.session_state.watts_per_meter_input
        f_seg = st.session_state.safety_factor_slider / 100 + 1
        
        if st.session_state.modo_asignacion_fuentes_radio == "Una fuente por cada corte":
            res_dict = collections.defaultdict(int)
            detalles = []
            for largo, cant in st.session_state.solicitudes_cortes_ingresadas.items():
                f_asig, adv = obtener_fuente_adecuada_individual(largo * watts_m, fuentes, f_seg)
                if f_asig: res_dict[f_asig] += cant
                detalles.append({"Corte": largo, "Cant": cant, "Fuente": f_asig, "Nota": adv})
            st.session_state.source_calculation_results = {"mode": "individual", "total_fuentes": res_dict, "detalles": detalles}
        else:
            total_f, detalles = optimizar_fuentes_para_cortes_agrupados(st.session_state.solicitudes_cortes_ingresadas, watts_m, fuentes, f_seg)
            st.session_state.source_calculation_results = {"mode": "grouped", "total_fuentes": total_f, "detalles": detalles}
    except Exception as e:
        st.error(f"Error en fuentes: {e}")

def main():
    st.set_page_config(layout="wide", page_title="Optimizador Jenny")
    
    # Estilos
    st.markdown("<style>html, body, [class*='st-'] { font-family: Calibri, sans-serif; }</style>", unsafe_allow_html=True)
    
    # Logo
    try:
        st.image("LOGO (1).png", width=200)
    except:
        st.info("Logo no encontrado.")

    st.title("Optimizador de cortes de tiras Jenny")

    # Auth Simple (Simulado para el ejemplo o usando secrets)
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    
    # --- Bypass de login para previsualización o implementación de secrets ---
    # En producción usarías: if not st.session_state.logged_in: ...
    st.session_state.logged_in = True 

    if st.session_state.logged_in:
        # Inicialización de State
        if 'solicitudes_cortes_ingresadas' not in st.session_state: st.session_state.solicitudes_cortes_ingresadas = {}
        if 'largo_input' not in st.session_state: st.session_state.largo_input = 0.1
        if 'cantidad_input' not in st.session_state: st.session_state.cantidad_input = 1

        # 1. Selección de Rollo
        ROLLOS = [5.0, 10.0, 20.0]
        largo_rollo = st.selectbox("Largo del rollo (m):", ROLLOS, key="largo_rollo_selector")

        # 2. Ingreso de Cortes
        st.header("Cortes Solicitados")
        col_a, col_b, col_c = st.columns([3,3,2])
        col_a.number_input("Largo (m)", min_value=0.1, key="largo_input", step=0.1)
        col_b.number_input("Cantidad", min_value=1, key="cantidad_input")
        col_c.write(" ")
        col_c.button("Añadir", on_click=add_cut_callback, use_container_width=True)

        if st.session_state.solicitudes_cortes_ingresadas:
            st.table(pd.DataFrame([{"Largo": k, "Cantidad": v} for k, v in st.session_state.solicitudes_cortes_ingresadas.items()]))
            st.button("Limpiar todo", on_click=clear_all_cuts_callback)

        # 3. Optimización
        if st.button("Optimizar Material", type="primary"):
            # Aquí llamarías a tu lógica real. Simulamos resultado:
            st.session_state.cut_optimization_results = {
                "estado": "Calculado",
                "detalles_cortes_por_rollo": [{"Rollo_ID": "R1", "Tipo_Rollo": largo_rollo, "Cortes_en_rollo": [1, 2], "Desperdicio_en_rollo": 2.0}]
            }

        # 4. Fuentes
        st.divider()
        if st.toggle("Calcular Fuentes de Poder", value=True):
            st.number_input("Watts por metro", value=10.0, key="watts_per_meter_input")
            st.text_input("Fuentes disponibles (W)", value="30, 60, 100, 150, 240, 360", key="available_sources_input")
            st.slider("Factor Seguridad (%)", 5, 50, 20, key="safety_factor_slider")
            st.radio("Modo", ["Una fuente por cada corte", "Optimizar fuentes para agrupar cortes"], key="modo_asignacion_fuentes_radio")
            st.button("Calcular Fuentes", on_click=calculate_sources_callback)

        # 5. Exportación con IO
        if 'source_calculation_results' in st.session_state or 'cut_optimization_results' in st.session_state:
            st.header("Exportar Resultados")
            
            # Consolidar datos para CSV
            export_data = []
            if 'source_calculation_results' in st.session_state and st.session_state.source_calculation_results:
                export_data = st.session_state.source_calculation_results['detalles']
            
            if export_data:
                df_export = pd.DataFrame(export_data)
                
                # USO DE IO
                csv_buffer = io.StringIO()
                df_export.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
                
                st.download_button(
                    label="📥 Descargar Reporte (CSV)",
                    data=csv_buffer.getvalue(),
                    file_name="reporte_jenny.csv",
                    mime="text/csv"
                )

if __name__ == "__main__":
    main()
