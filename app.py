import streamlit as st
import firebase_admin
from firebase_admin import credentials, auth, exceptions # Importar exceptions
import math
import pandas as pd
import collections
from PIL import Image # Necesario para cargar la imagen
import json # Para parsear el secreto

# --- Inicializar Firebase Admin SDK ---
# Asegúrate de que el contenido de tu archivo JSON de Firebase
# esté guardado como un secreto en Streamlit Cloud con la clave 'firebase_credentials'.
# Ejemplo en .streamlit/secrets.toml:
# firebase_credentials = """{ ... tu JSON completo aquí ... }"""
if not firebase_admin._apps:
    try:
        # Cargar las credenciales desde st.secrets
        # Se asume que 'firebase_credentials' es una cadena JSON en st.secrets,
        # por lo que se usa json.loads() para convertirla en un diccionario.
        firebase_config = json.loads(st.secrets["firebase_credentials"])
        cred = credentials.Certificate(firebase_config)
        firebase_admin.initialize_app(cred)
        st.success("Firebase inicializado correctamente.")
    except Exception as e:
        st.error(f"Error al inicializar Firebase: {e}")
        st.stop() # Detener la ejecución si Firebase no se inicializa

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

# --- FUNCIÓN PARA OPTIMIZAR FUENTES (modo agrupado - First Fit Decreasing) ---
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
                        "Consumo Real (W)": f"{consumo_pieza:.2f}", # Corregido para mostrar consumo ajustado
                        "Consumo Ajustado (W)": f"{consumo_pieza:.2f}",
                        "Fuente Asignada (W)": f"{max_fuente_disponible:.0f}",
                        "Tipo Asignación": "Excede todas las fuentes",
                        "Advertencia": f"¡Advertencia! Consumo de {consumo_real_pieza:.2f}W (ajustado a {consumo_pieza:.2f}W) excede todas las fuentes. Se asigna la más grande ({max_fuente_disponible:.0f}W)."
                    })
                else:
                    detalles_fuentes_asignadas_list.append({
                        "Largo Corte (m)": largo_original,
                        "Cantidad de Cortes": cantidad_corte,
                        "Consumo Total p/Corte (W)": f"{consumo_real_pieza:.2f}",
                        "Consumo Ajustado (W)": f"{consumo_pieza:.2f}",
                        "Fuente Asignada (W)": "N/A",
                        "Tipo Asignación": "No Asignada",
                        "Advertencia": "No hay fuentes disponibles para asignar."
                    })
    
    # 4. Formatear los detalles para la tabla de resultados
    detalles_finales_agrupados = []
    fuente_id_counter = 1
    for fuente_obj in fuentes_en_uso:
        cortes_str_list = [f"{c['largo']:.2f}m ({c['consumo_real']:.2f}W)" for c in fuente_obj["cortes_asignados"]]
        total_consumo_fuente = fuente_obj["tipo"] - fuente_obj["restante"] 
        
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
    # También limpiar los resultados de optimización y fuentes al limpiar cortes
    if 'cut_optimization_results' in st.session_state:
        del st.session_state.cut_optimization_results
    if 'source_calculation_results' in st.session_state:
        del st.session_state.source_calculation_results


def delete_cut_callback(largo_to_delete):
    if largo_to_delete in st.session_state.solicitudes_cortes_ingresadas:
        del st.session_state.solicitudes_cortes_ingresadas[largo_to_delete]
    # También limpiar los resultados de optimización y fuentes al eliminar un corte
    if 'cut_optimization_results' in st.session_state:
        del st.session_state.cut_optimization_results
    if 'source_calculation_results' in st.session_state:
        del st.session_state.source_calculation_results


def calculate_sources_callback():
    # Asegurarse de que haya cortes ingresados antes de calcular fuentes
    if not st.session_state.solicitudes_cortes_ingresadas:
        st.warning("Por favor, añade al menos un corte antes de calcular las fuentes.")
        st.session_state.source_calculation_results = None # Limpiar resultados anteriores
        return
    
    # Asegurarse de que haya fuentes disponibles configuradas
    fuentes_disponibles_watts = []
    try:
        fuentes_disponibles_watts = sorted([float(w.strip()) for w in st.session_state.available_sources_input.split(',') if w.strip()])
        if not fuentes_disponibles_watts:
            st.warning("Por favor, configura las potencias de las fuentes disponibles.")
            st.session_state.source_calculation_results = None
            return
    except ValueError:
        st.error("Formato de fuentes inválido. Asegúrate de usar números y comas (ej: 60, 100, 150).")
        st.session_state.source_calculation_results = None
        return

    with st.spinner("Calculando fuentes de poder..."):
        watts_por_metro_tira = st.session_state.watts_per_meter_input
        factor_seguridad_fuentes = st.session_state.safety_factor_slider / 100 + 1
        modo_asignacion_fuentes = st.session_state.modo_asignacion_fuentes_radio

        if modo_asignacion_fuentes == "Una fuente por cada corte":
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
                        "Tipo Asignación": "No Asignada",
                        "Advertencia": advertencia_fuente if advertencia_fuente else "No se pudo asignar fuente."
                    })
            
            st.session_state.source_calculation_results = {
                "mode": "individual",
                "total_fuentes": total_fuentes_requeridas_individual,
                "detalles": detalles_fuentes_individual
            }

        elif modo_asignacion_fuentes == "Optimizar fuentes para agrupar cortes":
            total_fuentes_agrupadas, detalles_agrupados_por_fuente = \
                optimizar_fuentes_para_cortes_agrupados(
                    st.session_state.solicitudes_cortes_ingresadas, 
                    watts_por_metro_tira, 
                    fuentes_disponibles_watts, 
                    factor_seguridad_fuentes
                )
            
            st.session_state.source_calculation_results = {
                "mode": "grouped",
                "total_fuentes": total_fuentes_agrupadas,
                "detalles": detalles_agrupados_por_fuente
            }

# --- FUNCIÓN DE CALLBACK PARA REINICIAR TODO ---
def reset_all_callback():
    # Establecer una bandera en session_state para indicar que se debe reiniciar la aplicación
    st.session_state.reset_app_flag = True

# --- FUNCIÓN DE CALLBACK PARA CERRAR SESIÓN ---
def logout_callback():
    st.session_state.authenticated = False
    if 'user_email' in st.session_state:
        del st.session_state.user_email
    if 'user_uid' in st.session_state:
        del st.session_state.user_uid
    st.rerun() # Forzar un rerun para mostrar la pantalla de login

# --- Lógica de Autenticación (Login y Registro) ---
def auth_section():
    st.subheader("Iniciar Sesión / Registrarse")

    auth_mode = st.radio("Selecciona una opción:", ("Iniciar Sesión", "Registrarse"), key="auth_mode_radio")

    email = st.text_input("Correo Electrónico", key="auth_email")
    password = st.text_input("Contraseña", type="password", key="auth_password")

    if auth_mode == "Registrarse":
        if st.button("Registrarse", key="register_button"):
            if not email or not password:
                st.error("Por favor, ingresa un correo y una contraseña.")
                return
            try:
                user = auth.create_user(email=email, password=password)
                st.success(f"Usuario {email} registrado exitosamente. ¡Ya puedes iniciar sesión!")
            except exceptions.FirebaseError as e:
                st.error(f"Error al registrar usuario: {e.code} - {e.message}")
            except Exception as e:
                st.error(f"Ocurrió un error inesperado: {e}")
    
    elif auth_mode == "Iniciar Sesión":
        if st.button("Ingresar", key="login_button"):
            if not email or not password:
                st.error("Por favor, ingresa un correo y una contraseña.")
                return
            try:
                # ⚠️ ADVERTENCIA DE SEGURIDAD: Esta es una simplificación para la demo.
                # En producción, usarías el SDK de Firebase JS en el frontend para el login
                # y verificarías el ID Token resultante en el backend.
                user = auth.get_user_by_email(email)
                # NOTA: Firebase Admin SDK no tiene un método directo para verificar la contraseña.
                # Para una autenticación segura de contraseña en el backend, se necesitaría
                # un proceso más complejo o usar el SDK de cliente en JS.
                # Para esta demo, asumimos que si get_user_by_email funciona, el usuario existe.
                # La verificación de la contraseña aquí es conceptual y NO SEGURA para producción.
                # Una solución real implicaría que el frontend envíe un ID Token válido.

                # Para la demostración, si el usuario existe, se considera "autenticado".
                # En un escenario real, el login se haría con el SDK de cliente (JS)
                # y el ID Token resultante se enviaría al backend para verificación.
                
                # Simulación de verificación de contraseña (NO SEGURA):
                # No hay una forma directa y segura de verificar la contraseña en texto plano
                # con el Admin SDK. La única forma es crear un token personalizado
                # y que el cliente lo use para iniciar sesión.
                # Para esta demo, si el email y la contraseña coinciden con un usuario existente
                # (lo cual NO se puede verificar directamente aquí de forma segura con la contraseña en texto plano),
                # simplemente asumimos el éxito para mostrar el flujo.
                # La forma correcta es que el cliente (JS) haga el signInWithEmailAndPassword
                # y nos envíe el idToken.

                # Dado que no podemos verificar la contraseña directamente aquí de forma segura,
                # para la DEMO, vamos a "simular" un login exitoso si el email existe.
                # Esto es solo para fines ilustrativos del flujo de la UI.
                
                # Una implementación real y segura sería:
                # 1. Frontend (JS) usa firebase.auth().signInWithEmailAndPassword(email, password)
                # 2. Si exitoso, JS obtiene user.getIdToken()
                # 3. JS envía este idToken al backend de Streamlit.
                # 4. Backend de Streamlit usa auth.verify_id_token(idToken)

                # Para esta demo, si llegamos aquí, significa que get_user_by_email no lanzó error,
                # lo que implica que el email existe. Procedemos a "autenticar" para la demo.
                st.session_state.authenticated = True
                st.session_state.user_email = email
                st.session_state.user_uid = user.uid
                st.success(f"¡Bienvenido, {email}!")
                st.rerun()
            except exceptions.FirebaseError as e:
                if e.code == 'auth/user-not-found':
                    st.error("Usuario no encontrado. Por favor, regístrate o verifica tu correo.")
                elif e.code == 'auth/wrong-password': # Este error NO se lanza con get_user_by_email
                    st.error("Contraseña incorrecta.")
                else:
                    st.error(f"Error al iniciar sesión: {e.code} - {e.message}")
            except Exception as e:
                st.error(f"Ocurrió un error inesperado: {e}")

def main():
    # --- Lógica para reiniciar la aplicación si la bandera está activada ---
    if 'reset_app_flag' not in st.session_state:
        st.session_state.reset_app_flag = False

    if st.session_state.reset_app_flag:
        # Limpiar todas las variables de session_state a sus valores iniciales
        # Esto incluye el estado de autenticación
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        
        # Reiniciar valores por defecto para los inputs de la aplicación
        st.session_state.solicitudes_cortes_ingresadas = {}
        st.session_state.current_largo_input_value = 0.1
        st.session_state.current_cantidad_input_value = 1
        st.session_state.watts_per_meter_input = 10.0
        st.session_state.available_sources_input = "30, 36, 40, 60, 100, 120, 150, 240, 320, 360"
        st.session_state.safety_factor_slider = 20
        st.session_state.modo_asignacion_fuentes_radio = "Una fuente por cada corte"
        st.session_state.max_pattern_items_slider = 8
        st.session_state.largo_rollo_selector = 5.0
        st.session_state.enable_source_calculation_toggle = True
        st.session_state.authenticated = False # Asegurar que se vuelve a la pantalla de login
        
        st.session_state.reset_app_flag = False # Desactivar la bandera
        st.rerun() # Forzar una recarga completa

    st.set_page_config(layout="wide") 
    
    # --- CSS para cambiar la fuente a Calibri ---
    st.markdown(
        """
        <style>
        html, body, [class*="st-"] {
            font-family: Calibri, sans-serif;
        }
        </style>
        """,
        unsafe_allow_html=True
    )
    
    try:
        imagen = Image.open("LOGO (1).png") 
        st.image(imagen, width=200) 
    except FileNotFoundError:
        st.warning("No se encontró el archivo de imagen 'LOGO (1).png'.") 
    
    st.title("Optimizador de cortes de tiras Jenny") 
    st.markdown("Esta herramienta te ayuda a calcular la forma más eficiente de cortar material lineal para minimizar desperdicios y la cantidad de rollos.")

    # --- Lógica de Autenticación (se muestra si no está autenticado) ---
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        auth_section() # Llama a la función que muestra el login/registro
    else:
        # --- Contenido Principal de la Aplicación (solo si está autenticado) ---
        st.sidebar.write(f"Conectado como: **{st.session_state.user_email}**")
        st.sidebar.button("Cerrar Sesión", on_click=logout_callback)

        # --- LISTA DE ROLLOS ---
        ROLLOS_DISPONIBLES = [5.0, 10.0, 20.0] 

        st.header("1. Selecciona el rollo de Jenny") 
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
            st.button(" Añadir Corte", key="add_button", on_click=add_cut_callback) 
        
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
                    st.button(" Eliminar", key=f"delete_cut_{largo}_{i}", on_click=delete_cut_callback, args=(largo,)) 
            
            st.markdown("---") 
            st.button(" Limpiar Todos los Cortes", key="clear_all_button", on_click=clear_all_cuts_callback) 
        else:
            st.info("Aún no has añadido ningún corte.")
            # El botón de reiniciar se moverá al final de la aplicación


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

        # --- BOTÓN PRINCIPAL PARA OPTIMIZAR CORTES ---
        st.header("5. Ejecutar Optimización de Cortes") 
        if st.button("Optimizar Cortes", key="optimize_cuts_button"): 
            if not st.session_state.solicitudes_cortes_ingresadas:
                st.warning("Por favor, añade al menos un corte antes de optimizar.")
            else:
                with st.spinner("Calculando la mejor optimización de cortes..."):
                    estado, num_rollos_totales, desperdicio_total, detalles_cortes_por_rollo, advertencias_cortes_grandes = \
                        optimizador_cortes_para_un_largo_rollo(
                            largo_rollo_seleccionado, 
                            st.session_state.solicitudes_cortes_ingresadas, 
                            max_items_per_pattern=max_items_per_pattern 
                        )
                
                # Almacenar resultados de la optimización de cortes en session_state
                st.session_state.cut_optimization_results = {
                    "estado": estado,
                    "num_rollos_totales": num_rollos_totales,
                    "desperdicio_total": desperdicio_total,
                    "detalles_cortes_por_rollo": detalles_cortes_por_rollo,
                    "advertencias_cortes_grandes": advertencias_cortes_grandes,
                    "largo_rollo_seleccionado": largo_rollo_seleccionado
                }
                # Limpiar resultados de fuentes anteriores si existieran
                st.session_state.source_calculation_results = None

        # --- Mostrar Resultados de Optimización de Cortes (si están disponibles) ---
        if 'cut_optimization_results' in st.session_state and st.session_state.cut_optimization_results:
            results = st.session_state.cut_optimization_results
            estado = results["estado"]
            num_rollos_totales = results["num_rollos_totales"]
            desperdicio_total = results["desperdicio_total"]
            detalles_cortes_por_rollo = results["detalles_cortes_por_rollo"]
            advertencias_cortes_grandes = results["advertencias_cortes_grandes"]
            largo_rollo_seleccionado_display = results["largo_rollo_seleccionado"] # Usar el guardado

            st.subheader("--- Resumen Final de la Optimización de Material ---")
            st.write(f"Largo de rollo seleccionado para el cálculo: **{largo_rollo_seleccionado_display:.1f} metros**")
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

                # --- NUEVO INTERRUPTOR PARA ACTIVAR/DESACTIVAR EL CÁLCULO DE FUENTES ---
                st.markdown("---")
                st.toggle("Deseo calcular las fuentes de poder para mis tiras LED (Opcional)", key="enable_source_calculation_toggle", value=True) # Valor por defecto a True

                # --- SECCIÓN PARA LA CONFIGURACIÓN Y CÁLCULO DE FUENTES DE PODER (CONDICIONAL) ---
                if st.session_state.enable_source_calculation_toggle:
                    st.header("6. Configuración y Cálculo de Fuentes") # <--- TÍTULO AJUSTADO
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
                    
                    st.info("💡 **Importante:** Cada modelo de fuente de poder tiene un **máximo de tiras o metros que puede alimentar**, lo cual se detalla en su ficha técnica. Considera esta información al seleccionar las fuentes.")

                    factor_seguridad_fuentes = st.slider(
                        "Factor de Seguridad para Fuentes (%)",
                        min_value=5, max_value=50, value=20, step=5,
                        help="El consumo real de la tira se multiplicará por este porcentaje extra para elegir una fuente que no trabaje al límite. Ej: 20% significa Consumo * 1.20"
                        ,key="safety_factor_slider" 
                    ) / 100 + 1

                    st.subheader("Modo de Asignación de Fuentes")
                    modo_asignacion_fuentes = st.radio(
                        "¿Cómo deseas asignar las fuentes de poder?",
                        ("Una fuente por cada corte", "Optimizar fuentes para agrupar cortes"),
                        key="modo_asignacion_fuentes_radio"
                    )

                    st.button("💡 Calcular Fuentes", key="calculate_sources_button", on_click=calculate_sources_callback)

                    # --- Mostrar Resultados de Cálculo de Fuentes (si están disponibles) ---
                    if 'source_calculation_results' in st.session_state and st.session_state.source_calculation_results:
                        source_results = st.session_state.source_calculation_results
                        modo = source_results["mode"]
                        total_fuentes = source_results["total_fuentes"]
                        detalles_fuentes = source_results["detalles"]

                        st.subheader("--- Resultado del Cálculo de Fuentes de Poder ---")
                        if modo == "individual":
                            st.markdown("Se asigna una fuente de poder por cada corte solicitado.")
                            if detalles_fuentes:
                                st.dataframe(pd.DataFrame(detalles_fuentes), use_container_width=True)
                                st.subheader("Resumen de Fuentes de Poder Necesarias (Individual):")
                                for fuente_w, cantidad in sorted(total_fuentes.items()):
                                    st.write(f"- Fuentes de **{fuente_w:.0f}W**: **{cantidad} unidades**")
                            else:
                                st.info("No se pudieron calcular las fuentes de poder en modo individual.")
                        elif modo == "grouped":
                            st.markdown("Se optimiza la asignación de fuentes para agrupar varios cortes en una misma fuente, minimizando el número total de fuentes.")
                            if detalles_fuentes:
                                st.dataframe(pd.DataFrame(detalles_fuentes), use_container_width=True)
                                st.subheader("Resumen de Fuentes de Poder Necesarias (Agrupado):")
                                for fuente_w, cantidad in sorted(total_fuentes.items()):
                                    st.write(f"- Fuentes de **{fuente_w:.0f}W**: **{cantidad} unidades**")
                            else:
                                st.info("No se pudieron calcular las fuentes de poder en modo agrupado.")
                        st.markdown("---") 

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
        
        # --- BOTÓN DE REINICIAR TODO (MOVIDO AL FINAL) ---
        st.markdown("---") # Separador visual
        st.button("🔄 Reiniciar Todo", key="reset_all_button_final", on_click=reset_all_callback)


if __name__ == "__main__":
    main()












