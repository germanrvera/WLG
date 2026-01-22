from pulp import *
import collections
import math

def optimizar_cortes_para_un_largo_rollo(largo_rollo_seleccionado, solicitudes_cortes, max_items_per_pattern=None):
    """
    Optimiza el corte de material lineal para un único largo de rollo seleccionado.
    Utiliza programación dinámica para generar patrones y programación lineal para minimizar rollos.
    """

    # --- 1. Pre-procesar solicitudes: Separar cortes que exceden el rollo ---
    cortes_para_optimizar = {}
    cortes_grandes_externos = [] 

    for largo, cantidad in solicitudes_cortes.items():
        if largo > largo_rollo_seleccionado:
            cortes_grandes_externos.append({"largo": largo, "cantidad": cantidad})
        else:
            if cantidad > 0:
                cortes_para_optimizar[largo] = cortes_para_optimizar.get(largo, 0) + cantidad

    # Procesar cortes grandes externos
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
            "Cortes_en_rollo": [f"TOTAL {total_metros_requeridos_grandes:.1f}m (Piezas > {largo_rollo_seleccionado:.1f}m)"],
            "Desperdicio_en_rollo": desperdicio_para_total_grandes,
            "Metros_Consumidos_para_esta_pieza": total_metros_requeridos_grandes, 
            "Rollos_Fisicos_Asignados": num_rollos_para_total_grandes 
        })
        
    if not cortes_para_optimizar:
        return "Optimal (Solo Piezas Grandes)", \
               total_rollos_grandes_externas, \
               total_desperdicio_grandes_externas, \
               detalles_cortes_grandes_externos_formateados, \
               cortes_grandes_externos

    # --- 2. Generar patrones de corte válidos (Programación Dinámica) ---
    largos_unicos = sorted(cortes_para_optimizar.keys(), reverse=True)
    
    def generar_patrones_eficiente(capacidad, items, max_items):
        # dp[w] guardará una lista de patrones (tuplas) que suman exactamente w o menos
        # Para evitar explosión de memoria, limitamos a patrones únicos útiles
        patrones_por_peso = collections.defaultdict(set)
        patrones_por_peso[0].add(())

        for item_largo in items:
            # Cantidad máxima de este item que cabe en un rollo
            max_posible = int(capacidad // item_largo)
            # Si hay restricción de items totales, respetarla
            if max_items:
                max_posible = min(max_posible, max_items)
            
            for peso_actual in range(int(capacidad), int(item_largo) - 1, -1):
                for cant in range(1, max_posible + 1):
                    peso_nuevo = peso_actual - (cant * item_largo)
                    if peso_nuevo >= 0:
                        for p in patrones_por_peso[peso_nuevo]:
                            nuevo_p = tuple(sorted(list(p) + [item_largo] * cant))
                            if max_items is None or len(nuevo_p) <= max_items:
                                if sum(nuevo_p) <= capacidad:
                                    patrones_por_peso[peso_actual].add(nuevo_p)

        # Consolidar todos los patrones encontrados en todas las capacidades
        todos = set()
        for p_set in patrones_por_peso.values():
            todos.update(p_set)
        
        # Eliminar el patrón vacío y filtrar patrones que no sirven (sub-patrones de otros)
        resultado = [p for p in todos if p]
        return resultado

    # Generamos los patrones
    patrones_unicos = generar_patrones_eficiente(largo_rollo_seleccionado, largos_unicos, max_items_per_pattern)

    if not patrones_unicos:
        return "Infeasible (No se generaron patrones)", 0, 0, [], []

    # --- 3. Modelo de Optimización (PuLP) ---
    problema = LpProblem("Minimizar_Rollos", LpMinimize)
    
    # Variables: x[i] es la cantidad de veces que usamos el patrón i
    x = LpVariable.dicts("P", range(len(patrones_unicos)), 0, None, LpInteger)

    # Objetivo: Minimizar total de rollos
    problema += lpSum([x[i] for i in range(len(patrones_unicos))])

    # Restricciones: Satisfacer demanda de cada corte
    for largo in largos_unicos:
        demanda = cortes_para_optimizar[largo]
        problema += lpSum([x[i] * patrones_unicos[i].count(largo) for i in range(len(patrones_unicos))]) >= demanda

    # Resolver
    # msg=0 desactiva los logs de consola de PuLP
    problema.solve(PULP_CBC_CMD(msg=0))
    
    estado_solucion = LpStatus[problema.status]

    detalles_optimizador = []
    num_rollos_opt = 0
    
    if estado_solucion == 'Optimal':
        num_rollos_opt = int(value(problema.objective))
        
        id_cnt = 1
        for i in range(len(patrones_unicos)):
            usos = int(x[i].varValue)
            if usos > 0:
                for _ in range(usos):
                    patron = list(patrones_unicos[i])
                    consumo = sum(patron)
                    detalles_optimizador.append({
                        "Rollo_ID": f"Opt-Rollo-{id_cnt}",
                        "Tipo_Rollo": largo_rollo_seleccionado,
                        "Cortes_en_rollo": patron,
                        "Desperdicio_en_rollo": largo_rollo_seleccionado - consumo,
                        "Metros_Consumidos_en_este_rollo": consumo
                    })
                    id_cnt += 1

    # Consolidar resultados finales
    num_rollos_totales = num_rollos_opt + total_rollos_grandes_externas
    
    # El desperdicio se calcula sobre el material total comprado vs material realmente pedido
    total_pedido_neto = sum(l * c for l, c in solicitudes_cortes.items())
    desperdicio_total = (num_rollos_totales * largo_rollo_seleccionado) - total_pedido_neto

    return (
        estado_solucion, 
        num_rollos_totales, 
        max(0, desperdicio_total), 
        detalles_cortes_grandes_externos_formateados + detalles_optimizador, 
        cortes_grandes_externos
    )
