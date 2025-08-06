import streamlit as st
import streamlit_authenticator as stauth # Importar la librería para autenticación
import math
import pandas as pd
import collections
from PIL import Image # Necesario para cargar la imagen
# import yaml # Ya no es necesario importar yaml si solo usas st.secrets
# from yaml.loader import SafeLoader # Ya no es necesario

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
                        "Consumo Real (W)": f"{consumo_real_pieza:.2f}", # Corregido para mostrar consumo real
                        "Consumo Ajustado (W)": f"{consumo_pieza:.2f}",
                        "Fuente Asignada (W)": f"{max_fuente_disponible:.0f}",
                        "Tipo Asignación": "Excede todas las fuentes",
                        "Advertencia": f"¡Advertencia! Consumo de {consumo_real_pieza:.2f}W (ajustado a {consumo_pieza:.2f}W) excede todas las fuentes. Se asigna la más grande ({max_fuente_disponible:.0f}W)."
                    })
                else:
                    detalles_fuentes_asignadas_list.append({
                        "Largo Corte (m)": largo_original,
                        "Cantidad de Cortes": 1, # Cada pieza individual se procesa
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
        total_consumo_en_fuente = sum(c['consumo_real'] for c in fuente_obj["cortes_asignados"]) # Suma de los consumos reales
        
        detalles_finales_agrupados.append({
            "ID Fuente": f"F-{fuente_id_counter}",
            "Potencia Fuente (W)": fuente_obj["tipo"],
            "Cortes Asignados": ", ".join(cortes_str_list),
            "Consumo Total en Fuente (W)": f"{total_consumo_en_fuente:.2f}",
            "Capacidad Restante (W)": f"{fuente_obj['restante']:.2f}",
            "Advertencia": "Consumo ajustado excede capacidad" if fuente_obj["restante"] < 0 else ""
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
        
        st.session_state.largo_input = 0.1 # Reiniciar el valor del input
        st.session_state.cantidad_input = 1 # Reiniciar el valor del input
    else:
        st.error("Por favor, ingresa valores positivos para largo y cantidad.")

def clear_all_cuts_callback():
    st.session_state.solicitudes_cortes_ingresadas = {}
    st.session_state.largo_input = 0.1
    st.session_state.cantidad_input = 1
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


def main():
    # --- Lógica para reiniciar la aplicación si la bandera está activada ---
    if 'reset_app_flag' not in st.session_state:
        st.session_state.reset_app_flag = False

    if st.session_state.reset_app_flag:
        # Limpiar todas las variables de session_state a sus valores iniciales
        # No se borra 'authentication_status' ni 'name' de stauth para permitir el reinicio de la sesión
        for key in list(st.session_state.keys()):
            if key not in ['authentication_status', 'name']: # Mantener las claves de autenticación
                del st.session_state[key]
        
        # Reiniciar valores por defecto para los inputs de la aplicación
        st.session_state.solicitudes_cortes_ingresadas = {}
        st.session_state.largo_input = 0.1
        st.session_state.cantidad_input = 1
        st.session_state.watts_per_meter_input = 10.0
        st.session_state.available_sources_input = "30, 36, 40, 60, 100, 120, 150, 240, 320, 360"
        st.session_state.safety_factor_slider = 20
        st.session_state.modo_asignacion_fuentes_radio = "Una fuente por cada corte"
        st.session_state.max_pattern_items_slider = 8
        st.session_state.largo_rollo_selector = 5.0
        st.session_state.enable_source_calculation_toggle = True
        
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
        st.warning("No se encontró el archivo de imagen 'LOGO (1).png'. Asegúrate de que 'LOGO (1).png' esté en la misma carpeta que 'app.py'.") 
    
    st.title("Optimizador de cortes de tiras Jenny") 
    st.markdown("Esta herramienta te ayuda a calcular la forma más eficiente de cortar material lineal para minimizar desperdicios y la cantidad de rollos.")

    # --- Configuración de Streamlit Authenticator ---
    # Cargar credenciales desde st.secrets (para Streamlit Cloud)
    # Si estás ejecutando localmente y quieres usar config.yaml, puedes añadir un bloque try-except para cargar yaml
    # Sin embargo, para producción en Streamlit Cloud, st.secrets es el método preferido.
    
    # Nuevo bloque para cargar múltiples usuarios desde st.secrets
    users_credentials = {}
    
    try:
        # Iterar sobre los secrets para encontrar todos los usuarios
        for secret_key in st.secrets.keys():
            if secret_key.startswith("AUTH_PASSWORD_") and secret_key.endswith("_HASH"):
                username_part = secret_key.replace("AUTH_PASSWORD_", "").replace("_HASH", "").lower()
                
                # Construir las claves esperadas para este usuario
                password_key = f"AUTH_PASSWORD_{username_part.upper()}_HASH"
                email_key = f"AUTH_USER_EMAIL_{username_part.upper()}"
                name_key = f"AUTH_USER_NAME_{username_part.upper()}"
                
                # Verificar que todas las claves necesarias para este usuario existan
                if password_key in st.secrets and email_key in st.secrets and name_key in st.secrets:
                    users_credentials[username_part] = {
                        'email': st.secrets[email_key],
                        'name': st.secrets[name_key],
                        'password': st.secrets[password_key]
                    }
                else:
                    st.warning(f"Advertencia: Credenciales incompletas para el usuario '{username_part}'. "
                               "Asegúrate de que existan AUTH_PASSWORD_{USER}_HASH, AUTH_USER_EMAIL_{USER}, y AUTH_USER_NAME_{USER}.")
        
        if not users_credentials:
            st.error("¡Error de configuración! No se encontraron credenciales de usuario válidas en Streamlit Secrets. "
                     "Asegúrate de haber configurado al menos un usuario (ej. AUTH_PASSWORD_JENNY_HASH, etc.).")
            st.stop()

        config = {
            'credentials': {
                'usernames': users_credentials
            },
            'cookie': {
                'name': st.secrets["AUTH_COOKIE_NAME"],
                'key': st.secrets["AUTH_COOKIE_KEY"],
                'expiry_days': st.secrets["AUTH_COOKIE_EXPIRY_DAYS"]
            }
        }
    except KeyError as e:
        st.error(f"¡Error de configuración! Falta una clave secreta fundamental: {e}. "
                 "Asegúrate de haber configurado todos los Secrets requeridos (ej. AUTH_COOKIE_NAME, AUTH_COOKIE_KEY, AUTH_COOKIE_EXPIRY_DAYS, y al menos un usuario).")
        st.stop() # Detener la ejecución si faltan secretos
    except Exception as e:
        st.error(f"Error inesperado al cargar la configuración de autenticación: {e}")
        st.stop()

    authenticator = stauth.Authenticate(
        config['credentials'],
        config['cookie']['name'],
        config['cookie']['key'],
        config['cookie']['expiry_days']
    )

    # --- Lógica de Autenticación ---
    name, authentication_status, username = authenticator.login('Login', 'main')

    if authentication_status == False:
        st.error('Usuario/Contraseña incorrecta')
        st.stop() # Detener la ejecución si la autenticación falla
    elif authentication_status == None:
        st.warning('Por favor, ingresa tu usuario y contraseña')
        st.stop() # Detener la ejecución si no se ha intentado autenticar

    # Si la autenticación es exitosa, el resto de la aplicación se muestra
    if authentication_status:
        st.sidebar.write(f'Bienvenido, *{name}*')
        authenticator.logout('Logout', 'sidebar')

        # --- Inicialización de session_state ---
        if 'solicitudes_cortes_ingresadas' not in st.session_state:
            st.session_state.solicitudes_cortes_ingresadas = {}
        if 'largo_input' not in st.session_state:
            st.session_state.largo_input = 0.1
        if 'cantidad_input' not in st.session_state:
            st.session_state.cantidad_input = 1
        if 'watts_per_meter_input' not in st.session_state:
            st.session_state.watts_per_meter_input = 10.0
        if 'available_sources_input' not in st.session_state:
            st.session_state.available_sources_input = "30, 36, 40, 60, 100, 120, 150, 240, 320, 360"
        if 'safety_factor_slider' not in st.session_state:
            st.session_state.safety_factor_slider = 20
        if 'modo_asignacion_fuentes_radio' not in st.session_state:
            st.session_state.modo_asignacion_fuentes_radio = "Una fuente por cada corte"
        if 'max_pattern_items_slider' not in st.session_state:
            st.session_state.max_pattern_items_slider = 8
        if 'largo_rollo_selector' not in st.session_state:
            st.session_state.largo_rollo_selector = 5.0
        if 'enable_source_calculation_toggle' not in st.session_state:
            st.session_state.enable_source_calculation_toggle = True

        # --- Sidebar para configuración global ---
        st.sidebar.header("Configuración Global")
        st.sidebar.slider(
            "Factor de seguridad para fuentes (%)",
            min_value=0,
            max_value=100,
            value=st.session_state.safety_factor_slider,
            key="safety_factor_slider",
            help="Porcentaje adicional de potencia para asegurar el funcionamiento óptimo de las fuentes. Ejemplo: 20% significa que una fuente de 100W solo se usará hasta 80W."
        )
        st.session_state.watts_per_meter_input = st.sidebar.number_input(
            "Consumo de la tira (Watts/metro)",
            min_value=0.1,
            max_value=100.0,
            value=st.session_state.watts_per_meter_input,
            step=0.1,
            format="%.1f",
            key="watts_per_meter_input"
        )
        st.session_state.available_sources_input = st.sidebar.text_input(
            "Potencias de fuentes disponibles (Watts, separadas por coma)",
            value=st.session_state.available_sources_input,
            key="available_sources_input",
            help="Ejemplo: 30, 60, 100, 150"
        )
        st.session_state.modo_asignacion_fuentes_radio = st.sidebar.radio(
            "Modo de asignación de fuentes",
            ("Una fuente por cada corte", "Optimizar fuentes para agrupar cortes"),
            key="modo_asignacion_fuentes_radio",
            help="Elige si cada corte necesita una fuente individual o si se pueden agrupar en fuentes más grandes."
        )
        st.session_state.enable_source_calculation_toggle = st.sidebar.checkbox(
            "Habilitar cálculo de fuentes de poder",
            value=st.session_state.enable_source_calculation_toggle,
            key="enable_source_calculation_toggle",
            help="Deshabilita esto si solo quieres optimizar los cortes de rollos."
        )

        st.sidebar.button("Reiniciar todo", on_click=reset_all_callback, help="Borra todos los datos ingresados y la configuración.")

        # --- Sección de entrada de cortes ---
        st.header("1. Ingresar Solicitudes de Cortes")
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            st.number_input(
                "Largo del corte (metros)",
                min_value=0.1,
                max_value=100.0,
                value=st.session_state.largo_input,
                step=0.1,
                format="%.1f",
                key="largo_input"
            )
        with col2:
            st.number_input(
                "Cantidad de cortes",
                min_value=1,
                max_value=1000,
                value=st.session_state.cantidad_input,
                step=1,
                key="cantidad_input"
            )
        with col3:
            st.markdown("<br>", unsafe_allow_html=True) # Espacio para alinear el botón
            st.button("Añadir Corte", on_click=add_cut_callback)

        if st.session_state.solicitudes_cortes_ingresadas:
            st.subheader("Cortes Ingresados:")
            cortes_df = pd.DataFrame([
                {"Largo (m)": largo, "Cantidad": cantidad, "Acción": f"Eliminar {largo}"}
                for largo, cantidad in st.session_state.solicitudes_cortes_ingresadas.items()
            ])
            
            # Crear columnas para la tabla y el botón de eliminar
            cols_to_display = ["Largo (m)", "Cantidad"]
            display_df = cortes_df[cols_to_display]
            
            # Mostrar la tabla sin la columna de acción inicialmente
            st.dataframe(display_df, hide_index=True)

            # Botones de eliminar individuales
            for largo in st.session_state.solicitudes_cortes_ingresadas.keys():
                st.button(f"Eliminar {largo}m", key=f"delete_btn_{largo}", on_click=delete_cut_callback, args=(largo,))
            
            st.button("Limpiar todos los cortes", on_click=clear_all_cuts_callback)
        else:
            st.info("Aún no has ingresado ningún corte.")

        # --- Sección de Optimización de Cortes de Rollos ---
        st.header("2. Optimización de Cortes de Rollos")
        st.markdown("Esta sección calcula la forma más eficiente de cortar las tiras de rollos estándar para minimizar el desperdicio.")

        st.session_state.largo_rollo_selector = st.selectbox(
            "Largo del rollo estándar (metros)",
            options=[5.0, 10.0, 20.0, 25.0, 50.0, 100.0],
            index=0, # Valor por defecto 5.0m
            key="largo_rollo_selector",
            help="Selecciona el largo del rollo de tira LED que utilizas."
        )
        st.session_state.max_pattern_items_slider = st.slider(
            "Número máximo de cortes diferentes por patrón",
            min_value=1,
            max_value=15,
            value=st.session_state.max_pattern_items_slider,
            step=1,
            key="max_pattern_items_slider",
            help="Limita la complejidad de los patrones de corte. Un número menor puede ser más fácil de implementar."
        )

        if st.button("Optimizar Cortes de Rollos"):
            if not st.session_state.solicitudes_cortes_ingresadas:
                st.warning("Por favor, añade al menos un corte para optimizar los rollos.")
            else:
                with st.spinner("Calculando patrones de corte óptimos..."):
                    largo_rollo = st.session_state.largo_rollo_selector
                    max_pattern_items = st.session_state.max_pattern_items_slider
                    
                    # Convertir el diccionario de solicitudes a una lista de (largo, cantidad)
                    items_a_cortar = []
                    for largo, cantidad in st.session_state.solicitudes_cortes_ingresadas.items():
                        items_a_cortar.extend([largo] * cantidad)
                    
                    if not items_a_cortar:
                        st.warning("No hay cortes para optimizar.")
                        st.session_state.cut_optimization_results = None
                    else:
                        # Algoritmo de Bin Packing (First Fit Decreasing) para optimizar cortes de rollos
                        # Ordenar los cortes de mayor a menor
                        items_a_cortar.sort(reverse=True)
                        
                        rollos_utilizados = [] # Cada rollo es una lista de los cortes que contiene
                        
                        for item in items_a_cortar:
                            asignado = False
                            # Intentar colocar el corte en un rollo existente
                            for rollo in rollos_utilizados:
                                if sum(rollo) + item <= largo_rollo and len(collections.Counter(rollo).keys()) < max_pattern_items:
                                    rollo.append(item)
                                    asignado = True
                                    break
                            
                            # Si no se puede colocar en un rollo existente, usar un nuevo rollo
                            if not asignado:
                                rollos_utilizados.append([item])
                        
                        # Consolidar los resultados y calcular desperdicio
                        patrones_generados = collections.defaultdict(int)
                        detalles_patrones = []
                        total_desperdicio = 0
                        
                        for i, rollo in enumerate(rollos_utilizados):
                            rollo_actual_consumo = sum(rollo)
                            desperdicio_rollo = largo_rollo - rollo_actual_consumo
                            total_desperdicio += desperdicio_rollo
                            
                            # Crear una representación del patrón (ej: "2x 1.5m, 1x 2.0m")
                            conteo_cortes = collections.Counter(rollo)
                            patron_str = ", ".join([f"{count}x {largo:.1f}m" for largo, count in sorted(conteo_cortes.items(), reverse=True)])
                            
                            patrones_generados[patron_str] += 1
                            
                            detalles_patrones.append({
                                "ID Rollo": i + 1,
                                "Largo Rollo (m)": largo_rollo,
                                "Cortes en Rollo": patron_str,
                                "Consumo Total (m)": f"{rollo_actual_consumo:.2f}",
                                "Desperdicio (m)": f"{desperdicio_rollo:.2f}"
                            })
                        
                        total_rollos_usados = len(rollos_utilizados)
                        
                        st.session_state.cut_optimization_results = {
                            "total_rollos_usados": total_rollos_usados,
                            "total_desperdicio": total_desperdicio,
                            "patrones_generados": patrones_generados,
                            "detalles_patrones": detalles_patrones
                        }

        # Mostrar resultados de optimización de cortes de rollos
        if 'cut_optimization_results' in st.session_state and st.session_state.cut_optimization_results:
            st.subheader("Resultados de Optimización de Cortes de Rollos:")
            results = st.session_state.cut_optimization_results
            st.metric("Rollos Totales Requeridos", results["total_rollos_usados"])
            st.metric("Desperdicio Total (metros)", f"{results['total_desperdicio']:.2f} m")

            st.write("Resumen de Patrones de Corte:")
            for patron, count in results["patrones_generados"].items():
                st.write(f"- **{count}** rollos con patrón: {patron}")
            
            st.write("Detalle de Rollos Utilizados:")
            st.dataframe(pd.DataFrame(results["detalles_patrones"]), hide_index=True)


        # --- Sección de Cálculo de Fuentes de Poder ---
        if st.session_state.enable_source_calculation_toggle:
            st.header("3. Cálculo de Fuentes de Poder")
            st.markdown("Esta sección te ayuda a determinar las fuentes de poder necesarias para tus cortes, considerando un factor de seguridad.")

            st.button("Calcular Fuentes", on_click=calculate_sources_callback)

            # Mostrar resultados del cálculo de fuentes
            if 'source_calculation_results' in st.session_state and st.session_state.source_calculation_results:
                st.subheader("Resultados del Cálculo de Fuentes de Poder:")
                results = st.session_state.source_calculation_results

                if results["mode"] == "individual":
                    st.write("Resumen de Fuentes Requeridas (Una fuente por cada corte):")
                    for fuente, cantidad in results["total_fuentes"].items():
                        st.write(f"- **{cantidad}** fuentes de **{fuente:.0f}W**")
                    
                    st.write("Detalle de Asignación por Corte:")
                    st.dataframe(pd.DataFrame(results["detalles"]), hide_index=True)

                elif results["mode"] == "grouped":
                    st.write("Resumen de Fuentes Requeridas (Agrupadas):")
                    for fuente, cantidad in results["total_fuentes"].items():
                        st.write(f"- **{cantidad}** fuentes de **{fuente:.0f}W**")
                    
                    st.write("Detalle de Fuentes Agrupadas:")
                    st.dataframe(pd.DataFrame(results["detalles"]), hide_index=True)

# --- Para generar el hash de la contraseña (ejecutar una vez en un entorno Python) ---
# import streamlit_authenticator as stauth
# hashed_passwords = stauth.Hasher(['tu_contraseña_aqui']).generate()
# print(hashed_passwords)
# Copia el hash generado y pégalo en tu config.yaml

if __name__ == "__main__":
    main()
