# optimizador_logic.py
from pulp import *
import collections
import math

# Asegúrate de que esta función acepte max_items_per_pattern
def optimizar_cortes_para_un_largo_rollo(largo_rollo_seleccionado, solicitudes_cortes, max_items_per_pattern=None):
    """
    Optimiza el corte de material lineal para un único largo de rollo seleccionado,
    minimizando el número de rollos y el desperdicio.
    Maneja cortes muy grandes por separado para alinear con la expectativa de desperdicio cero
    si el total de metros de estos cortes es un múltiplo del rollo.

    Args:
        largo_rollo_seleccionado (float): La longitud del rollo que se usará para todos los cortes.
        solicitudes_cortes (dict): Un diccionario donde la clave es el largo del corte
                                   (float) y el valor es la cantidad solicitada (int).
        max_items_per_pattern (int, optional): Número máximo de piezas individuales en un patrón de corte.
                                                Útil para controlar la complejidad y el rendimiento.
    """

    # --- 1. Pre-procesar solicitudes: Separar cortes que exceden el rollo seleccionado ---
    cortes_para_optimizar = {}
    cortes_grandes_externos = [] 

    for largo, cantidad in solicitudes_cortes.items():
        if largo > largo_rollo_seleccionado:
            cortes_grandes_externos.append({"largo": largo, "cantidad": cantidad})
        else:
            cortes_para_optimizar[largo] = cortes_para_optimizar.get(largo, 0) + cantidad

    # --- Procesar cortes grandes externos: Calculamos su contribución a rollos y desperdicio ---
    total_rollos_grandes_externas = 0
    total_desperdicio_grandes_externas = 0
    detalles_cortes_grandes_externos_formateados = []

    if cortes_grandes_externos:
        total_metros_requeridos_grandes = sum(c['largo'] * c['cantidad'] for c in cortes_grandes_externos)
        
        num_rollos_para_total_grandes = math.ceil(total_metros_requeridos_grandes / largo_rollo_seleccionado)
        
        material_consumido_para_grandes = num_rollos_para_total_grandes * largo_rollo_seleccionado
        desperdicio_para_total_grandes = material_consumido_para_grandes - total_metros_requeridos_grandes

        total_rollos_grandes_externas = num_rollos_para_total_grandes
        total_desperdicio_grandes_externas = desperdicio_para_total_grandes

        detalles_cortes_grandes_externos_formateados.append({
            "Rollo_ID": "RESUMEN_PIEZAS_GRANDES",
            "Tipo_Rollo": largo_rollo_seleccionado,
            "Cortes_en_rollo": [f"TOTAL {total_metros_requeridos_grandes:.1f}m (para {sum(c['cantidad'] for c in cortes_grandes_externos)} piezas grandes > {largo_rollo_seleccionado:.1f}m)"],
            "Desperdicio_en_rollo": desperdicio_para_total_grandes,
            "Metros_Consumidos_para_esta_pieza": total_metros_requeridos_grandes, 
            "Rollos_Fisicos_Asignados": num_rollos_para_total_grandes 
        })
        
    if not cortes_para_optimizar:
        return "Optimal (Solo Cortes Mayores al Rollo Seleccionado)", \
               total_rollos_grandes_externas, \
               total_desperdicio_grandes_externas, \
               detalles_cortes_grandes_externos_formateados, \
               cortes_grandes_externos


    # --- 2. Generar patrones de corte válidos para el largo de rollo seleccionado (solo para cortes_para_optimizar) ---
    largos_unicos_a_optimizar = sorted(list(cortes_para_optimizar.keys()), reverse=True)

    # La función interna también debe aceptar max_items
    def generar_todos_los_patrones(largos_disponibles, largo_maximo_patron, current_pattern=[], max_items=None):
        patrones = []
        suma_actual = sum(current_pattern)

        # Si el patrón actual excede el número máximo de ítems permitidos, lo ignoramos
        if max_items is not None and len(current_pattern) >= max_items:
            # Si ya tenemos un patrón válido (no vacío y que cabe), lo añadimos antes de detener la recursión
            if suma_actual <= largo_maximo_patron and current_pattern:
                patrones.append(current_pattern)
            return patrones

        # Si el patrón actual es válido (no excede el largo del rollo) y no está vacío, lo agregamos
        if suma_actual <= largo_maximo_patron and current_pattern:
            patrones.append(current_pattern)

        for i, largo in enumerate(largos_disponibles):
            # Si al agregar el siguiente corte, no excedemos el largo del rollo
            if suma_actual + largo <= largo_maximo_patron:
                nuevos_patrones = generar_todos_los_patrones(
                    largos_disponibles[i:], largo_maximo_patron, current_pattern + [largo], max_items # Pasa max_items
                )
                patrones.extend(nuevos_patrones)
        return patrones

    # Llamar a la función de generación de patrones con el nuevo límite
    todos_los_patrones = [
        tuple(sorted(p)) for p in generar_todos_los_patrones(largos_unicos_a_optimizar, largo_rollo_seleccionado, max_items=max_items_per_pattern) # Pasa max_items_per_pattern
    ]
    patrones_unicos = list(collections.OrderedDict.fromkeys(todos_los_patrones))

    if not patrones_unicos:
        return "No hay patrones válidos generados para cortes pequeños", \
               total_rollos_grandes_externas, \
               total_desperdicio_grandes_externas, \
               detalles_cortes_grandes_externos_formateados, \
               cortes_grandes_externos

    # --- 3. Crear el modelo de optimización (Problema de Programación Lineal) ---
    problema = LpProblem("Minimizar Desperdicio de Corte", LpMinimize)

    # Variables de decisión: x[i] = cuántas veces usamos el patrón i
    x = LpVariable.dicts("UsoPatron", range(len(patrones_unicos)), 0, None, LpInteger)

    # --- 4. Función Objetivo: Minimizar el número total de rollos utilizados ---
    problema += lpSum([x[i] for i in range(len(patrones_unicos))]), "Total de Rollos Usados"

    # --- 5. Restricciones: Asegurarse de que todos los cortes solicitados se cumplan ---
    for largo_requerido, cantidad_solicitada in cortes_para_optimizar.items():
        problema += lpSum([
            x[i] * patrones_unicos[i].count(largo_requerido)
            for i in range(len(patrones_unicos))
        ]) >= cantidad_solicitada, f"Cumplir_Corte_{largo_requerido}"

    # --- 6. Resolver el problema ---
    problema.solve()

    # --- 7. Procesar y devolver los resultados ---
    estado_solucion = LpStatus[problema.status]

    num_rollos_optimizador = 0
    desperdicio_optimizador = 0
    detalles_cortes_optimizador_formateados = []

    if estado_solucion == 'Optimal':
        num_rollos_optimizador = problema.objective.value()
        
        total_cortado_necesario_optimizador = sum(l * c for l, c in cortes_para_optimizar.items())
        desperdicio_optimizador = (num_rollos_optimizador * largo_rollo_seleccionado) - total_cortado_necesario_optimizador
        
        rollo_id_contador_opt = 1
        for i in range(len(patrones_unicos)):
            num_usos_patron = int(x[i].varValue)
            if num_usos_patron > 0:
                for _ in range(num_usos_patron):
                    patron_actual = list(patrones_unicos[i])
                    uso_material_en_patron = sum(patron_actual)
                    desperdicio_en_este_rollo = largo_rollo_seleccionado - uso_material_en_patron
                    
                    detalles_cortes_optimizador_formateados.append({
                        "Rollo_ID": f"Opt-Rollo-{rollo_id_contador_opt}",
                        "Tipo_Rollo": largo_rollo_seleccionado,
                        "Cortes_en_rollo": patron_actual,
                        "Desperdicio_en_rollo": desperdicio_en_este_rollo,
                        "Metros_Consumidos_en_este_rollo": uso_material_en_patron
                    })
                    rollo_id_contador_opt += 1

    # Consolidar todos los resultados (cortes grandes externos + optimizados)
    num_rollos_totales_final = num_rollos_optimizador + total_rollos_grandes_externas
    desperdicio_total_final = desperdicio_optimizador + total_desperdicio_grandes_externas
    
    todos_los_detalles_de_rollos = detalles_cortes_grandes_externos_formateados + detalles_cortes_optimizador_formateados

    return estado_solucion, num_rollos_totales_final, desperdicio_total_final, todos_los_detalles_de_rollos, cortes_grandes_externos
