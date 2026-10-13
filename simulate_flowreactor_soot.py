import os
import re
import time
import cantera as ct
import numpy as np
import pandas as pd
from omnisoot import PlugFlowReactor, SootGas


# =============================================================================
# CONSTANTES Y CONFIGURACIÓN
# =============================================================================

Av = 6.0221408e+23  # 1/mol, número de Avogadro

# Especies PAH precursoras de hollín, específicas de cada mecanismo (los
# nombres de especie no son los mismos de un mecanismo a otro).
MECH_PRECURSORS = {
    "CRECK_SOOT": ["C10H8", "C14H10", "C16H10", "C12H8"],
    "Caltech": ["A2", "A3", "A4", "A2R5"],
    "KAUST": ["A2", "A3", "A4", "A2R5"],
    "C3Mech": ["NAPH", "PHNTHRN", "C16H10", "A2R5"],
    "ITV": ["A2", "A3XC14H10", "A4XC16H10", "A2R5"],
}


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
# FUNCIÓN PRINCIPAL DE SIMULACIÓN (Omnisoot)
# =============================================================================

def simulate_flowreactor_soot(
    mech_name,                    # Nombre del mecanismo (columna H del Excel)
    particle_dynamics_model_type, # "Monodisperse" o "Sectional" (columna J del Excel)
    PAH_growth_model_type,        # Modelo de crecimiento de PAH (columna K del Excel)
    precursors,                   # Precursores
    inlet_composition,            # Composición de entrada, formato Cantera (columna G del Excel)
    P,                            # Presión, en Pa (columna A del Excel)
    T,                            # Temperatura isoterma del reactor, en K (columna B del Excel)
    reactor_length,               # Longitud del reactor, en m (columna C del Excel)
    reactor_diameter,             # Diámetro interno del reactor, en m (columna D del Excel)
    mdot,                         # Flujo másico TOTAL de entrada, en kg/s. Ya resuelto por
                                    # launcher.py a partir de "Mass flow rate" o "Volumetric
                                    # flow rate" (columnas E/F del Excel). Aquí solo se recibe
                                    # el valor final en kg/s.
    output_file_name,             # Nombre de archivo de resultados (columna L del Excel)
    sheet_name,                   # Nombre de la hoja de resultados (columna M del Excel)
):
    
    """
    Simula la pirólisis en un reactor PFR isotermo usando Omnisoot (Cantera +
    modelado de formación de hollín), y vuelca los resultados en un archivo
    xlsx. Si el modelo de dinámica de partículas es "Sectional", además
    guarda la distribución de tamaño de partícula (PSD) a la salida del
    reactor en una segunda hoja del mismo archivo.
    """

    # -------------------------------------------------------------------
    # PASO 1: Precursores del mecanismo elegido
    # -------------------------------------------------------------------
    # Comprueba si la variable precursors está vacía. De ser así, Add/modify
    # precursors = NO, por lo que se asignan directamente del diccionario

    if not precursors:
        precursors = MECH_PRECURSORS[mech_name]

    # -------------------------------------------------------------------
    # PASO 2: Creación del gas (Cantera) y su envoltorio para Omnisoot
    # -------------------------------------------------------------------
    gas = ct.Solution(f"./data/{mech_name}.yaml")
    soot_gas = SootGas(gas)


    # -------------------------------------------------------------------
    # PASO 3: Configuración del reactor PFR
    # -------------------------------------------------------------------
   
    pfr = PlugFlowReactor(soot_gas)
    pfr.inlet.TPX = T, P, inlet_composition            
    pfr.inlet.mdot = mdot                              # kg/s
    pfr.inlet_area = np.pi / 4.0 * reactor_diameter**2 # m2

    # Perfil de temperatura isotermo: punto inicial y final con misma T
    fixed_profile = np.vstack(([0.0, reactor_length], [T, T]))
    pfr.set_fix_temperature_profile(fixed_profile)
    pfr.max_step = 1e-4    # Tamaño máximo permitido para la integración

    # -------------------------------------------------------------------
    # PASO 4: Configuración del modelo de hollín
    # -------------------------------------------------------------------
    soot = pfr.soot
    soot.particle_dynamics_model_type = particle_dynamics_model_type
    soot.PAH_growth_model_type = PAH_growth_model_type
    soot.set_precursor_names = precursors
    # Objeto interno que representa el modelo de dinámica de partículas 
    # Necesario más adelante para recuperar la PSD
    particle_dynamics = soot.particle_dynamics_model

    # -------------------------------------------------------------------
    # PASO 5: Arranque del reactor y bucle de integración
    # -------------------------------------------------------------------
    pfr.start()
    # Creando el objeto states para ir guardando el vector de solución durante la simulación
    states = ct.SolutionArray(gas, 1, extra={'restime': [0.0], 'z': [0.0], 'velocity': [pfr.u],
                                     'N_agg': [soot.N_agg], 'N_pri': [soot.N_pri],
                                     'C_tot': [soot.C_tot], 'H_tot': [soot.H_tot],
                                     'A_tot': [soot.A_tot],
                                     'd_p': [soot.d_p], 'd_m': [soot.d_m],
                                     'd_v': [soot.d_v], 'd_g': [soot.d_g],
                                     'n_p': [soot.n_p],
                                     'total_mass': [soot.total_mass],
                                     'volume_fraction': [soot.volume_fraction],
                                     'SSA': [soot.SSA],
                                     'inception_mass': [soot.inception_mass],
                                     'coagulation_mass': [soot.coagulation_mass],
                                     'PAH_adsorption_mass': [soot.PAH_adsorption_mass],
                                     'surface_growth_mass': [soot.surface_growth_mass],
                                     'oxidation_mass': [soot.oxidation_mass],
                                     'total_carbon_flux': [pfr.total_carbon_flux],
                                     'soot_carbon_flux': [pfr.soot_carbon_flux]
                                        })
    # Avanzando a lo largo del reactor hasta alcanzar la longitud total
    start_time = time.time()        # Tiempo de inicio de la simulación
    step = 0
    while pfr.z < reactor_length:
        pfr.step()
        step += 1
        if step % 20 == 0:
            states.append(gas.state, z = pfr.z, restime = pfr.restime, velocity = pfr.u,
                N_agg = soot.N_agg, N_pri = soot.N_pri,
                C_tot = soot.C_tot, H_tot = soot.H_tot, A_tot = soot.A_tot,
                d_p = soot.d_p, d_m = soot.d_m, d_v = soot.d_v, d_g = soot.d_g,
                n_p = soot.n_p,
                total_mass = soot.total_mass, volume_fraction = soot.volume_fraction, SSA = soot.SSA,
                inception_mass = soot.inception_mass,
                coagulation_mass = soot.coagulation_mass,
                PAH_adsorption_mass = soot.PAH_adsorption_mass,
                surface_growth_mass = soot.surface_growth_mass,
                oxidation_mass = soot.oxidation_mass,
                total_carbon_flux = pfr.total_carbon_flux,
                soot_carbon_flux = pfr.soot_carbon_flux
            )

    end_time = time.time()                     # Tiempo de fin de simulación
    simulation_time = end_time - start_time    # Duración de la simulación
    print(f"[soot] Simulation completed in {simulation_time:.2f} s.")
    
    # -------------------------------------------------------------------
    # PASO 6: Construcción de la tabla de resultados (DataFrame)
    # -------------------------------------------------------------------
    # Creando el dataframe a partir del vector de solución
    soot_columns = []
    soot_data = []
    flow_columns = []
    flow_data = []
    species_columns = []
    species_data = []

    soot_columns += ["N_agg[mol/kg]", "N_pri[mol/kg]", "C_tot[mol/kg]", "H_tot[mol/kg]"]
    soot_data += [states.N_agg, states.N_pri, states.C_tot, states.H_tot]

    soot_columns += ["A_tot[m2/kg]", "N_agg[#/cm3]", "N_pri[#/cm3]", "N_agg[#/g]", "N_pri[#/g]"]
    soot_data += [states.A_tot, states.N_agg*Av*states.density/1e6, states.N_pri*Av*states.density/1e6,
                 states.N_agg*Av/1e3, states.N_pri*Av/1e3]

    soot_columns += ["d_p[nm]", "d_m[nm]", "d_g[nm]", "d_v[nm]", "n_p"]
    soot_data += [states.d_p*1e9, states.d_m*1e9, states.d_g*1e9, states.d_v*1e9, states.n_p]

    soot_columns += ["soot_mass[ug/g]", "volume_fraction[-]", "SSA[m2/g]",
                     "total_carbon_flux[kg/m2-s]", "carbon_yield[-]"]
    soot_data += [states.total_mass*1e6, states.volume_fraction, states.SSA,
                  states.total_carbon_flux, states.soot_carbon_flux/states.total_carbon_flux[0]]

    soot_columns += ['inception_mass[mol/kg-s]', "coagulation_mass[mol/kg-s]",
                     "PAH_adsorption_mass[mol/kg-s]", "surface_growth_mass[mol/kg-s]"]
    soot_data += [states.inception_mass, states.coagulation_mass,
                  states.PAH_adsorption_mass, states.surface_growth_mass]

    flow_columns += ["t[s]", "z[m]", "T[K]", "density[kg/m3]", "mean_MW[kg/mol]", "velocity[m/s]"]
    flow_data += [states.restime, states.z, states.T, states.density, states.mean_molecular_weight/1000, states.velocity]

    species_columns = [f"{sp}" for sp in gas.species_names]
    species_data += [states.X[:, i] for i in range(len(gas.species_names))]

    columns = flow_columns + soot_columns + species_columns
    data = (np.array(flow_data + soot_data + species_data)).transpose()
    df = pd.DataFrame(data=data, columns=columns)

    # -------------------------------------------------------------------
    # PASO 7: Distribución de tamaño de partícula (PSD) a la salida
    #
    # Solo disponible con el modelo "Sectional" (discretiza la población
    # de partículas en secciones de tamaño). Con "Monodisperse" no existe
    # esta información, así que esta hoja simplemente no se genera.
    # -------------------------------------------------------------------
    
    # Comprueba si se ha seleccionado "Sectional" y extrae la PSD
    include_psd = (particle_dynamics_model_type == "Sectional")
    if include_psd:
        rho_outlet = gas.density  # kg/m3, densidad del gas en el último punto calculado
        d_m_sec = np.array(particle_dynamics.d_m_sec_all())      # m, diámetro de movilidad por sección
        N_agg_sec = np.array(particle_dynamics.N_agg_sec_all())  # mol/kg, agregados por sección
        N_pri_sec = np.array(particle_dynamics.N_pri_sec_all())  # mol/kg, partículas primarias por sección

        psd_columns = ["section", "d_m_sec[nm]",
                       "N_agg_sec[mol/kg]", "N_agg_sec[#/cm3]",
                       "N_pri_sec[mol/kg]", "N_pri_sec[#/cm3]"]
        psd_data = np.column_stack((
            np.arange(1, len(d_m_sec) + 1),
            d_m_sec * 1e9,
            N_agg_sec,
            N_agg_sec * Av * rho_outlet / 1e6,
            N_pri_sec,
            N_pri_sec * Av * rho_outlet / 1e6,
        ))
        df_psd = pd.DataFrame(data=psd_data, columns=psd_columns)

    # -------------------------------------------------------------------
    # PASO 8: Guardado de resultados en Excel
    #
    # El nombre de archivo y de hoja se leen directamente de los campos 
    # "Output file name" y "Excel sheet name" del Excel de inputs, saneados para
    # evitar caracteres no permitidos por Excel/el sistema de archivos.
    # -------------------------------------------------------------------
    
    # Si no existe, se crea un directorio para guardar el archivo de resultados
    output_dir = f"results/{particle_dynamics_model_type}/{PAH_growth_model_type}"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Limpiar el nombre del archivo
    clean_file_name = _sanitize_file_name(output_file_name)
    # Creación de la ruta completa del archivo
    file_name = f"{output_dir}/{clean_file_name}"

    # Limpiar el nombre de la hoja de resultados y crear el nombre de la hoja de la PSD
    clean_sheet_name = _sanitize_excel_sheet_name(sheet_name)
    psd_sheet_name = _sanitize_excel_sheet_name(f"PSD_{clean_sheet_name}")

    # Decidir si se crea ("w") o se edita el archivo ("a)
    write_mode = "a" if os.path.exists(file_name) else "w"
    
    # Se define el motor y se añade el modo de escritura. También, si el archivo
    # ya existía, se indica que, si ya hay una hoja con el mismo nombre dentro 
    # del Excel, se reemplaza con los datos de la nueva simulación
    writer_kwargs = dict(engine="openpyxl", mode=write_mode)
    if write_mode == "a":
        writer_kwargs["if_sheet_exists"] = "replace"
        
    # Exportación de los DataFrame a Excel
    with pd.ExcelWriter(file_name, **writer_kwargs) as writer:
        df.to_excel(writer, sheet_name=clean_sheet_name, index=False)
        if include_psd:
            df_psd.to_excel(writer, sheet_name=psd_sheet_name, index=False)

    # -------------------------------------------------------------------
    # PASO 9: Mensajes finales
    # -------------------------------------------------------------------
    if include_psd:
        print(f"[soot] Results written to '{file_name}', sheets '{clean_sheet_name}' and '{psd_sheet_name}'.")
    else:
        print(f"[soot] Results written to '{file_name}', sheet '{clean_sheet_name}'.")

    return file_name, clean_sheet_name



"""
EL FLUJO COMPLETO:
    
simulate_flowreactor_soot(...)
        │
        ├── 1. Comprueba los precursores
        │
        ├── 2. Carga el mecanismo químico
        │
        ├── 3. Crea SootGas
        │
        ├── 4. Crea el PFR
        │
        ├── 5. Define T, P, composición y mdot
        │
        ├── 6. Calcula el área transversal
        │
        ├── 7. Impone perfil isotermo
        │
        ├── 8. Selecciona modelo de partículas
        │
        ├── 9. Selecciona modelo de crecimiento PAH
        │
        ├── 10. Define precursores
        │
        ├── 11. Arranca el reactor
        │
        ├── 12. Guarda estado inicial
        │
        ├── 13. Integra axialmente
        │       │
        │       ├── pfr.step()
        │       ├── actualiza química
        │       ├── actualiza hollín
        │       └── guarda cada 20 pasos
        │
        ├── 14. Construye DataFrame principal
        │
        ├── 15. Calcula PSD si es Sectional
        │
        ├── 16. Crea carpeta de resultados
        │
        ├── 17. Limpia nombres
        │
        ├── 18. Guarda Excel
        │
        ├── 19. Imprime mensajes
        │
        └── 20. Devuelve nombre de archivo y hoja
"""