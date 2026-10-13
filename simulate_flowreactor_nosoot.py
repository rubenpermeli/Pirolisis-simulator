import os
import re
import time
import cantera as ct
import numpy as np
import pandas as pd


# =============================================================================
# CONSTANTES
# =============================================================================

# Número de reactores agitados (CSTR) en cadena usados para aproximar el PFR.
# No es un input del Excel: es un parámetro numérico interno del método de
# solución (a más pasos, más precisión pero más tiempo de cálculo).
n_steps = 500


# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================

def _sanitize_excel_sheet_name(name):
    """
    Adapta un texto libre para que sea un nombre de hoja de Excel válido:
    - Excel prohíbe los caracteres : \\ / ? * [ ]
    - El nombre no puede superar los 31 caracteres
    - El nombre no puede estar vacío
    Devuelve el nombre adaptado
    """
    # Si no se proporciona nombre de hoja, "Sheet1" se asigna como predeterminado
    if not name:
        name = "Sheet1"
    # Sustitución de caracteres no permitidos por "_"
    clean_name = re.sub(r'[:\\/?*\[\]]', '_', str(name))
    # Limitación del nombre a 31 caracteres
    clean_name = clean_name[:31]
    return clean_name          # Devuelve el nombre adaptado


def _sanitize_file_name(name):
    """
    Adapta el nombre de archivo introducido por el usuario en el Excel:
    - Quita caracteres no válidos para nombres de archivo en disco
    - Se asegura de que termine en '.xlsx'
    Devuelve el nombre adaptado
    """
    # Si no se proporciona nombre de hoja, "sim_results" se asigna como predeterminado
    if not name:
        name = "sim_results"
    # Sustitución de caracteres no permitidos por "_"
    clean_name = re.sub(r'[<>:"/\\|?*]', '_', str(name))
    # Se añade la extensión ".xlsx" si el nombre no la contiene
    if not clean_name.lower().endswith(".xlsx"):
        clean_name += ".xlsx"
    return clean_name          # Devuelve el nombre adaptado


# =============================================================================
# FUNCIÓN PRINCIPAL DE SIMULACIÓN (solo Cantera, sin hollín)
# =============================================================================

def simulate_flowreactor_nosoot(
    mech_name,           # Nombre del mecanismo (columna H del Excel)
    inlet_composition,   # Composición de entrada, formato Cantera (columna G del Excel)
    P,                   # Presión, en Pa (columna A del Excel)
    T,                   # Temperatura isoterma del reactor, en K (columna B del Excel)
    reactor_length,      # Longitud del reactor, en m (columna C del Excel)
    reactor_diameter,    # Diámetro interno del reactor, en m (columna D del Excel)
    mdot,                # Flujo másico TOTAL de entrada, en kg/s. Ya resuelto por
                            # launcher.py a partir de "Mass flow rate" o "Volumetric
                            # flow rate" (columnas E/F del Excel). Aquí solo se recibe
                            # el valor final en kg/s.
    output_file_name,    # Nombre de archivo de resultados (columna L del Excel)
    sheet_name,          # Nombre de la hoja de resultados (columna M del Excel)
):
    """
    Simula la pirólisis en un reactor PFR isotermo usando únicamente Cantera
    (sin Omnisoot, sin modelado de hollín), mediante el método de "cadena de
    reactores": el PFR se aproxima como una serie de n_steps reactores
    agitados (CSTR) en serie, cada uno integrado hasta su estado
    estacionario, con la salida de uno como entrada del siguiente. Los
    resultados se vuelcan en un archivo xlsx, con el mismo formato de
    columnas que simulate_flowreactor_soot.py, pero sin las columnas de
    hollín.
    """

    # -------------------------------------------------------------------
    # PASO 1: Creación del gas (Cantera) y fijación del estado de entrada
    # -------------------------------------------------------------------
    gas = ct.Solution(f"./data/{mech_name}.yaml")
    gas.TPX = T, P, inlet_composition

    # -------------------------------------------------------------------
    # PASO 2: Geometría del reactor
    # -------------------------------------------------------------------
    cross_section_area = np.pi / 4.0 * reactor_diameter**2   # m2, área de sección
    dz = reactor_length / n_steps                            # m, longitud de cada "rebanada" del reactor
    r_vol = cross_section_area * dz                          # m3, volumen de cada reactor de la cadena

    # -------------------------------------------------------------------
    # PASO 3: Construcción de la cadena de reactores
    #
    # El gas a la entrada del primer reactor tiene la composición de
    # entrada especificada; para todos los demás, la entrada es la
    # composición del reactor inmediatamente anterior. Como en un modelo
    # de PFR no hay difusión, los reactores aguas arriba no se ven
    # afectados por los de aguas abajo, así que el problema se resuelve
    # avanzando del primero al último, integrando cada uno hasta su
    # estado estacionario.
    # -------------------------------------------------------------------
    
    # Se desactiva la ecuación de energía (reactor isotermo)
    r = ct.IdealGasReactor(gas, clone=True, energy='off')
    r.volume = r_vol

    # Depósito que representa el reactor inmediatamente aguas arriba
    upstream = ct.Reservoir(gas, name='upstream', clone=True)

    # Depósito de salida (aguas abajo); su composición es irrelevante
    downstream = ct.Reservoir(gas, name='downstream', clone=True)

    # El flujo másico de entrada se fija con un MassFlowController
    m = ct.MassFlowController(upstream, r, mdot=mdot)

    # Controlador de presión hacia el depósito de salida; determina la
    # presión del reactor. El valor de K solo afecta a la diferencia de
    # presión transitoria, no al resultado en estado estacionario
    v = ct.PressureController(r, downstream, primary=m, K=1e-5)

    sim = ct.ReactorNet([r])
    sim.max_time_step = 1e4

    # -------------------------------------------------------------------
    # PASO 4: Bucle de integración a lo largo de la cadena de reactores
    # -------------------------------------------------------------------
    
    # Preparación de los arrays de resultados
    z = (np.arange(n_steps) + 1) * dz
    t_r = np.zeros_like(z)      # tiempo de residencia en cada reactor
    u = np.zeros_like(z)
    t = np.zeros_like(z)
    states = ct.SolutionArray(gas)

    start_time = time.time()    # Tiempo de inicio de la simulación
    for n in range(n_steps):
        # Se fija el estado del depósito de entrada igual al del reactor anterior
        upstream.phase.TDY = r.phase.TDY
        upstream.syncState()
        # Se integra el reactor hacia adelante en el tiempo hasta alcanzar el estado estacionario
        sim.reinitialize()
        sim.advance_to_steady_state()
        # Cálculo de velocidad y tiempo de residencia acumulado
        u[n] = mdot / cross_section_area / r.phase.density
        t_r[n] = r.mass / mdot
        t[n] = np.sum(t_r)
        # Se guarda el estado resultante
        states.append(r.phase.state)
    end_time = time.time()                    # Tiempo de fin de la simulación
    simulation_time = end_time - start_time   # Duración de la simulación

    # -------------------------------------------------------------------
    # PASO 5: Construcción de la tabla de resultados (DataFrame)
    # -------------------------------------------------------------------
    df = pd.DataFrame({
        "t[s]": t,
        "z[m]": z,
        "T[K]": states.T,
        "density[kg/m3]": states.density,
        "mean_MW[kg/mol]": states.mean_molecular_weight / 1000,
        "velocity[m/s]": u,
    })

    for sp in gas.species_names:
        df[f"{sp}"] = states.X[:, gas.species_index(sp)]

    # -------------------------------------------------------------------
    # PASO 6: Guardado de resultados en Excel
    #
    # El nombre de archivo y de hoja se leen directamente de los campos 
    # "Output file name" y "Excel sheet name" del Excel de inputs, saneados para
    # evitar caracteres no permitidos por Excel/el sistema de archivos.
    # -------------------------------------------------------------------
    
    # Si no existe, se crea un directorio para guardar el archivo de resultados
    output_dir = "results/NoSoot"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Limpiar el nombre del archivo
    clean_file_name = _sanitize_file_name(output_file_name)
    # Creación de la ruta completa del archivo
    file_name = f"{output_dir}/{clean_file_name}"

    # Limpiar el nombre de la hoja de resultados
    clean_sheet_name = _sanitize_excel_sheet_name(sheet_name)
   
    # Decidir si se crea ("w") o se edita el archivo ("a)
    write_mode = "a" if os.path.exists(file_name) else "w"
    
    # Se define el motor y se añade el modo de escritura. También, si el archivo
    # ya existía, se indica que, si ya hay una hoja con el mismo nombre dentro 
    # del Excel, se reemplaza con los datos de la nueva simulación
    writer_kwargs = dict(engine="openpyxl", mode=write_mode)
    if write_mode == "a":
        writer_kwargs["if_sheet_exists"] = "replace"

    # Exportación del DataFrame a Excel
    with pd.ExcelWriter(file_name, **writer_kwargs) as writer:
        df.to_excel(writer, sheet_name=clean_sheet_name, index=False)

    # -------------------------------------------------------------------
    # PASO 7: Mensajes finales
    # -------------------------------------------------------------------
    print(f"[nosoot] Simulation completed in {simulation_time:.2f} s.")
    print(f"[nosoot] Results written to '{file_name}', sheet '{clean_sheet_name}'.")

    return file_name, clean_sheet_name



"""
EL FLUJO COMPLETO:
    
simulate_flowreactor_nosoot(...)
    │
    ├── Carga mecanismo Cantera
    │
    ├── Define estado inicial
    │
    ├── Calcula área transversal
    │
    ├── Divide longitud en 500 segmentos
    │
    ├── Calcula volumen de cada CSTR
    │
    ├── Crea reactor CSTR
    │
    ├── Crea depósitos upstream/downstream
    │
    ├── Crea MassFlowController
    │
    ├── Crea PressureController
    │
    ├── Crea ReactorNet
    │
    ├── Para cada segmento:
    │      ├── Actualiza la entrada
    │      ├── Reinicializa la red
    │      ├── Integra hasta estado estacionario
    │      ├── Calcula velocidad
    │      ├── Calcula tiempo de residencia
    │      └── Guarda composición
    │
    ├── Construye DataFrame
    │
    ├── Añade columnas de todas las especies
    │
    ├── Crea results/NoSoot
    │
    ├── Limpia nombre de archivo y hoja
    │
    ├── Guarda Excel
    │
    └── Devuelve archivo y hoja
"""