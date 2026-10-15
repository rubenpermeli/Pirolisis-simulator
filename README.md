# Fuel Pyrolysis PFR Simulation Environment

An Excel-driven simulation environment for fuel pyrolysis in an isothermal plug flow reactor (PFR), built on [Cantera](https://cantera.org) and [Omnisoot](https://pypi.org/project/omnisoot/). The user describes the operating conditions in a spreadsheet, runs a single script, and obtains an Excel file with the axial profiles of the reactor and, optionally, PNG plots. No Python programming is required to use it.

The environment offers two simulation engines behind the same interface. The first one couples Cantera with Omnisoot to include soot formation, with a choice of particle dynamics model (monodisperse or sectional) and of PAH growth model. The second one uses Cantera alone and reports the gas-phase chemistry without any soot model. Switching between them is a matter of selecting `YES` or `NO` in a single cell of the input file.

## Contents

- [Repository structure](#repository-structure)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Input file](#input-file)
- [Outputs](#outputs)
- [How it works](#how-it-works)
- [Limitations](#limitations)
- [Troubleshooting](#troubleshooting)
- [Acknowledgements and references](#acknowledgements-and-references)

## Repository structure

```
.
├── launcher.py                      # Entry point: reads inputs.xlsx and runs the selected engine
├── simulate_flowreactor_soot.py     # Cantera + Omnisoot engine (with soot modelling)
├── simulate_flowreactor_nosoot.py   # Cantera-only engine (no soot)
├── plot.py                          # PNG plot generation from a results file
├── inputs.xlsx                      # Input spreadsheet (Instructions, Inputs and DB sheets)
└── data/                            # Chemical mechanisms in Cantera YAML format
```

The `data/` folder must contain the mechanism files that you intend to use. There are some default chemical mechanisms for the simulation environment located in the folder. However, additional mechanisms can be added inside the `data/` folder to be used.

## Installation

The code was developed and tested on Windows with Python 3.13.9, Cantera 3.2.0 and Omnisoot 0.2.10. It has not been verified on Linux or macOS.

You can work with either a plain Python installation or with Anaconda. In both cases, start by getting a local copy of the project, either with Git or by downloading the files manually.

### Getting the code

If you have [Git](https://git-scm.com/downloads) installed, the simplest way is to clone the repository and move into the project folder:

```bash
git clone https://github.com/rubenpermeli/pyrolysis-simulator.git
cd pyrolysis-simulator
```

If you prefer not to use Git, you can download the files manually. On the main page of the repository, click the green *Code* button and choose *Download ZIP*. Once the download has finished, extract the archive in a location of your choice. 

From this point on, the instructions are the same for both ways of getting the code. All the paths used by the scripts are relative to the project folder, so the terminal must be located in that folder whenever the environment is installed or run. If you downloaded the files manually, open a terminal and move into the folder with `cd`, giving its full path (for example, `cd C:\Users\<your-user>\pyrolysis-simulator` on Windows).

### Option A: Python and terminal

Install Python from [python.org](https://www.python.org/downloads/). On Windows, make sure to tick *Add python.exe to PATH* in the installer. 

### Option B: Anaconda

Install [Anaconda](https://www.anaconda.com/download), which already includes Python, the conda environment manager and the Spyder editor. Then create and activate an environment that contains Spyder, so that it can later be launched with all the dependencies available:

```bash
conda create -n pirolisis python=3.13.9 spyder
conda activate pirolisis
```

### Python dependencies

Install the libraries with `pip`, regardless of the option chosen above:

```bash
pip install cantera omnisoot numpy pandas matplotlib
```

To verify the installation, run the following command. It should print all versions without any error:

```bash
python -c "import cantera, omnisoot, numpy, pandas, openpyxl, matplotlib; print(cantera.__version__, omnisoot.__version__, numpy.__version__, pandas.__version__, matplotlib.__version__)"
```

## Quick start

Open `inputs.xlsx`, fill in a data row of the `Inputs` sheet (e.g., row 5), save the file and close it. Then run the launcher from the project folder:

```bash
python launcher.py
```

If you prefer a graphical interface, launch Spyder from the `pirolisis` environment (through Anaconda Navigator, or by typing `spyder` in a terminal where the environment is active), open `launcher.py`, check that the working directory is the project folder, and press `F5`.

As an example, the following row simulates pure methane at 900 °C (1173.15 K) and atmospheric pressure in a 20 cm long, 15 mm diameter reactor fed with 30 mL/min (5·10⁻⁷ m³/s):

| Pressure [Pa] | Temperature [K] | Reactor length [m] | Reactor diameter [m] | Volumetric flow rate [m3/s] | Inlet composition | Chemical mechanism | Simulate soot | Particle dynamic model | PAH growth model | Add/modify precursors | Precursors | Output file name | Excel sheet name | Plots |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 101325 | 1173.15 | 0.2 | 0.015 | 5e-7 | CH4:1 | CRECK_SOOT | YES | Sectional | ReactiveDimerization | NO |   | CH4_pyrolysis_CRECK_SOOT | T1173.15K | YES |

## Input file

The `Inputs` sheet of `inputs.xlsx` has one column per parameter, and the headers must not be renamed because the Python reader looks them up literally. The `DB` sheet holds the options of the drop-down menus and should not be modified either. Columns marked with an asterisk are mandatory.

| Column | Description |
|---|---|
| Pressure [Pa] * | Constant pressure of the reactor. |
| Temperature [K] * | Reactor temperature, uniform along the whole length. |
| Reactor length [m] * | Length of the reactor. |
| Reactor diameter [m] * | Internal diameter, used to obtain the cross-sectional area. |
| Mass flow rate [kg/s] | Total inlet mass flow rate. Fill this **or** the volumetric flow rate, never both. |
| Volumetric flow rate [m3/s] | Inlet volumetric flow rate, converted internally to mass flow rate. |
| Inlet composition * | Mole fractions in Cantera string format, for example `CH4:1` or `CH4:1, H2:2`. |
| Chemical mechanism * | One of `CRECK`, `CRECK_SOOT`, `Caltech`, `KAUST`, `C3Mech`, `ITV`. |
| Simulate soot * | `YES` runs the Omnisoot engine, `NO` runs the Cantera-only engine. |
| Particle dynamic model | `Monodisperse` or `Sectional`. Only used when soot is simulated. |
| PAH growth model | `ReactiveDimerization`, `DimerCoalescence`, `EBridgeModified` or `IrreversibleDimerization`. Only used when soot is simulated. |
| Add/modify precursors| `YES` to add precursor manually, `NO` to use default precursors. |
| Precursors | Precursors in Omnisoot string format. Only used when Add/modify precursors = `YES` . |
| Output file name | Name of the results `.xlsx` file. Defaults to `sim_results.xlsx` if left empty. |
| Excel sheet name | Name of the sheet that stores the results. Invalid characters are replaced and the name is cut to 31 characters. |
| Plots | `YES` generates PNG plots next to the results file. |


## Outputs

Results are written as Excel workbooks. Simulations without soot are saved in `results/NoSoot/`, whereas simulations with soot are saved in `results/<particle model>/<PAH growth model>/`. The file and sheet names are the ones given in the input file. If the workbook already exists, the new sheet is appended, so several simulations can be accumulated in one file; reusing a sheet name overwrites that sheet. Close the workbook in Excel before running a simulation that writes to it, otherwise the operating system will deny write access.

The main sheet contains one row per saved axial position, with residence time `t[s]`, axial position `z[m]`, temperature, density, mean molecular weight, velocity and the mole fraction of every species in the mechanism. Simulations with soot add the soot variables, among them the aggregate and primary particle number concentrations, the characteristic diameters (`d_p`, `d_m`, `d_g`, `d_v`), the number of primary particles per aggregate, soot mass and volume fraction, specific surface area, the carbon yield, and the contribution of each formation pathway (inception, coagulation, PAH adsorption and surface growth).

With the `Sectional` model, an additional sheet named `PSD_<sheet name>` stores the particle size distribution at the reactor outlet: the mobility diameter of each size section and the corresponding concentration of aggregates and primary particles, in mol/kg and in particles per cm³.

When plots are requested, a `plots/` folder is created next to the results file. It contains the mole fractions of CH₄ and H₂ against residence time and against reactor length. Simulations with soot also produce the evolution of the soot carbon yield along the reactor and, for the sectional model, the particle size distribution on logarithmic axes.

## How it works

`launcher.py` reads the data row of the `Inputs` sheet, validates the mandatory fields with explicit error messages, resolves the inlet mass flow rate, and calls the engine selected by the `Simulate soot` cell. Both engines receive exactly the same arguments, apart from the soot-specific models, so that their behaviour and output format are consistent. If plots are requested, `plot.py` is then called on the generated workbook, which means it can also be reused on its own with an existing results file.

The Omnisoot engine uses the `PlugFlowReactor` class with a fixed temperature profile defined by two points at the same temperature. The soot precursors (PAH species) depend on the mechanism, because species names differ from one mechanism to another.

The Cantera-only engine approximates the PFR as a chain of 500 ideal gas reactors with the energy equation switched off, each one integrated to steady state and feeding the next. The number of reactors is a numerical parameter (`N_STEPS` in `simulate_flowreactor_nosoot.py`), not a user input.

## Limitations

The reactor is isothermal, with a uniform temperature along its length. The soot model in the installed Omnisoot version does not include deposition of soot on the reactor walls, so all the soot formed is accounted for as remaining suspended in the gas stream and leaving through the outlet; the model cannot distinguish between soot collected on the walls and soot leaving with the gas. The particle size distribution is only available with the `Sectional` model and is extracted at the outlet only. 

## Troubleshooting

Most errors explain themselves in the message printed by the launcher: a mandatory cell left empty is reported by its column name, and filling both flow rate columns or neither of them is rejected. A `ModuleNotFoundError` usually means that the environment is not active, or that the editor is using a different Python interpreter from the one where the libraries were installed. A `PermissionError` when saving results almost always means that the results workbook is open in Excel.

## Acknowledgements and references

This project builds on Cantera and Omnisoot, and results obtained with it should cite them. Omnisoot is described in *Omnisoot: an object-oriented process design package for gas-phase synthesis of carbonaceous nanoparticles* ([arXiv:2507.10879](https://arxiv.org/abs/2507.10879)). For Cantera, please follow the citation guidance on the [Cantera website](https://cantera.org). The chemical mechanisms in `data/` belong to their respective authors and should be cited accordingly.
