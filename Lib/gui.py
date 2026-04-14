""" This code was developed with assistance from ChatGPT (OpenAI, 2025)

    Icons by Freepik:
    https://www.freepik.com/icon/exit_3094700
    https://www.freepik.com/icon/log_1960087
"""
import os
import tkinter as tk
from tkinter import ttk, font, filedialog, Menu
import numpy as np
from typing import List
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D

import Lib.config as cfg
import Lib.files as files
import Lib.logger as logger
from Lib.analysis import SternVolmerData

"""Base class for all frames, with access to the controller."""
class BaseFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.create_widgets()

    def create_widgets(self):
        """To be implemented in subclasses."""
        pass

"""Home page frame displaying experiment workflow controls"""
class HomePage(BaseFrame):
    def create_widgets(self):
        button_colors = cfg.guiColorScheme["buttons"]["btnSpectrometerLED"]
        self.btnSpectrometerLED = tk.Button(self, text="Spectrometer and LED", width=25, command=self.btnSpectrometer_click,
                                            bg=button_colors["bg"], fg=button_colors["fg"], state="disabled")
        self.btnSpectrometerLED.pack(pady=5)
        button_colors = cfg.guiColorScheme["buttons"]["btnBaseline"]
        self.btnBaseline = tk.Button(self, text="Record baseline", width=25, command=self.btnBaseline_click,
                                     bg=button_colors["bg"], fg=button_colors["fg"], state="disabled")
        self.btnBaseline.pack(pady=5)
        button_colors = cfg.guiColorScheme["buttons"]["btnLoadExperiment"]
        self.btnLoadExperiment = tk.Button(self, text="Load experiment", width=25, command=self.btnLoadExperiment_click,
                                           bg=button_colors["bg"], fg=button_colors["fg"], state="disabled")
        self.btnLoadExperiment.pack(pady=5)
        self.labelExperimentFilename = tk.Label(self, text="No experiment loaded", font='Arial 10 bold')
        self.labelExperimentFilename.pack(pady=5)
        button_colors = cfg.guiColorScheme["buttons"]["btnPumps"]
        self.btnPumps = tk.Button(self, text="Prime pumps", width=25, command=self.btnPumps_click,
                                  bg=button_colors["bg"], fg=button_colors["fg"], state="disabled")
        self.btnPumps.pack(pady=5)
        button_colors = cfg.guiColorScheme["buttons"]["btnStartPauseExperiment"]
        self.btnStartPauseExperiment = tk.Button(self, text="Start experiment", width=25, command=self.btnStartPauseExperiment_click,
                                           bg=button_colors["bg"], fg=button_colors["fg"], state="disabled")
        self.btnStartPauseExperiment.pack(pady=5)
        button_colors = cfg.guiColorScheme["buttons"]["btnStopExperiment"]
        self.btnStopExperiment = tk.Button(self, text="Stop experiment", width=25, command=self.btnStopExperiment_click,
                                           bg=button_colors["bg"], fg=button_colors["fg"], state="disabled")
        self.btnStopExperiment.pack(pady=5)
        button_colors = cfg.guiColorScheme["buttons"]["btnAnalysisParameters"]
        self.btnAnalysisParameters = tk.Button(self, text="Analysis parameters", width=25, command=self.btnAnalysisParameters_click,
                                           bg=button_colors["bg"], fg=button_colors["fg"], state="disabled")
        self.btnAnalysisParameters.pack(pady=5)
        if cfg.LOG_WINDOW in cfg.LOGGER_MODE:
            button_colors = cfg.guiColorScheme["buttons"]["btnViewLog"]
            self.btnViewLog = tk.Button(self, text="Open log window", width=25, command=self.btnOpenLogWindow_click,
                                        bg=button_colors["bg"], fg=button_colors["fg"])
            self.btnViewLog.pack(pady=5)

    def toggle_spectrometer_buttons(self, btns_state):
        self.btnBaseline.config(state="normal" if btns_state else "disabled")
        self.btnSpectrometerLED.config(state="normal" if btns_state else "disabled")
        self.btnLoadExperiment.config(state="normal" if btns_state else "disabled")
        self.labelExperimentFilename.config(state="normal" if btns_state else "disabled")

    def toggle_experiment_buttons(self, btns_state):
        self.btnStartPauseExperiment.config(state="normal" if btns_state else "disabled")
        # self.btnStopExperiment.config(state="normal" if btns_state else "disabled")

    def btnBaseline_click(self):
        """Calls the spectrometer module function to collect the baseline."""
        self.controller.data_reader.record_background()
        # self.controller.update_status("New baseline has been recorded")

    def btnPumps_click(self):
        """Open the settings popup window."""
        self.controller.data_reader.pause()
        self.controller.update_status("Setting the syringe pump parameters and priming...")
        self.controller.open_pump_settings_window()

    def btnSpectrometer_click(self):
        """Navigate to the Data Page."""
        if not cfg.EXPERIMENT_IS_RUNNING: # to allow on-the-fly changes of spectrometer settings for now
            self.controller.data_reader.restart()
        self.controller.update_status("Changing spectrometer settings...")
        self.controller.show_frame(SpectrometerPage)

    def btnLoadExperiment_click(self):
        """Loads the experiment data from the file."""
        self.controller.data_reader.pause()
        self.controller.update_status("Opening a .CSV file with an experiment program...")
        files.experimentFilePath = filedialog.askopenfilename(filetypes=[(".CSV (comma-separated values)", "*.csv")])
        if files.experimentFilePath:
            file_name = os.path.basename(files.experimentFilePath)
            files.experimentFileName = file_name
            displayed_file_name = files.truncate_long_filename(file_name, 30)
            CSV_parsing_error = files.parseExperimentCSV(files.experimentFilePath)
            if CSV_parsing_error:
                font_strikethrough = font.Font(family="Arial", size=10, weight="bold", overstrike=True)
                self.labelExperimentFilename.config(text=displayed_file_name, font=font_strikethrough, fg="red")
                self.controller.update_status(f"Error while reading {file_name}: not an experiment program!", "red")
                self.controller.logger.add_entry("gui", f"Error while reading {file_name}: {CSV_parsing_error}", error=True)
                self.controller.data_reader.resume()
                # disable btnPumps and btnAnalysisParameters
                self.btnPumps.config(state="disabled")
                self.btnAnalysisParameters.config(state="disabled")
            else:
                self.labelExperimentFilename.config(text=displayed_file_name, font='Arial 10 bold', fg="green4")
                self.controller.update_status(f"Loaded an experiment from {file_name}")
                self.controller.logger.add_entry("gui", f"Loaded an experiment {files.experimentData['Name']} from {file_name}")
                # loading syringe settings and priming values
                # enable btnPumps and btnAnalysisParameters
                self.btnPumps.config(state="normal")
                self.btnAnalysisParameters.config(state="normal")
            # print(f" *>>>>> cfg.EXPERIMENT_LOADED_OK {cfg.EXPERIMENT_LOADED_OK}")
            # self.controller.update_plot()
            self.controller.update_plot_flag = True
            # self.controller.data_reader.restart() # only keep for now for debug purposes
            self.btnStopExperiment.config(state="normal")
        else:
            self.controller.data_reader.resume()

    def btnStartPauseExperiment_click(self):
        if cfg.EXPERIMENT_IS_RUNNING:
            if cfg.EXPERIMENT_IS_PAUSED:
                self.controller.data_reader.resume()
                self.controller.pump_controller.resume_sequence()
            else:
                self.controller.data_reader.pause()
                self.controller.pump_controller.pause_sequence()
        else:
            # create a new output 2D spectrum data file
            spectrum2D_X_header = self.controller.data_reader.get("wavelengths")
            spectrum2D_file_path = files.spectrum2DFileCreate(spectrum2D_X_header)
            if spectrum2D_file_path:
                self.controller.logger.add_entry("files", f"Created a 2D spectrum file '{spectrum2D_file_path}")
            else:
                self.controller.logger.add_entry("files",
                                                 f"Could not create 2D spectrum file '{spectrum2D_file_path}, no spectrum data will be saved.",
                                                 error=True)
            # create a new emission over time data file
            emissions_file_path = files.emissionDataFileCreate()
            if emissions_file_path:
                self.controller.logger.add_entry("files", f"Created fluorescence emission file '{emissions_file_path}")
            else:
                self.controller.logger.add_entry("files",
                                                 f"Could not create fluorescence emission file '{emissions_file_path}, no emission data over time will be saved.",
                                                 error=True)
            # run the experiment program
            self.controller.data_reader.restart()
            self.controller.pump_controller.run_experiment_program()
            cfg.EXPERIMENT_IS_RUNNING = True

    def btnStopExperiment_click(self):
        cfg.EXPERIMENT_IS_RUNNING = False
        cfg.EXPERIMENT_IS_PAUSED = False
        self.controller.data_reader.restart()
        self.controller.pump_controller.abort_sequence()
        files.spectrum2DFileClose()
        files.emissionDataFileClose()

    def btnAnalysisParameters_click(self):
        self.controller.update_status("Changing analysis parameters...")
        cfg.SINGLE_PASS_ANALYSIS = True
        self.controller.show_frame(AnalysisParametersPage)

    def btnOpenLogWindow_click(self):
        self.controller.log_window.show()


class MessageBoxConfirmExitWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Exit")
        self._icon_exit = tk.PhotoImage(file=f"{cfg.RESOURCES_DIR}/Exit.png")
        self.iconphoto(False, self._icon_exit)
        
        # center the message box over main application window
        msgbox_width = 190
        msgbox_height = 90
        x = parent.winfo_x() + parent.winfo_width() // 2
        y = parent.winfo_y() + parent.winfo_height() // 2
        self.geometry(f"{msgbox_width}x{msgbox_height}+{x - msgbox_width // 2}+{y - msgbox_height // 2}")

        self.update_idletasks()
        self.transient(parent)
        self.grab_set()

        label_closeapp = tk.Label(self, text="Close the application?")
        label_closeapp.pack(pady=10)

        button_frame = tk.Frame(self)
        button_frame.pack()

        def force_close_app():
            # TODO: make sure this is done appropriately with regards to the data!
            parent.logger.add_entry("gui", "->| Closing the main application")
            # switching off LED and close LED controller serial connection (UART6) 
            parent.LED_controller.LED_brightness_percent = 0
            parent.LED_controller.detach()
            # closing serial connections (UART3...UART5) using pump controller
            parent.pump_controller.close()
            # closing the files that may still be open
            files.spectrum2DFileClose()
            # closing the loggers
            if cfg.LOG_WINDOW in cfg.LOGGER_MODE:
                parent.log_window.close()  # closing log window here
            if cfg.LOG_FILE in cfg.LOGGER_MODE:
                parent.logger.logger_file.close()  # closing the logger file
            if cfg.LOG_UART in cfg.LOGGER_MODE:
                parent.logger.logger_uart.close_uart()  # closing the UART used for logging
            parent.destroy()
            exit()

        yes_button = tk.Button(button_frame, text="Yes", width=9, command=force_close_app)
        yes_button.pack(side=tk.LEFT, padx=5)

        no_button = tk.Button(button_frame, text="No",  width=9, command=self.destroy)
        no_button.pack(side=tk.RIGHT, padx=5)

class SVPlotWindow(tk.Toplevel):
    def __init__(self, parent, plot_title: str):
        super().__init__(parent)
        self.title("Stern-Volmer analysis plot")

        # Center the plot window over the parent
        plot_window_width = 600
        plot_window_height = 400
        x = parent.winfo_x() + 20
        y = parent.winfo_y() + 20
        self.geometry(f"{plot_window_width}x{plot_window_height}+{x}+{y}")

        self.update_idletasks()  # Ensures geometry info is up-to-date before layout
        self.transient(parent)   # Keeps this window on top and minimizes with parent
        self.grab_set()          # Makes this window modal (disables interaction with parent)

        self._create_plot(files.experimentSVdataResult, plot_title)

    def _create_plot(self, sv_data: List[SternVolmerData], title: str):
        x_vals = [d.conc_quencher_M * 1000 for d in sv_data]  # mmol/L
        y_vals = [d.ratio_I0_I for d in sv_data]
        y_errs = [d.ser_I0_I for d in sv_data]

        fig, ax = plt.subplots(figsize=(6, 4), dpi=100)
        ax.errorbar(x_vals, y_vals, yerr=y_errs, fmt='o', capsize=5, label='Data')

        # Fit line: y = m*x + b
        coeffs = np.polyfit(x_vals, y_vals, deg=1)
        trend_fn = np.poly1d(coeffs)
        x_fit = np.linspace(min(x_vals), max(x_vals), 100)
        y_fit = trend_fn(x_fit)
        ax.plot(x_fit, y_fit, 'r--', label=f'Fit: y = {coeffs[0]:.3e}x + {coeffs[1]:.3f}')

        # Compute R² and residuals
        y_pred = trend_fn(x_vals)
        residuals = np.array(y_vals) - y_pred
        ss_res = np.sum(residuals ** 2)
        ss_tot = np.sum((np.array(y_vals) - np.mean(y_vals)) ** 2)
        r_squared = 1 - (ss_res / ss_tot)

        # Add text box with stats
        # R^2 shows how well the linear model fits the data (1.0 = 100% fit)
        # SSR is the sum of squared residuals, useful for assessing error magnitude
        stats_text = f"$R^2$ = {r_squared:.4f}\nSSR = {ss_res:.4f}"
        ax.text(0.05, 0.95, stats_text, transform=ax.transAxes,
                fontsize=10, verticalalignment='top', bbox=dict(boxstyle="round", facecolor="white", alpha=0.6))

        # Formatting and plotting
        ax.set_xlabel("[Quencher], mmol/L")
        ax.set_ylabel("I0/I")
        ax.set_title(title)
        ax.grid(True)
        ax.legend()

        canvas = FigureCanvasTkAgg(fig, master=self)
        canvas.draw()
        canvas_widget = canvas.get_tk_widget()
        canvas_widget.pack(fill=tk.BOTH, expand=True)

        # Adding right-click save option
        def save_figure():
            filepath = filedialog.asksaveasfilename(
                defaultextension=".png",
                filetypes=[("PNG Image", "*.png"), ("All Files", "*.*")],
                title="Save Plot As..."
            )
            if filepath:
                fig.savefig(filepath, dpi=cfg.GUI_SAVEIMAGE_OUTPUT_DPI)

        def show_context_menu(event):
            menu = Menu(self, tearoff=0)
            menu.add_command(label="Save As...", command=save_figure)
            menu.tk_popup(event.x_root, event.y_root)

        # Binding right-click menu
        canvas_widget.bind("<Button-3>", show_context_menu)

class PumpSettingsWindow(tk.Toplevel):
    """Popup window to control pump settings"""
    def __init__(self, controller):
        super().__init__(controller)
        self.controller = controller
        self.title("Syringe pump settings")
        self._icon_pump = tk.PhotoImage(file=f"{cfg.RESOURCES_DIR}/Pump.png")
        self.iconphoto(False, self._icon_pump)
        
        self.geometry(f"{cfg.PUMPSETTINGSWINDOW_SIZE_WIDTH}x{cfg.PUMPSETTINGSWINDOW_SIZE_HEIGHT}+{cfg.MAINWINDOW_POSITION_X + 50}+{cfg.MAINWINDOW_POSITION_Y + 50}")
        self.resizable(False, False)
        self.syringeparameter_entries = { "SyringeVolume": [], "PrimeVolume": [], "PrimeFlowrate": [] }  # dictionary to store entry widgets for syringe parameters
        self.create_widgets()
        self.transient(self.controller)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def create_widgets(self):
        # Table Layout
        button_colors = cfg.guiColorScheme["buttons"]["btnPrimePumps"]
        self.btnPrimePumps = tk.Button(self, text="Prime all", width=9, command=self.btnPrimePumps_click,
                                       bg=button_colors["bg"], fg=button_colors["fg"])
        self.btnPrimePumps.grid(row=0, column=0, padx=5, pady=5)
        tk.Label(self, text="Syringe volume, mL").grid(row=0, column=1, padx=5, pady=5)
        tk.Label(self, text="Prime volume, mL").grid(row=0, column=2, padx=5, pady=5)
        tk.Label(self, text="Flow rate, mL/min").grid(row=0, column=3, padx=5, pady=5)
        # parsing the controller.shared_data["pumps"]
        for i, (pump_name, pump_data) in enumerate(self.controller.shared_data["pumps"].items()):
            # label for each pump in the table
            tk.Label(self, text=pump_data['label']+':').grid(row=i + 2, column=0, padx=5, pady=5, sticky='w')
            # iterate over syringe parameters
            for j, parameter in enumerate(self.syringeparameter_entries):
                # create an Entry widget for the current parameter
                entry = tk.Entry(self, textvariable=pump_data[parameter], width=10)
                # place the Entry widget in the grid, shifting by column index (j+1)
                entry.grid(row=i + 2, column=j + 1, padx=5, pady=5)
                # bind key release event and capture current row and parameter name
                entry.bind("<KeyRelease>", lambda event, row_index=i+1, parameter_name=parameter: self.check_input_value(event, row_index, parameter_name))
                # Store the entry in the respective parameter's list
                self.syringeparameter_entries[parameter].append(entry)

    def check_input_value(self, event, row_index, parameter_name):
        # Entry text color is changed to red if outside the limits
        # Only allow to use the syringes registered in SYRINGES_CSV_FILE
        entry = event.widget
        try:
            if parameter_name == "SyringeVolume":
                value = int(entry.get())
                syringe_registered = str(value) in files.syringesData
                entry.config(fg="black" if syringe_registered else "red") # check if syringe with this volume is registered
                if not syringe_registered:
                    self.controller.update_status(f"Unknown syringe volume (not in {cfg.SYRINGES_CSV_FILE}), cannot prime it", "red")
                    self.controller.logger.add_entry("gui", f"Pump settings: {value} mL syringe is not registered in {cfg.SYRINGES_CSV_FILE}")
                # trigger update for other parameters, if syringe volume was changed
                self.force_validate_dependent_parameters(row_index)
            else:
                value = float(entry.get())
                syringe_volume = self.syringeparameter_entries["SyringeVolume"][row_index - 1].get()
                if parameter_name == "PrimeVolume":
                    entry.config(fg="black" if 0 <= value <= int(syringe_volume) else "red") # allow zero values to skip priming individual pumps
                else: # parameter_name == "PrimeFlowrate"
                    max_flowrate = files.GetDefaultSyringeSettings(syringe_volume).get("Max flow rate (mL/min)")
                    entry.config(fg="black" if 0 < value <= float(max_flowrate) else "red")  # Max permissible prime flow rate is limited by max flow rate for this syringe
        except ValueError:
            entry.config(fg="red")
        self.allow_prime_if_all_input_values_good()

    def force_validate_dependent_parameters(self, row_index):
        # rechecks syringe parameter entries if syringe volume has been changed
        for parameter_name in ["PrimeVolume", "PrimeFlowrate"]:
            entry = self.syringeparameter_entries[parameter_name][row_index - 1]
            self.check_input_value(event=type('Event', (), {'widget': entry})(), row_index=row_index,
                                   parameter_name=parameter_name)

    def allow_prime_if_all_input_values_good(self):
        # enable or disable btnPrimePumps based on whether all settings in entries are correct
        for param_entries in self.syringeparameter_entries.values():
            for entry in param_entries:
                if entry.cget("fg") == "red":  # if any entry has red text, disable btnPrimePumps
                    self.btnPrimePumps.config(state="disabled")
                    self.controller.update_status("Correct the values highlighted in red", "red")
                    return
        # Enable btnPrimePumps if no red entries exist
        self.btnPrimePumps.config(state="normal")
        self.controller.update_status("All settings are within the limits, ready to prime")

    def record_priming_program(self):
        # syringe settings are all set, create a priming program
        # it is a sequence of 3 steps: Pump2 (DYE/CATALYST) -> Pump3 (QUENCHER) -> Pump1 (SOLVENT)
        # step_duration_Pump1 = self.controller.shared_data["pumps"]["UART3"]["PrimeVolume"].get() / self.controller.shared_data["pumps"]["UART3"]["PrimeFlowrate"].get() * 60
        # step_duration_Pump2 = self.controller.shared_data["pumps"]["UART4"]["PrimeVolume"].get() / self.controller.shared_data["pumps"]["UART4"]["PrimeFlowrate"].get() * 60
        # step_duration_Pump3 = self.controller.shared_data["pumps"]["UART5"]["PrimeVolume"].get() / self.controller.shared_data["pumps"]["UART5"]["PrimeFlowrate"].get() * 60
        # files.primingPumpProgram = [(step_duration_Pump2, 0.0, self.controller.shared_data["pumps"]["UART4"]["PrimeFlowrate"].get(), 0.0),
        #                            (step_duration_Pump3, 0.0, 0.0, self.controller.shared_data["pumps"]["UART5"]["PrimeFlowrate"].get()),
        #                            (step_duration_Pump1, self.controller.shared_data["pumps"]["UART3"]["PrimeFlowrate"].get(), 0.0, 0.0)]
        pumps = self.controller.shared_data["pumps"]
        files.primingPumpProgram.clear()
        files.primingPumpProgram.extend([
            (
                pump_number,
                pumps[cfg.PUMP_UARTS[pump_number]]["PrimeVolume"].get(),
                pumps[cfg.PUMP_UARTS[pump_number]]["PrimeFlowrate"].get()
            )
            for pump_number in cfg.PUMP_PRIMING_ORDER
        ])
        # print(files.primingPumpProgram)
        self.controller.logger.add_entry("gui", "Pumps priming program written")


    def btnPrimePumps_click(self):
        # TODO: now also needs some refactoring as to how the syringe diameters are stored
        self.record_priming_program()
        files.UpdateSyringeDiameters(self.controller.shared_data["pumps"]["UART3"]["SyringeVolume"].get(),
                                     self.controller.shared_data["pumps"]["UART4"]["SyringeVolume"].get(),
                                     self.controller.shared_data["pumps"]["UART5"]["SyringeVolume"].get())
        # self.controller.data_reader.run()
        self.controller.data_reader.restart()
        self.controller.pump_controller.prime_pumps()
        self.destroy()  # Close the window

    def on_close(self):
        """Function called when the settings window is closed."""
        self.controller.update_status("Pump settings have been updated")
        self.controller.data_reader.resume()
        self.destroy()  # Close the window

class SpectrometerPage(BaseFrame):
    """Frame for modifying scatter plot data."""
    def create_widgets(self):
        # Layout Grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        def update_ledIntensity_label(*args):
            ledIntensity_label.config(text=f"LED ({self.controller.shared_data['ledIntensityPWM'].get():.0f}%)")

        # Slider with label
        ledIntensity_label = tk.Label(self, text=f"LED ({self.controller.shared_data['ledIntensityPWM'].get():.0f}%)")
        ledIntensity_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.controller.shared_data["ledIntensityPWM"].trace_add("write", update_ledIntensity_label)
        self._user_dragging_slider = False
        self.ledIntensity_slider = ttk.Scale(self, from_=0, to=100, orient=tk.HORIZONTAL,
                               variable=self.controller.shared_data["ledIntensityPWM"], length=100)
        self.ledIntensity_slider.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        # Bind the press and release events of the slider - to ensure the value is updated only once its desired position is set by the user, which should override hardware updates
        self.ledIntensity_slider.bind("<ButtonPress-1>", self._on_slider_press)
        self.ledIntensity_slider.bind("<ButtonRelease-1>", self._on_slider_release)

        # Entry widgets with labels
        # TODO: unfold this properly or list all widgets explicitly - this looks really ugly!
        # currently variable 'i' is doing row number tracking
        for i, (spectrometer_datakey, spectrometer_datavalue) in enumerate(self.controller.shared_data["spectrometer"].items(), start=1):
            tk.Label(self, text=spectrometer_datakey).grid(row=i + 1, column=0, padx=5, pady=5, sticky='w')
            if isinstance(spectrometer_datavalue, tk.IntVar):
                # if data value can be altered by the user, use an Entry widget
                if spectrometer_datakey == "Average N spectra, N =":
                    self.averageNspectra_entry = tk.Entry(self, textvariable=spectrometer_datavalue, width=10)
                    self.averageNspectra_entry.grid(row=i + 1, column=1, padx=5, pady=5)
                elif spectrometer_datakey == "Integration time, \u03BCs":
                    self.integrationtime_entry = tk.Entry(self, textvariable=spectrometer_datavalue, width=10)
                    self.integrationtime_entry.grid(row=i + 1, column=1, padx=5, pady=5)
                elif spectrometer_datakey == "SMA boxcar, nm":
                    self.SMAboxcar_entry = tk.Entry(self, textvariable=spectrometer_datavalue, width=10)
                    self.SMAboxcar_entry.grid(row=i + 1, column=1, padx=5, pady=5)
                elif spectrometer_datakey == "Acquisition delay, ms":
                    self.acquisitiondelay_entry = tk.Entry(self, textvariable=spectrometer_datavalue, width=10)
                    self.acquisitiondelay_entry.grid(row=i + 1, column=1, padx=5, pady=5)
                else:
                    self.controller.logger.add_entry("gui", f"Unknown entry added to spectrometer settings ({spectrometer_datakey} : {spectrometer_datavalue})",
                                          error=True)
                    tk.Entry(self, textvariable=spectrometer_datavalue, width=10).grid(row=i + 1, column=1, padx=5, pady=5)
            else:
                # otherwise, use a Label widget
                tk.Label(self, textvariable=spectrometer_datavalue, fg="blue").grid(row=i + 1, column=1, padx=5, pady=5)

        # LabelFrame with inputs for detection window options
        self.detection_frame = tk.LabelFrame(self, text=" Emission detection options ", width=150, height=100)
        self.detection_frame.grid(row=i+2, column=0, padx=5, pady=10, columnspan=2, sticky="ew")

        # Radio Buttons
        self.singlewavelength_radio = tk.Radiobutton(self.detection_frame, text="Single wavelength at emission \u03BBmax", variable=self.controller.shared_data["emission_detection"]["detection_mode"],
                                                     value=cfg.EMISSIONDETECT_SINGLE_WAVELENGTH, command=self.toggle_detection_entries)
        self.singlewavelength_radio.pack(anchor=tk.W)

        self.integrationwindow_radio = tk.Radiobutton(self.detection_frame, text="Integrate over window", variable=self.controller.shared_data["emission_detection"]["detection_mode"],
                                                      value=cfg.EMISSIONDETECT_INTEGRATE_OVER_WINDOW, command=self.toggle_detection_entries)
        self.integrationwindow_radio.pack(anchor=tk.W)

        # Row for Min/Max inputs
        self.detection_Lmin_label = tk.Label(self.detection_frame, text="\u03BBmin:")
        self.detection_Lmin_label.pack(side=tk.LEFT, padx=2, pady=5)

        self.detection_Lmin_entry = tk.Entry(self.detection_frame, width=5, textvariable=self.controller.shared_data["emission_detection"]["window_min"])
        self.detection_Lmin_entry.pack(side=tk.LEFT, padx=2, pady=5)

        self.detection_Lmax_label = tk.Label(self.detection_frame, text="\u03BBmax:")
        self.detection_Lmax_label.pack(side=tk.LEFT, padx=2, pady=5)

        self.detection_Lmax_entry = tk.Entry(self.detection_frame, width=5, textvariable=self.controller.shared_data["emission_detection"]["window_max"])
        self.detection_Lmax_entry.pack(side=tk.LEFT, padx=2, pady=5)

        # Adding limit check highlighting for all Entry input values
        self.averageNspectra_entry.bind("<KeyRelease>",
                                       # lambda is used to pass additional parameters to validate_detection_limits
                                       lambda event: self.check_input_value(event, 1,
                                                                                    cfg.MAX_SPECTRA_PER_DATAPOINT))
        self.integrationtime_entry.bind("<KeyRelease>",
                                        # lambda is used to pass additional parameters to validate_detection_limits
                                        lambda event: self.check_input_value(event, cfg.INTEGRATION_TIME_US_MIN,
                                                                                     cfg.INTEGRATION_TIME_US_MAX))
        self.SMAboxcar_entry.bind("<KeyRelease>",
                                        # lambda is used to pass additional parameters to validate_detection_limits
                                        lambda event: self.check_input_value(event, 1,
                                                                                  cfg.MAX_BOXCAR_SIZE))
        self.acquisitiondelay_entry.bind("<KeyRelease>",
                                         # lambda is used to pass additional parameters to validate_detection_limits
                                         lambda event: self.check_input_value(event, cfg.MIN_ACQUISITION_DELAY_MS,
                                                                                   cfg.MAX_ACQUISITION_DELAY_MS))
        self.detection_Lmin_entry.bind("<KeyRelease>", # lambda is used to pass additional parameters to validate_detection_limits
                                       lambda event: self.check_input_value(event, cfg.WAVELENGTH_MIN,
                                                                                    cfg.WAVELENGTH_MAX))
        self.detection_Lmax_entry.bind("<KeyRelease>",
                                       lambda event: self.check_input_value(event, self.controller.shared_data["emission_detection"]["window_min"].get(),
                                                                                    cfg.WAVELENGTH_MAX))

        self.toggle_detection_entries()  # Ensure correct state on startup

        # Button to return to HomePage
        tk.Button(self, text="Update settings", command=self.btnUpdateSettings_click, width=20).grid(row=i + 3, column=0, padx=5, columnspan=2)
        tk.Button(self, text="Return", command=self.btnReturn_click, width=10).grid(row=i + 4, column=0, padx=5, pady=10, columnspan=2)

    def _on_slider_press(self, event):
        self._user_dragging_slider = True

    def _on_slider_release(self, event):
        self._user_dragging_slider = False
        value = self.ledIntensity_slider.get()
        rounded_value = round(float(value) / 5) * 5  # rounded to 5 to ensure the step size of 5
        cfg.LED_INTENSITY = rounded_value / 100
        self.controller.LED_controller.LED_brightness_percent = rounded_value

    def toggle_ledIntensity_slider(self, sliderEnabled: bool):
        if sliderEnabled:
            self.ledIntensity_slider.configure(state="normal")
        else:
            self.ledIntensity_slider.configure(state="disabled")

    def toggle_detection_entries(self):
        state = tk.NORMAL if self.controller.shared_data["emission_detection"]["detection_mode"].get() == cfg.EMISSIONDETECT_INTEGRATE_OVER_WINDOW else tk.DISABLED
        self.detection_Lmin_entry.config(state=state)
        self.detection_Lmax_entry.config(state=state)

    def check_input_value(self, event, min_allowed, max_allowed):
        # Entry text color is changed to red if outside the permissible limits or not integer
        entry = event.widget
        try:
            value = int(entry.get())
            if min_allowed <= value <= max_allowed:
                entry.config(fg="black")
            else:
                entry.config(fg="red")
        except ValueError:
            entry.config(fg="red")

    def update_input_value(self, input_entry, min_allowed, max_allowed, data_reader_var, controller_value):
        # Check if the value in input_entry is within permissible limits: min_allowed <= input_entry.get() <= max_allowed
        # If yes, update the data reader attribute data_reader_var with value from input_entry
        # If no, restore the corresponding parameter controller_value of the controller with the value from data_reader_var
        # returns True if the value was accepted (for additional post-update actions), False if not and previous value was reloaded
        result = False
        try:
            value_temp = int(input_entry.get())
            if min_allowed <= value_temp <= max_allowed:
                self.controller.data_reader.set(data_reader_var, value_temp)
                result = True
            else:
                controller_value.set(self.controller.data_reader.get(data_reader_var))
        except ValueError:
            controller_value.set(self.controller.data_reader.get(data_reader_var))
        input_entry.config(fg="black") # restore the color of input_entry text (if there was an error, it has been corrected)
        return result

    def btnUpdateSettings_click(self):
        """Check the entered values for validity.
           Update the corresponding variables in spectrometer.py with accepted values.
           Otherwise, replace the values in shared_data with those from spectrometer.py variables.
           Finally, navigate to the HomePage."""
        # checking averageNspectra_entry and setting NumOfSpectraPerDatapoint
        self.update_input_value(self.averageNspectra_entry, 1, cfg.MAX_SPECTRA_PER_DATAPOINT,
                                "NumOfSpectraPerDatapoint", self.controller.shared_data["spectrometer"]["Average N spectra, N ="])
        # checking integrationtime_entry and setting integration_time (also updating the spectrometer setting)
        if self.update_input_value(self.integrationtime_entry, cfg.INTEGRATION_TIME_US_MIN, cfg.INTEGRATION_TIME_US_MAX,
                                   "integration_time", self.controller.shared_data["spectrometer"]["Integration time, \u03BCs"]):
            self.controller.data_reader.update_integration_time() # post-update action
        # checking SMAboxcar_entry
        self.update_input_value(self.SMAboxcar_entry, 1, cfg.MAX_BOXCAR_SIZE,
                                "boxcarSMA", self.controller.shared_data["spectrometer"]["SMA boxcar, nm"])
        # checking acquisitiondelay_entry
        self.update_input_value(self.acquisitiondelay_entry, 0, cfg.MAX_ACQUISITION_DELAY_MS,
                                   "acquisition_delay", self.controller.shared_data["spectrometer"]["Acquisition delay, ms"])
        # checking the inputs of detection_frame and setting the variables for emission detection mode
        if self.controller.shared_data["emission_detection"]["detection_mode"].get() == cfg.EMISSIONDETECT_SINGLE_WAVELENGTH:
            self.controller.data_reader.EmissionDetectionMode = cfg.EMISSIONDETECT_SINGLE_WAVELENGTH
        else:
            self.update_input_value(self.detection_Lmin_entry, cfg.WAVELENGTH_MIN, cfg.WAVELENGTH_MAX,
                                   "detection_Lmin", self.controller.shared_data["emission_detection"]["window_min"])
            self.update_input_value(self.detection_Lmax_entry, self.controller.data_reader.detection_Lmin, cfg.WAVELENGTH_MAX,
                                    "detection_Lmax", self.controller.shared_data["emission_detection"]["window_max"])
            self.controller.data_reader.EmissionDetectionMode = cfg.EMISSIONDETECT_INTEGRATE_OVER_WINDOW
        # send the new value to LED controller
        # self.controller.LED_controller.LED_brightness_percent = self.controller.shared_data["ledIntensityPWM"].get()
        # confirm that the settings have been updated
        self.controller.update_status("Spectrometer and LED settings have been updated")

    def btnReturn_click(self):
        # return to displaying HomePage
        self.controller.show_frame(HomePage)

class AnalysisParametersPage(BaseFrame):
    """Frame for modifying scatter plot data."""
    def create_widgets(self):
        # Layout Grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # Entry widgets with labels
        # currently variable 'i' is doing row number tracking
        for i, (analysis_datakey, analysis_datavalue) in enumerate(self.controller.shared_data["analysis"].items(), start=1):
            tk.Label(self, text=analysis_datakey).grid(row=i + 1, column=0, padx=5, pady=5, sticky='w')
            if isinstance(analysis_datavalue, tk.IntVar):
                # if data value can be altered by the user, use an Entry widget
                if analysis_datakey == "Emission RMS tolerance, a.u.":
                    self.RMStolerance_entry = tk.Entry(self, textvariable=analysis_datavalue, width=10)
                    self.RMStolerance_entry.grid(row=i + 1, column=1, padx=5, pady=5)
                elif analysis_datakey == "Sliding window size, samples":
                    self.windowsize_entry = tk.Entry(self, textvariable=analysis_datavalue, width=10)
                    self.windowsize_entry.grid(row=i + 1, column=1, padx=5, pady=5)
                elif analysis_datakey == "Max # of outliers":
                    self.numofoutliers_entry = tk.Entry(self, textvariable=analysis_datavalue, width=10)
                    self.numofoutliers_entry.grid(row=i + 1, column=1, padx=5, pady=5)
                elif analysis_datakey == "Min step duration, samples":
                    self.stepduration_entry = tk.Entry(self, textvariable=analysis_datavalue, width=10)
                    self.stepduration_entry.grid(row=i + 1, column=1, padx=5, pady=5)
                else:
                    self.controller.logger.add_entry("gui", f"Unknown entry added to spectrometer settings ({analysis_datakey} : {analysis_datavalue})",
                                          error=True)
                    tk.Entry(self, textvariable=analysis_datavalue, width=10).grid(row=i + 1, column=1, padx=5, pady=5)
            else:
                # otherwise, use a Label widget
                tk.Label(self, textvariable=analysis_datavalue, fg="blue").grid(row=i + 1, column=1, padx=5, pady=5)

        # Adding limit check highlighting for all Entry input values
        self.RMStolerance_entry.bind("<KeyRelease>",
                                       # lambda is used to pass additional parameters to validate_detection_limits
                                       lambda event: self.check_input_value(event, 1,10000))
        self.windowsize_entry.bind("<KeyRelease>",
                                        # lambda is used to pass additional parameters to validate_detection_limits
                                        lambda event: self.check_input_value(event, 3, 100))
        self.numofoutliers_entry.bind("<KeyRelease>",
                                        # lambda is used to pass additional parameters to validate_detection_limits
                                        lambda event: self.check_input_value(event, 1, 20))
        self.stepduration_entry.bind("<KeyRelease>",
                                         # lambda is used to pass additional parameters to validate_detection_limits
                                         lambda event: self.check_input_value(event, 3, 100))

        # Button to return to HomePage
        tk.Button(self, text="Update settings", command=self.btnUpdateSettings_click, width=20).grid(row=i + 3, column=0, padx=5, columnspan=2)
        tk.Button(self, text="Plot results", command=self.btnPlotResults_click, width=20).grid(row=i + 4, column=0, padx=5, pady=10, columnspan=2)
        tk.Button(self, text="Return", command=self.btnReturn_click, width=10).grid(row=i + 5, column=0, padx=5, pady=10, columnspan=2)

    def check_input_value(self, event, min_allowed, max_allowed):
        # Entry text color is changed to red if outside the permissible limits or not integer
        entry = event.widget
        try:
            value = int(entry.get())
            if min_allowed <= value <= max_allowed:
                entry.config(fg="black")
            else:
                entry.config(fg="red")
        except ValueError:
            entry.config(fg="red")

    def update_input_value(self, input_entry, min_allowed, max_allowed, config_value, controller_value):
        # Check if the value in input_entry is within permissible limits: min_allowed <= input_entry.get() <= max_allowed
        # If yes, update the controller_value with value from input_entry
        # If no, restore the controller_value from config_value
        # returns True if the value was accepted (for additional post-update actions), False if not
        result = False
        try:
            value_temp = int(input_entry.get())
            if min_allowed <= value_temp <= max_allowed:
                controller_value.set(value_temp)
                result = True
            else:
                controller_value.set(config_value)
        except ValueError:
            controller_value.set(config_value)
        input_entry.config(fg="black") # restore the color of input_entry text (if there was an error, it has been corrected)
        return result

    def btnUpdateSettings_click(self):
        """Check the entered values for validity.
           Update the corresponding variables in spectrometer.py with accepted values.
           Otherwise, replace the values in shared_data with those from spectrometer.py variables.
           Finally, navigate to the HomePage."""
        # checking RMStolerance_entry and setting ANALYSIS_RMS_TOLERANCE
        self.update_input_value(self.RMStolerance_entry, 1, 10000, cfg.ANALYSIS_RMS_TOLERANCE, self.controller.shared_data["analysis"]["Emission RMS tolerance, a.u."])
        cfg.ANALYSIS_RMS_TOLERANCE = self.controller.shared_data["analysis"]["Emission RMS tolerance, a.u."].get()
        self.controller.logger.add_entry("analysis",
                              f"Emission RMS tolerance set to {cfg.ANALYSIS_RMS_TOLERANCE} a.u.")
        # checking windowsize_entry and setting ANALYSIS_WINDOW_SIZE
        self.update_input_value(self.windowsize_entry, 3, 100, cfg.ANALYSIS_WINDOW_SIZE, self.controller.shared_data["analysis"]["Sliding window size, samples"])
        cfg.ANALYSIS_WINDOW_SIZE = self.controller.shared_data["analysis"]["Sliding window size, samples"].get()
        self.controller.logger.add_entry("analysis",
                                         f"Sliding window size set to {cfg.ANALYSIS_WINDOW_SIZE} samples")
        # checking numofoutliers_entry
        self.update_input_value(self.numofoutliers_entry, 1, 20, cfg.ANALYSIS_MAX_OUTLIERS, self.controller.shared_data["analysis"]["Max # of outliers"])
        cfg.ANALYSIS_MAX_OUTLIERS = self.controller.shared_data["analysis"]["Max # of outliers"].get()
        self.controller.logger.add_entry("analysis",
                                         f"Max # of outliers set to {cfg.ANALYSIS_MAX_OUTLIERS} samples")
        # checking stepduration_entry
        self.update_input_value(self.stepduration_entry, 3, 100, cfg.ANALYSIS_MIN_STEP_DURATION, self.controller.shared_data["analysis"]["Min step duration, samples"])
        cfg.ANALYSIS_MIN_STEP_DURATION = self.controller.shared_data["analysis"]["Min step duration, samples"].get()
        self.controller.logger.add_entry("analysis",
                                         f"Min step duration set to {cfg.ANALYSIS_MIN_STEP_DURATION} samples")
        # confirm that the parameters have been updated
        self.controller.update_status("Analysis parameters have been updated, re-analyzing...")
        # force re-analysis if no experiment is currently running but he data is present
        if cfg.EXPERIMENT_FINISHED_OK: # TODO! crude temporary solution, just to check that it works. File writing to be done in separate thread!
            # recalculate all steps with newly set parameters
            timePoints = self.controller.data_reader.get("timePoints")
            emissionData = self.controller.data_reader.get("emissionData")
            min_len = min(len(timePoints), len(emissionData))  # trimming the arrays by minimal length, to avoid exceptions if plotting mismatched
            timePoints = timePoints[:min_len]
            emissionData = emissionData[:min_len]
            self.controller.data_reader.step_detector.process_full_dataset(timePoints, emissionData)
            files.experimentStepsResult = self.controller.data_reader.step_detector.get_steps()
            if len(files.experimentStepsResult) > 0:
                self.controller.logger.add_entry("gui", f"Calculating Stern-Volmer analysis results for experiment {files.experimentData['Name']}")
                files.experimentSVdataResult = self.controller.data_reader.step_detector.calculateSVdata(files.experimentData)
            # rewrite Stern-Volmer data file
            SVData_file_path = files.rewriteSVdataFile()
            if SVData_file_path is not None:
                if SVData_file_path:
                    self.controller.logger.add_entry("files", f"Saved the Stern-Volmer analysis data in '{SVData_file_path}'")
                else:  # files.rewriteSVdataFile() returns an empty string if the empty file was deleted
                    self.controller.logger.add_entry("gui",
                                          f"No steps detected, Stern-Volmer results file will not be created.")

    def btnPlotResults_click(self):
        if len(files.experimentSVdataResult) > 1:
            self.controller.logger.add_entry("analysis", f"Plotting the sample analysis output for experiment {files.experimentData['Name']}")
            self.controller.plotSVdata(files.experimentData["Name"])
        else:
            self.controller.logger.add_entry("analysis", f"No data from experiment {files.experimentData['Name']} ready for plotting", error=True)

    def btnReturn_click(self):
        # return to displaying HomePage
        cfg.SINGLE_PASS_ANALYSIS = False
        self.controller.show_frame(HomePage)

class MainWindow(tk.Tk):
    """Main GUI application managing frames, shared data, and the status bar"""
    def __init__(self):
        super().__init__()
        self.title("Stern-Volmer flow setup controller")
        self._icon_img = tk.PhotoImage(file=f"{cfg.RESOURCES_DIR}/SV.png")
        self.iconphoto(True, self._icon_img)
            
        self.geometry(f"{cfg.MAINWINDOW_SIZE_WIDTH}x{cfg.MAINWINDOW_SIZE_HEIGHT}+{cfg.MAINWINDOW_POSITION_X}+{cfg.MAINWINDOW_POSITION_Y}") # window size 800x450, position: x0 = 100, y0 = 100
        self.resizable(False, False)

        # Handle window close event
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Shared data for username, scatter plot points, and status
        self.shared_data = {
            "ledIntensityPWM": tk.DoubleVar(value=cfg.LED_INTENSITY*100), # default value is 100% PWM (ttk.Scale widget uses float control variable, which has to be rounded)
            "spectrometer": {
                "Model": tk.StringVar(value="NONE"), # default value for no spectrometer connected
                "Serial #": tk.StringVar(value="-------"), # dummy string for absent serial number
                "Average N spectra, N =": tk.IntVar(value=0),
                "Integration time, \u03BCs": tk.IntVar(value=0), # in microseconds
                "SMA boxcar, nm": tk.IntVar(value=0), # in nm
                "Acquisition delay, ms": tk.IntVar(value=0) # in ms
            },
            "emission_detection": {
                "detection_mode": tk.IntVar(value=cfg.EMISSIONDETECT_SINGLE_WAVELENGTH), # default detection by emission at single wavelength (Lmax)
                "window_min": tk.IntVar(value=cfg.WAVELENGTH_MIN), # default detection window limits are taken from min/max spectrum width
                "window_max": tk.IntVar(value=cfg.WAVELENGTH_MAX)
            },
            "analysis": {
                "Emission RMS tolerance, a.u.": tk.IntVar(value=cfg.ANALYSIS_RMS_TOLERANCE),
                "Sliding window size, samples": tk.IntVar(value=cfg.ANALYSIS_WINDOW_SIZE),
                "Max # of outliers": tk.IntVar(value=cfg.ANALYSIS_MAX_OUTLIERS),
                "Min step duration, samples": tk.IntVar(value=cfg.ANALYSIS_MIN_STEP_DURATION)
            },
            "pumps": {
                "UART3": { # Pump1: SOLVENT
                    "label": cfg.UART_DEVICES["UART3"]["name"],
                    "SyringeVolume": tk.IntVar(value=20),
                    "PrimeFlowrate": tk.DoubleVar(value=2),
                    "PrimeVolume": tk.DoubleVar(value=2),
                    "status_text": "Pump1",
                    "status_color": "white"
                },
                "UART4": { # Pump2: DYE/CATALYST
                    "label": cfg.UART_DEVICES["UART4"]["name"],
                    "SyringeVolume": tk.IntVar(value=10),
                    "PrimeFlowrate": tk.DoubleVar(value=2),
                    "PrimeVolume": tk.DoubleVar(value=1),
                    "status_text": "Pump2",
                    "status_color": "white"
                },
                "UART5": { # Pump3: QUENCHER
                    "label": cfg.UART_DEVICES["UART5"]["name"],
                    "SyringeVolume": tk.IntVar(value=10),
                    "PrimeFlowrate": tk.DoubleVar(value=2),
                    "PrimeVolume": tk.DoubleVar(value=1),
                    "status_text": "Pump3",
                    "status_color": "white"
                }
            },
            "StatusText": "Please connect an Ocean Optics spectrometer"
        }

        # Create a container frame for both left_frame and right_frame
        content_frame = tk.Frame(self)
        content_frame.pack(fill="both", expand=True)

        # Creating left-side frame for switchable pages
        left_frame = tk.Frame(content_frame, width=cfg.MAINWINDOW_LEFTFRAME_WIDTH, height=cfg.MAINWINDOW_SIZE_HEIGHT)
        left_frame.pack(side="left", fill="both", expand=False)

        # Creating right-side frame for Matplotlib plots
        self.right_frame = tk.Frame(content_frame, width=cfg.MAINWINDOW_SIZE_WIDTH-cfg.MAINWINDOW_LEFTFRAME_WIDTH, height=cfg.MAINWINDOW_SIZE_HEIGHT-20)
        self.right_frame.pack(side="right", fill="both", expand=True)

        # Dictionary to store frame objects
        self.frames = {}

        # Creating and storing frames
        for F in (HomePage, SpectrometerPage, AnalysisParametersPage):
            frame = F(left_frame, self)
            self.frames[F] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        # Creating the status container at the bottom of the main window
        self.status_bar = tk.Frame(self, bd=1, relief=tk.SUNKEN)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # Status container: Main status label (on the left)
        self.status_label = tk.Label(self.status_bar, bd=1, relief=tk.SUNKEN, anchor=tk.W,
                                     text=self.shared_data["StatusText"], font=('Arial', 9))
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Status container: container for device labels (on the right)
        self.device_frame = tk.Frame(self.status_bar, bd=1, relief=tk.SUNKEN)
        self.device_frame.pack(side=tk.RIGHT, padx=2)

        # Create 3 device labels (Pump1, Pump2, Pump3)
        # TODO: maybe also add a spectrometer state label here?
        self.device_labels = []
        number_of_labels = 3
        for i, device_label in enumerate(self.shared_data["pumps"].values()):
            label = tk.Label(self.device_frame, bd=1, relief=tk.SUNKEN,
                             width=6, font=('Arial', 9),
                             text=device_label["status_text"],
                             bg=device_label["status_color"])
            label.pack(side=tk.LEFT, padx=(0, 5) if i < (number_of_labels - 1) else 0)  # 5px gap between labels
            self.device_labels.append(label)

        # # Creating the status bar at the bottom of the main window
        # self.status_label = tk.Label(self, bd=1, relief=tk.SUNKEN, anchor=tk.W,
        #                              text=self.shared_data["StatusText"], font=('Arial', 9))
        # self.status_label.pack(side="bottom", fill=tk.X)

        self.show_frame(HomePage)  # Show Home Page first
        self.create_plot()  # Create Matplotlib plot on the right side
        self.update_plot_flag = False # creating a flag for updating the plot asynchronously
        self.updater() # start the updater

        # Creating log window instance, if enables in config
        if cfg.LOG_WINDOW in cfg.LOGGER_MODE:
            self.log_window = logger.LogWindow(self)

    def updater(self):
        if self.update_plot_flag:
            self.update_plot_flag = False
            self.update_plot()
        # update LED intensity value from LED controller
        if hasattr(self, "LED_controller") and (not self.frames[SpectrometerPage]._user_dragging_slider):
            # TODO: only directly update if the Spectrometer settings window is not open
            self.shared_data["ledIntensityPWM"].set(self.LED_controller.LED_brightness_percent)
            self.frames[SpectrometerPage].toggle_ledIntensity_slider(self.LED_controller.LED_is_ON)
        # update pump status indication
        if hasattr(self, "pump_controller"):
            self.update_pump_status_indication() # TODO: BUG? this should not be called here, only works because self.update_plot_flag = False on startup
        # update button titles and states
        enable_spectrometer_buttons = cfg.SPECTROMETER_CONNECTED_OK and cfg.SPECTRUM_RECORDED_OK
        self.toggle_spectrometer_interface(cfg.SPECTROMETER_CONNECTED_OK)
        self.frames[HomePage].toggle_spectrometer_buttons(enable_spectrometer_buttons)
        enable_experiment_buttons = cfg.EXPERIMENT_LOADED_OK and cfg.PUMPS_PRIMED_OK
        self.frames[HomePage].toggle_experiment_buttons(enable_experiment_buttons) # TODO: does not seem to work, check logic!
        if cfg.EXPERIMENT_IS_PAUSED:
            self.frames[HomePage].btnStartPauseExperiment.config(text="Resume experiment")
        elif cfg.EXPERIMENT_IS_RUNNING:
            self.frames[HomePage].btnStartPauseExperiment.config(text="Pause experiment")
        else:
            self.frames[HomePage].btnStartPauseExperiment.config(text="Start experiment")
        self.after(cfg.GUI_PLOT_UPDATE_INTERVAL_MS, self.updater)

    def link_data_reader(self, data_reader):
        self.data_reader = data_reader # linking the current instance of DataReader() to enable widgets in frames to call its methods
        self.data_reader.set_status_label(self.status_label) # sending a handle to status_label to receive status messages from DataReader
        self.shared_data["spectrometer"]["Average N spectra, N ="].set(self.data_reader.NumOfSpectraPerDatapoint)
        self.shared_data["spectrometer"]["Integration time, \u03BCs"].set(self.data_reader.integration_time) # in microseconds
        self.shared_data["spectrometer"]["SMA boxcar, nm"].set(self.data_reader.boxcarSMA) # in nm
        self.shared_data["spectrometer"]["Acquisition delay, ms"].set(self.data_reader.acquisition_delay) # in ms

    def link_logger(self, logger_handle):
        self.logger = logger_handle

    def link_pump_controller(self, pump_controller_handle):
        self.pump_controller = pump_controller_handle
        self.pump_controller.set_progress_label(self.status_label)  # sending a handle to status_label to receive status messages from PumpController and PumpScheduler
        self.pump_controller.initialize_pumps()

    def link_LED_controller(self, LED_controller_handle):
        self.LED_controller = LED_controller_handle
        self.LED_controller.reset_LED_controller()

    def on_closing(self):
        MessageBoxConfirmExitWindow(self)

    def show_frame(self, page_class):
        """Raise a frame to the front and refresh if necessary."""
        frame = self.frames[page_class]
        frame.tkraise()

    def create_plot(self):
        """Create the Matplotlib scatter plots for current spectrum (top) and intensity over time (bottom)"""
        self.figure = plt.figure()
        # two plots per figure (two rows, one column)
        self.graphSpectrum = self.figure.add_subplot(211) # current spectrum
        self.graphSpectrum.text(0.5, 0.55, "Live fluorescence emission spectrum", transform=self.graphSpectrum.transAxes,
                    fontsize=12, ha='center', va='top', c="dodgerblue") # temporary title visible while the spectrometer is not connected
        # self.graphSpectrum.set_title(f" Live fluorescence emission spectrum")
        self.graphIntensity = self.figure.add_subplot(212) # plotting emission intensity over time
        # self.graphIntensity.set_title(f"Emission intensity over time\nand experiment pump program")
        self.graphIntensity.text(0.5, 0.6, "Emission intensity over time\nand experiment pump program", transform=self.graphIntensity.transAxes,
                     fontsize=12, ha='center', va='top', c="forestgreen")  # temporary title visible while the spectrometer is not connected
        self.canvas = FigureCanvasTkAgg(self.figure, self.right_frame)
        self.canvas.get_tk_widget().pack(side="top", fill="x")

    def update_plot(self):
        """Update the Matplotlib scatter plot with new data."""
        # TODO: fixed the bug with updating GUI from spectrometer thread
        ## but probably still need to check len(timePoints) == len(emissionData)
        self.graphSpectrum.clear()

        ### updating the spectrum plot
        # Ensuring that the array dimensions are matched
        wavelengthsData = self.data_reader.wavelengths
        intensitiesData = self.data_reader.intensities
        intensitiesSMAData = self.data_reader.intensitiesSMA
        min_len = min(len(wavelengthsData), len(intensitiesData), len(intensitiesSMAData))  # trimming the arrays by minimal length, to avoid exceptions if plotting mismatched
        wavelengthsData = wavelengthsData[:min_len]
        intensitiesData = intensitiesData[:min_len]
        intensitiesSMAData = intensitiesSMAData[:min_len]
         # plotting the raw data as light blue scatter graph
        self.graphSpectrum.scatter(wavelengthsData, intensitiesData, label="raw spectrum", s=5, c="powderblue")
        # plotting the (averaged) spectrum blue if within limits, red if intensity overflown over the linear range of the detector
        self.graphSpectrum.plot(wavelengthsData, intensitiesSMAData, label=f"SMA (N = {self.data_reader.boxcarSMA})",
                                c="dodgerblue" if not self.data_reader.OverflowFlag else "red")
        self.graphSpectrum.scatter(self.data_reader.Lmax, self.data_reader.Ymax_position + 5,
                                   label="\u03BBmax: " + str(self.data_reader.Lmax) + " nm", marker=7,
                                   c="red")  # marker filled triangle aligned to bottom
        # if in integration over window detection mode, plot vertical lines to indicate position of integration limits
        if self.data_reader.EmissionDetectionMode == cfg.EMISSIONDETECT_INTEGRATE_OVER_WINDOW:
            self.graphSpectrum.vlines(x=self.data_reader.detection_Lmin, ymin=0, ymax=self.data_reader.Ymax_position,
                                      colors='darkorange', label='detection')
            self.graphSpectrum.vlines(x=self.data_reader.detection_Lmax, ymin=0, ymax=self.data_reader.Ymax_position,
                                      colors='darkorange')
        self.graphSpectrum.set_xlim(cfg.WAVELENGTH_MIN,
                                    cfg.WAVELENGTH_MAX)  # as this array is returned ordered by wavelength
        self.graphSpectrum.set_ylim(round(np.min(intensitiesData)), round(np.max(intensitiesData)) + 50)
        self.graphSpectrum.set_xlabel("wavelength [nm]")
        self.graphSpectrum.legend(loc="upper right") # upper left?
        self.graphSpectrum.set_ylabel("I [a.u.]")

        ### updating the intensity vs time plot
        self.graphIntensity.clear()
        try:
            self.graphPumpProgram.remove()
            self.graphPumpProgram = None
        except:
            # TODO: think of a better way, without catching all exceptions here!
            pass
        # Ensuring that the array dimensions are matched
        timePoints = self.data_reader.get("timePoints") # TODO! rework getters/setters using @property!
        emissionData = self.data_reader.get("emissionData")
        overflownData = self.data_reader.get("overflownData")
        min_len = min(len(timePoints), len(emissionData), len(overflownData)) # trimming the arrays by minimal length, to avoid exceptions if plotting mismatched
        timePoints = timePoints[:min_len]
        emissionData = emissionData[:min_len]
        overflownData = overflownData[:min_len]
        if min_len == 0: # plotting zero-length data would raise an exception, avoiding
            return
        if files.experimentData: # if experiment data have been loaded, draw the pump program with correct timings
            # plot the pump program
            self.graphPumpProgram = self.graphIntensity.twinx()  # plotting pump program over emission intensity graph
            self.graphPumpProgram.set_xlim(0, files.experimentProgramTotalTime)
            # loading values for stacked bars
            # TODO: correct - the pump program bars only need to be calculated once per experiment!
            step_time_array, solvent_flow_array, catalyst_flow_array, quencher_flow_array = zip(*files.experimentPumpProgram)
            bar_widths = np.diff(step_time_array + (files.experimentProgramTotalTime,)) # adding final time to step_time_array and compute bar widths
            self.graphPumpProgram.bar(step_time_array, catalyst_flow_array, color='gold', alpha=0.3, label='catalyst', width=bar_widths, align='edge', zorder=1)
            self.graphPumpProgram.bar(step_time_array, quencher_flow_array, bottom=catalyst_flow_array, color='darkgray', alpha=0.3, label='quencher', width=bar_widths, align='edge',
                                      zorder=1)
            self.graphPumpProgram.bar(step_time_array, solvent_flow_array, bottom=np.array(catalyst_flow_array) + np.array(quencher_flow_array), color='lightblue', alpha=0.3, label='solvent',
                                      width=bar_widths, align='edge', zorder=1)
            self.graphPumpProgram.set_ylabel("Flow (mL/min)")
            self.graphPumpProgram.set_ylim(0, files.experimentProgramMaxFlow)
            # self.graphPumpProgram.tick_params(axis='y')
            # self.graphPumpProgram.set_yticks(np.linspace(0, files.experimentProgramMaxFlow, 5))
            self.graphPumpProgram.legend(loc="upper right") # lower right?
            # plot the current emission intensities in the experiment time frame in two colors (red for overflown data) using NumPy boolean masking
            self.graphIntensity.set_xlim(0, files.experimentProgramTotalTime)
            # self.graphIntensity.scatter(timePoints, emissionData, label="I(t)", s=10, c="forestgreen")
            self.graphIntensity.scatter(timePoints[~overflownData], emissionData[~overflownData], label="I(t)", s=10, c="forestgreen", zorder=2, alpha=0.4)
            self.graphIntensity.scatter(timePoints[overflownData], emissionData[overflownData], s=10, c="red", zorder=2, alpha=0.4)
            # plot the detected stable emission steps, if available
            emissionSteps = self.data_reader.step_detector.get_steps()
            if emissionSteps:
                for emission_step in emissionSteps.values():
                    # Compute rectangle dimensions
                    x = emission_step.step_t_min
                    width = emission_step.step_t_max - emission_step.step_t_min
                    # padding_x = 0.1 * width # 5% buffer to display around scatter markers
                    y = emission_step.value_average - emission_step.value_stddev
                    height = emission_step.value_stddev * 4 # average±2*stddev approximates 0.95 confidence in a normal distribution - better use SEM instead?
                    # padding_y = 0.05 * height  # 200% buffer to display around scatter markers
                    # Filled rectangle with light green background
                    # rect = Rectangle((x, y), width, height, # height + 2 * padding_y,
                    #                 facecolor='red',
                    #                 edgecolor=None,
                    #                 alpha=0.5,
                    #                 zorder=2.5)
                    #self.graphIntensity.add_patch(rect)
                    # Alternative: Border-only version (no fill)
                    rect = Rectangle((x, y), width, height,
                                             facecolor='none',
                                             edgecolor='magenta',
                                             linewidth=1.0,
                    #                         linestyle='--',
                                             zorder=2.5)
                    self.graphIntensity.add_patch(rect)
                    # add midpoint tick marker for each rectangle
                    x_mid = emission_step.step_t_mid
                    y_mid = emission_step.value_average
                    # y_tick_height = max(emission_step.value_stddev, np.max(emissionData)*0.03)
                    y_tick_height = 2*emission_step.value_stddev + np.max(emissionData)*0.03 # average±2*stddev approximates 0.95 confidence in a normal distribution - better use SEM instead?
                    tick = Line2D([x_mid, x_mid], [y_mid - y_tick_height, y_mid + y_tick_height],
                                  color='magenta',  # same as rectangle
                                  linewidth=1.0,
                                  zorder=2.6)  # slightly above the rectangle
                    self.graphIntensity.add_line(tick)
        else: # otherwise, plotting only current emission intensities for monitoring
            #self.graphIntensity.scatter(timePoints, self.data_reader.get("emissionData"), label="I(t)", s=10, c="forestgreen")
            #  self.graphIntensity.scatter(timePoints, emissionData, label="I(t)", s=10, c="forestgreen")
            self.graphIntensity.scatter(timePoints[~overflownData], emissionData[~overflownData], label="I(t)", s=10, c="forestgreen", zorder=2)
            self.graphIntensity.scatter(timePoints[overflownData], emissionData[overflownData], s=10, c="red", zorder=2)
            self.graphIntensity.set_xlim(timePoints[0], max(timePoints[-1], 10))  # time limits from timePoints array, but not less than 10 sec
            self.graphIntensity.legend(loc="upper right")
        self.graphIntensity.set_ylim(0, round(np.max(emissionData)) + 50)
        self.graphIntensity.set_xlabel("time [s]")
        self.graphIntensity.set_ylabel("I(\u03BBmax) [a.u.]")
        # redrawing
        self.figure.tight_layout()
        self.canvas.draw()

    def update_status(self, status_text, color="black"):
        """Update the status bar text dynamically."""
        self.shared_data["StatusText"] = status_text
        self.status_label.config(text=self.shared_data["StatusText"], fg=color)
        # the following line may be used to test the logging
        # self.logger.add_entry("gui", status_text)

    def update_pump_status_indication(self):
        self.pump_controller.poll_state()
        pump_states = self.pump_controller.get_pump_states()
        for i, pump_state in enumerate(pump_states):
            # device_label_color = cfg.guiColorScheme["statusPumpStatusColors"][pump_state]
            # self.shared_data["pumps"][cfg.PUMP_UARTS[i]]["status_color"] = device_label_color
            # self.device_labels[i]["text"] = self.shared_data["pumps"][pump_uart]["status_text"]
            self.device_labels[i]["bg"] = cfg.guiColorScheme["statusPumpStatusColors"][pump_state]

    def update_spectrometer_model_ID(self, model, serial_number):
        self.shared_data["spectrometer"]["Model"].set(model)
        self.shared_data["spectrometer"]["Serial #"].set(serial_number)

    def toggle_spectrometer_interface(self, connected):
        if not connected:
            self.show_frame(HomePage)
            self.update_status("Please connect an Ocean Optics spectrometer")
        # self.update_idletasks()

    def update_pump_settings(self):
        # Trying to load the default syringe settings from SYRINGES_CSV_FILE
        result_msg = files.LoadSyringesCSV()
        if not result_msg:  # only if opened without errors
            self.logger.add_entry("files", f"Syringe settings loaded from {cfg.SYRINGES_CSV_FILE}")
            for pump_entry in self.shared_data["pumps"].values():
                pump_label = pump_entry["label"]
                syringe_volume = int(files.experimentData["Syringes"][pump_label]["Volume (mL)"]) # load syringe volume from experimentData
                pump_entry["SyringeVolume"].set(syringe_volume) # save it into shared_data for GUI use
                syringe_settings = files.GetDefaultSyringeSettings(syringe_volume) # load default settings (prime flowrate & volume, max flowrate) for the syringe of this volume
                # TODO! add saving max flowrate here!
                if syringe_settings:
                     pump_entry["PrimeFlowrate"].set(float(syringe_settings["Prime flow rate (mL/min)"]))
                     pump_entry["PrimeVolume"].set(float(syringe_settings["Prime volume (mL)"]))
                     self.logger.add_entry("gui", f"Default syringe settings loaded for {pump_label}")
        else:
            self.logger.add_entry("files", f"Could not load syringe settings from {cfg.SYRINGES_CSV_FILE}", error=True)

    def open_pump_settings_window(self):
        """Open the Pump Settings popup window."""
        self.update_pump_settings()
        PumpSettingsWindow(self)

    def plotSVdata(self, plot_title: str):
        SVPlotWindow(self, plot_title)

if __name__ == "__main__":
    from logger import Logger
    from spectrometer import DataReader

    app = MainWindow()
    logger = Logger(app)
    data_reader = DataReader(app, logger)
    app.link_data_reader(data_reader)
    app.link_logger(logger)
   # app.frames[HomePage].btnLoadExperiment.config(state="normal")
   # app.frames[HomePage].btnPumps.config(state="normal")
   # app.frames[HomePage].btnStartPauseExperiment.config(state="normal")
    app.mainloop()
