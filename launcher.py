import cantera as ct
import pandas as pd
import os
from simulate_flowreactor_soot import simulate_flowreactor_soot
from simulate_flowreactor_nosoot import simulate_flowreactor_nosoot
from plot import make_plots

# %%
# =============================================================================
# CONFIGURACIÓN
# =============================================================================

# Archivo de entrada, hoja de Excel y fila de encabezados
INPUTS_FILE = "inputs.xlsx"
INPUTS_SHEET = "Inputs"
HEADER_EXCEL_ROW = 4  # fila del Excel donde están los encabezados de columna

# Nombres de columna EXACTOS del Excel de inputs. Deben coincidir con los
# encabezados reales de la hoja "Inputs" -- si alguien renombra una columna
# en el Excel, hay que actualizar también aquí (ver Instructions!A11 del
# propio Excel: "Do not rename worksheet names or column headers if the
# Python reader depends on them").
COL_PRESSURE = "Pressure [Pa] *"
COL_TEMPERATURE = "Temperature [K] *"
COL_LENGTH = "Reactor length [m] *"
COL_DIAMETER = "Reactor diameter [m] *"
COL_MASS_FLOW = "Mass flow rate [kg/s]"
COL_VOL_FLOW = "Volumetric flow rate [m3/s]"
COL_COMPOSITION = "Inlet composition *"
COL_MECHANISM = "Chemical mechanism *"
COL_SIMULATE_SOOT = "Simulate soot *"
COL_PARTICLE_MODEL = "Particle dynamic model"
COL_PAH_MODEL = "PAH growth model"
COL_ADD_PRECURSORS = "Add/modify precursors"
COL_PRECURSORS = "Precursors"
COL_OUTPUT_FILE = "Output file name"
COL_SHEET_NAME = "Excel sheet name"
COL_PLOTS = "Plots"


# %%
# =============================================================================
# LECTURA Y VALIDACIÓN DE LOS INPUTS
# =============================================================================

def _read_inputs(path=INPUTS_FILE, sheet=INPUTS_SHEET):
    """
    Lee la hoja de inputs del Excel y devuelve un DataFrame con una fila por
    simulación a ejecutar, descartando filas completamente vacías.
    Se comprueba que el DataFrame no esté vacío.
    """
    # Abrir y leer el archivo Excel. Crear el DataFrame con los datos
    df = pd.read_excel(path, sheet_name=sheet, header=HEADER_EXCEL_ROW - 1)
    
    # Eliminar las filas o columnas si todas sus celdas están vacías
    df = df.dropna(how="all")
    
    # Comprobar si el DataFrame está vacío, generando un error en caso positivo
    if df.empty:
        raise ValueError(
            f"No data rows found in sheet '{sheet}' of '{path}'. "
            f"Fill in at least one row below the header before running the launcher."
        )
    return df     # Devuelve el DataFrame con los datos de entrada


def _require(row, column):
    """
    Devuelve el valor de una columna obligatoria (marcada con "*" en el
    Excel), lanzando un error claro si está en blanco para que el
    usuario (que no tiene por qué saber Python) entienda exactamente qué
    casilla le falta por rellenar.
    """
    # Obtener el valor del input DataFrame. "row" es una serie de Pandas que
    # almacena una línea de inputs, declarada adelante en la función "main()"
    value = row.get(column)
    
    # COMPROBACIÓN DE QUE NO ES UN INPUT EN BLANCO
    # pd.isna comprueba si es un dato ausente como "NaN" o "None"
    # isinstance(value, str) devuelve "True" si valor es tipo string
    # value.strip elimina espacios al principio y al final
    if pd.isna(value) or (isinstance(value, str) and value.strip() == ""):
        raise ValueError(
            f"Required field '{column}' is empty. Please fill it in the "
            f"'{INPUTS_SHEET}' sheet of '{INPUTS_FILE}'."
        )
    return value   # Devuelve un input habiendo comprobado que no está vacío


def _optional_str(row, column):
    """
    Devuelve el valor de una columna opcional de texto, o None si la
    celda está en blanco. Se usa para leer file name y sheet name.
    Necesario porque una celda vacía de Excel llega
    a pandas como NaN (float), no como None, y NaN, al convertirlo
    directamente a str(), da el texto literal "nan".
    """
    # Obtener el valor del input DataFrame
    value = row.get(column)
    
    # Si el input está vacío, devuelve None
    if pd.isna(value):
        return None
    
    # Si no está vacío, devuelve el texto suprimiendo espacios a los extremos
    return str(value).strip()


def _resolve_mass_flow_rate(row, mech_name):
    """
    Determina el flujo másico total de entrada (mdot, en kg/s), a partir de
    uno de los dos campos de caudal del Excel:
    - "Mass flow rate [kg/s]": se usa directamente.
    - "Volumetric flow rate [m3/s]": se convierte a másico multiplicando
      por la densidad del gas en las condiciones de entrada (T, P,
      composición), calculada aquí con Cantera.
    Devuelve el flujo másico en kg/s.
    """
    
    # Leer y almacenar los inputs
    mass_flow_rate = row.get(COL_MASS_FLOW)
    vol_flow_rate = row.get(COL_VOL_FLOW)
    
    # Almacenar TRUE si los campos están rellenos
    mass_given = pd.notna(mass_flow_rate)
    vol_given = pd.notna(vol_flow_rate)

    # Comprobar si se han introducido ambos datos de caudal
    # Genera un error en caso afirmativo
    if mass_given and vol_given:
        raise ValueError(
            f"Both '{COL_MASS_FLOW}' and '{COL_VOL_FLOW}' are filled in. "
            f"Leave exactly one of the two blank."
        )
        
    # Comprobar si no se ha introducido ninguno de los datos de caudal
    # Genera un error en caso afirmativo
    if not mass_given and not vol_given:
        raise ValueError(
            f"Neither '{COL_MASS_FLOW}' nor '{COL_VOL_FLOW}' is filled in. "
            f"Enter one of the two."
        )

    # Comprobar si el caudal se ha indicado como flujo másico
    # Devuelve el valor del flujo másico como float
    if mass_given:
        return float(mass_flow_rate)
    
    # Si se ha introducido el cadual como flujo volumétrico, hay que convertirlo
    # a flujo másico, usando la densidad del gas en las condiciones de entrada
    # Se crea un objeto de Cantera "de usar y tirar" solo para este cálculo
    # Devuelve el valor del flujo másico como float
    gas = ct.Solution(f"./data/{mech_name}.yaml")
    gas.TPX = float(_require(row, COL_TEMPERATURE)), float(_require(row, COL_PRESSURE)), _require(row, COL_COMPOSITION)
    rho_inlet = gas.density  # kg/m3
    return float(vol_flow_rate) * rho_inlet


# %%
# =============================================================================
# EJECUCIÓN DE UNA SIMULACIÓN
# =============================================================================

def run_simulation(row):
    """
    Ejecuta una simulación (con o sin Omnisoot, según la columna
    "Simulate soot *") a partir de una fila de la hoja de inputs, y genera
    las gráficas si "Plots" está marcado como YES.
    
    Flujo:   
    fila Excel
   │
   ├── obtener mecanismo
   ├── comprobar YES/NO para soot
   ├── comprobar YES/NO para gráficas
   ├── obtener mdot
   ├── construir argumentos comunes
   ├── llamar a soot o nosoot
   ├── generar gráficas si corresponde
   └── devolver archivo y hoja de salida
    """
    
    # Obtención del mecanismo y comprobación de que el archivo .yaml 
    # se encuentra disponible en la carpeta "data".
    mech_name = _require(row, COL_MECHANISM)
    if not os.path.isfile(f"./data/{mech_name}.yaml"):
        raise ValueError(
            f"Unknown cheminal mechanism '{mech_name}'."
            f"Add {mech_name}.yaml to data."
        )
  
    # INTERPRETAR SI SE SIMULA TENIENDO EN CUENTA LA FORMACIÓN DE HOLLÍN
    # Usa _require() para obtener el valor del input DataFrame
    # .strip elimina espacios al principio y al final
    # .upper convierte el texto a mayúsculas
    # == "YES" compara con "YES", teniendo como resultado un booleano True o False
    simulate_soot = str(_require(row, COL_SIMULATE_SOOT)).strip().upper() == "YES"
    
    # INTERPRETAR SI SE GENERAN GRÁFICAS
    # Usa row.get() directamente porque no es un input obligatorio, fijando 
    # por defecto "NO" si se deja el campo vacío
    make_plots_flag = str(row.get(COL_PLOTS, "NO")).strip().upper() == "YES"

    # Obtención del flujo másico, guardándolo en la variable mdot en kg/s
    mdot = _resolve_mass_flow_rate(row, mech_name)

    # CREACIÓN DEL DICCIONARIO DE ARGUMENTOS COMUNES
    # Argumentos comunes a ambos motores de simulación (soot y nosoot),
    # con exactamente los mismos nombres de parámetro en las dos funciones.
    common_args = dict(
        mech_name = mech_name,
        inlet_composition = _require(row, COL_COMPOSITION),
        P = float(_require(row, COL_PRESSURE)),
        T = float(_require(row, COL_TEMPERATURE)),
        reactor_length = float(_require(row, COL_LENGTH)),
        reactor_diameter = float(_require(row, COL_DIAMETER)),
        mdot = mdot,
        output_file_name = _optional_str(row, COL_OUTPUT_FILE),
        sheet_name = _optional_str(row, COL_SHEET_NAME),
    )
    
    
    # EJECUTAR LA SIMULACIÓN CON O SIN FORMACIÓN DE HOLLÍN 
    # Comprueba si simulate_soot == True, lee los parámetros restantes necesarios
    # para simular hollín y llama a la función "simulate_flowreactor_soot"
    # Si add_modify_precursors == True, añade los precursores a la simulación,
    # transformando el string en una lista usando la "," como separación entre elementos
    # Si add_modify_precursors == False, la variable queda vacía para poder asignar 
    # los precursores establecidos en el diccionario.
    # Si simulate_soot == False, ejecuta directamente la función sin soot
    if simulate_soot:
        particle_dynamics_model_type = _require(row, COL_PARTICLE_MODEL)
        PAH_growth_model_type = _require(row, COL_PAH_MODEL)
        add_modify_precursors = str(row.get(COL_ADD_PRECURSORS, "NO")).strip().upper() == "YES"
        if add_modify_precursors:
            precursors_text = _require(row, COL_PRECURSORS)
            precursors = [elemento.strip() for elemento in precursors_text.split(",")]
        else:
            precursors = None
        file_name, sheet_name = simulate_flowreactor_soot(
        particle_dynamics_model_type = particle_dynamics_model_type,
        PAH_growth_model_type = PAH_growth_model_type,
        precursors = precursors,
        **common_args)
    else:
        file_name, sheet_name = simulate_flowreactor_nosoot(**common_args)

    # GENERACIÓN OPCIONAL DE GRÁFICAS
    # Comprueba si make_flow_flag == True y, en caso afirmativo, 
    # llama a la función "make_plots".
    if make_plots_flag:
        make_plots(file_name, sheet_name, simulate_soot=simulate_soot)


# %%
# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================

def main():
    """
    Función principal del programa.
    Coordina la ejecución completa de la simulación. Desde aquí se leen y se 
    almacenan los inputs en la serie "row", que luego sirve como entrada para
    la función "run_simulation", encargándose esta de gestionar los inputs y
    ejecutar la simulación con los parámetros deseados. Luego, se itera para 
    las diferentes filas de inputs_df, llevando a cabo una simulación por cada fila.
    """
    # Obtención del DataFrame de los inputs
    inputs_df = _read_inputs()
    
    # Bucle que ejecuta las diferentes simulaciones contenidas en el DataFrame
    for _, row in inputs_df.iterrows():
        run_simulation(row)

    print("[launcher] The simulations have been executed succesfully.")
# %%
# =============================================================================
# LANZAR LA SIMULACIÓN
# =============================================================================
"""
Este bloque final lanza la simulación. Cuando se ejecuta un script de manera 
directa, la variable especial __name__ toma el valor "__main__". 
if __name__ == "__main__" evita que el código se ejecute si se importan 
funciones de este script en otro, facilitando la reutilización de código
"""
if __name__ == "__main__":
    main()



"""
EL FLUJO COMPLETO:
    
python launcher.py
        │
        ▼
Se ejecutan los imports
        │
        ▼
Se definen constantes
        │
        ▼
Se definen funciones
        │
        ▼
Se alcanza:
if __name__ == "__main__":
        │
        ▼
main()
        │
        ▼
_read_inputs()
        │
        ▼
pd.read_excel("inputs.xlsx", sheet_name="Inputs", header=3)
        │
        ▼
Se eliminan filas completamente vacías
        │
        ▼
Se selecciona inputs_df.iloc[0]
        │
        ▼
run_simulation(row)
        │
        ├── Lee mecanismo
        ├── Comprueba que existe
        ├── Interpreta Simulate soot
        ├── Interpreta Plots
        ├── Calcula mdot
        ├── Construye common_args
        │
        ├── Si soot = YES:
        │      └── Interpreta precursors
        │      └── simulate_flowreactor_soot(...)
        │
        └── Si soot = NO:
               └── simulate_flowreactor_nosoot(...)
        │
        ▼
Si Plots = YES:
        └── make_plots(...)
        │
        ▼
Se imprime mensaje en la consola
"""