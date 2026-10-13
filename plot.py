import os
import re
import pandas as pd
import matplotlib
matplotlib.use("Agg")   # backend sin interfaz gráfica (necesario para generar
                        # imágenes en un entorno sin pantalla)
import matplotlib.pyplot as plt


# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================

def _plots_dir_for(file_name):
    """
    Crea (si hace falta) una carpeta 'plots' junto al archivo de resultados
    xlsx, y devuelve su ruta.
    """
    base_dir = os.path.dirname(file_name) or "."
    plots_dir = os.path.join(base_dir, "plots")
    os.makedirs(plots_dir, exist_ok=True) # exist_ok comprueba si ya existe el directorio
    return plots_dir


def _savefig(fig, plots_dir, base_name, suffix):
    """
    Guarda una figura como .png, sustituyendo cualquier carácter no válido
    para nombres de archivo por un guion bajo.
    """
    # Sustitución de caracteres no válidos por "_"
    safe_base = re.sub(r'[^A-Za-z0-9_.-]', '_', base_name)
    path = os.path.join(plots_dir, f"{safe_base}_{suffix}.png")
    # GUARDAR LA FIGURA
    # resolución 150 dpi y ajuste del área para evitar espacios innecesarios alrededor
    fig.savefig(path, dpi=150, bbox_inches="tight")
    # Cierre de la figura para no mantenerlas en la memoria
    plt.close(fig)
    return path


# =============================================================================
# FUNCIÓN PRINCIPAL
# =============================================================================

def make_plots(file_name, sheet_name, simulate_soot=False):
    """
    Genera las gráficas principales de una simulación ya guardada en el
    archivo xlsx `file_name`, hoja `sheet_name`, y las guarda como .png en
    una carpeta 'plots' junto al archivo de resultados.

    Si `simulate_soot` es True, además intenta leer la hoja de PSD
    correspondiente (nombrada "PSD_<sheet_name>", truncada a 31
    caracteres como hace simulate_flowreactor_soot.py) y genera también la
    gráfica de distribución de tamaño de partícula. Si esa hoja no existe
    (por ejemplo, porque se usó el modelo "Monodisperse", que no genera
    PSD), esa gráfica simplemente se omite sin dar error.

    Devuelve la lista de rutas de las imágenes creadas.
    """
    # Lectura del Excel y almacenamiento de los resutados en un DataFrame
    df = pd.read_excel(file_name, sheet_name=sheet_name)
    # Creación de la carpeta almacén
    plots_dir = _plots_dir_for(file_name)
    created_files = []
    # Base del nombre del gráfico, que consiste en el nombre del archivo (quitando
    # la ruta y la entensión) concatenado con el nombre de la hoja
    base_name = f"{os.path.basename(file_name).removesuffix('.xlsx')}_{sheet_name}"
    
    # -------------------------------------------------------------------
    # Gráfica 1: fracción molar de CH4 y H2 frente al tiempo de residencia
    # -------------------------------------------------------------------
    if {"t[s]", "CH4", "H2"}.issubset(df.columns):
        fig, ax = plt.subplots()
        ax.plot(df["t[s]"], df["CH4"], label=r"$\mathrm{CH_4}$")
        ax.plot(df["t[s]"], df["H2"], label=r"$\mathrm{H_2}$")
        ax.set_xlabel("t [s]")
        ax.set_ylabel("Mole fraction [-]")
        ax.set_title(r"$\mathrm{CH_4}$ & $\mathrm{H_2}$ mole fraction vs time")
        ax.legend()
        created_files.append(_savefig(fig, plots_dir, base_name, "x_vs_t"))

    # -------------------------------------------------------------------
    # Gráfica 2: fracción molar de CH4 y H2 frente a la posición axial
    # -------------------------------------------------------------------
    if {"z[m]", "CH4", "H2"}.issubset(df.columns):
        fig, ax = plt.subplots()
        ax.plot(df["z[m]"], df["CH4"], label=r"$\mathrm{CH_4}$")
        ax.plot(df["z[m]"], df["H2"], label=r"$\mathrm{H_2}$")
        ax.set_xlabel("z [m]")
        ax.set_ylabel("Mole fraction [-]")
        ax.set_title(r"$\mathrm{CH_4}$ & $\mathrm{H_2}$ mole fraction vs reactor length")
        ax.legend()
        created_files.append(_savefig(fig, plots_dir, base_name, "x_vs_z"))

    if simulate_soot:
        # -----------------------------------------------------------------
        # Gráfica 3: evolución del rendimiento a hollín (carbon yield)
        # -----------------------------------------------------------------
        if {"z[m]", "carbon_yield[-]"}.issubset(df.columns):
            fig, ax = plt.subplots()
            ax.plot(df["z[m]"], df["carbon_yield[-]"])
            ax.set_xlabel("z [m]")
            ax.set_ylabel("Carbon yield [-]")
            ax.set_title("Soot carbon yield along the reactor")
            created_files.append(_savefig(fig, plots_dir, base_name, "carbon_yield_vs_z"))

        # -----------------------------------------------------------------
        # Gráfica 4: distribución de tamaño de partícula (PSD)
        #
        # Solo existe si se usó el modelo "Sectional" (con "Monodisperse"
        # no se genera la hoja PSD_..., así que aquí simplemente no se
        # crea esta gráfica).
        # -----------------------------------------------------------------
        # La hoja de Excel tiene una limitación de 31 caracteres
        psd_sheet_name = f"PSD_{sheet_name}"[:31]
        
        # Comprueba si la hoja PSD existe. Si se ha elegido el modelo Monodisperse
        # esta hoja no existirá, dejando la variable vacía.
        try:
            df_psd = pd.read_excel(file_name, sheet_name=psd_sheet_name)
        except ValueError:
            df_psd = None  # la hoja no existe
        
        # Si existe la hoja PSD y las columnas indicadas, se crea el gráfico
        if df_psd is not None and {"d_m_sec[nm]", "N_agg_sec[#/cm3]"}.issubset(df_psd.columns):
            fig, ax = plt.subplots()
            ax.plot(df_psd["d_m_sec[nm]"], df_psd["N_agg_sec[#/cm3]"])
            ax.set_xscale("log")
            ax.set_yscale("log")
            ax.set_ylim(1, None)
            ax.set_xlabel(r"$\mathrm{d_m}$ [nm]")
            ax.set_ylabel(r"$\mathrm{N}_{\mathrm{agg}}\ [\#/\mathrm{cm}^{3}]$")
            ax.set_title("Soot particle size distribution")
            created_files.append(_savefig(fig, plots_dir, base_name, "PSD"))
            
    print(f"[plot] {len(created_files)} plot(s) saved in '{plots_dir}'.")
    return created_files