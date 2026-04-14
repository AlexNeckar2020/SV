""" This code was developed with assistance from ChatGPT (OpenAI, 2025) """

import seabreeze

from Lib.analysis import StepDetector

import Lib.config as cfg

if cfg.PLATFORM != cfg.PLATFORM_RASPBERRY_PI:
    seabreeze.use('pyseabreeze')
# else:
#    seabreeze.use('cseabreeze') # use the default backend on Raspberry Pi
from seabreeze.spectrometers import Spectrometer

from threading import Thread, Event, Lock
import numpy as np
import math
from random import random, uniform # for random noise in SpectrometerEmulator._emulator_spectrum_function()
import time
import csv
from datetime import datetime

import Lib.files as files
import Lib.analysis as analysis

#### Data processing functions begin
def MovingAverage(data_set, boxcar = 10):
    """ Simple moving average for smoothing the emission spectra.
        Default boxcar: 10 nm
        code idea: https://gist.github.com/rday/5716218
    """
    if boxcar == 1: # no averaging
        return data_set
    weights = np.ones(boxcar) / boxcar
    return np.convolve(data_set, weights, mode="same") # preserve the length of data_set array to simplify plotting
#### Data processing functions end

#### SpectrometerEmulator class begin
# An emulator mimicking a connected Ocean Optics spectrometer.
class SpectrometerEmulator:
    def __init__(self, logger_handle):
        self.logger = logger_handle
        self.model = "USB4000"
        self.serial_number = "Emulator"
        self.integration_time_micros_limits = [10, 65535000]
        self._integration_time = 100000
        self.max_intensity = 65535.0
        self._wavelengths = np.arange(190.0, 950.0, step=0.5, dtype=np.float64)
        self._spectrum_width = self._wavelengths[-1] - self._wavelengths[0]
        self._intensities = np.zeros_like(self._wavelengths, dtype=np.float64)
        self._time0 = time.monotonic()
        self._sample_spectrum = None
        if self._load_sample_spectrum():
            self.logger.add_entry("spectrometer", f"Sample spectrum file loaded from {cfg.SAMPLE_SPECTRUM_CSV_FILE}")

    def _emulator_spectrum_function(self, x: float) -> float:
        """
        A function generating random or periodic data in time-dependent fashion.
        """
        number_of_periods = 10
        max_amplitude_percent = 0.8
        time_shift = time.monotonic() - self._time0
        y = (math.sin((x + time_shift*5) * 2 * math.pi * number_of_periods / self._spectrum_width) + uniform(1, 3)) * (self.max_intensity / 4) * max_amplitude_percent
        return y

    def _load_sample_spectrum(self) -> bool:
        """
        Loads a sample emission spectrum from the "../Rsc" folder, asserting that it has not been corrupted.
        :return True if succeeded, False if file was not open or was damaged (logging the exception).
        """
        try:
            with open(cfg.SAMPLE_SPECTRUM_CSV_FILE, newline='', encoding='utf-8') as csvfile:
                csv_reader = csv.reader(csvfile)

                # Column names of the spectrum file for confirmation
                expected_columns = ["Wavelength (nm)", "Intensity (a.u.)"]

                # Read the header row
                headers = next(csv_reader)
                assert headers[:2] == expected_columns, f"expected {expected_columns}, found {headers[:2]} in as column headers"

                sample_spectrum_wavelengths, sample_spectrum_intensities = [], []
                for row in csv_reader:
                    sample_spectrum_wavelengths.append(float(row[0]))
                    sample_spectrum_intensities.append(float(row[1]))
                assert len(sample_spectrum_wavelengths) == len(sample_spectrum_intensities), "wavelength and intensity arrays are mismatched"

        except (FileNotFoundError, OSError, AssertionError, ValueError) as e:
            self.logger.add_entry("spectrometer", f"Sample spectrum file {cfg.SAMPLE_SPECTRUM_CSV_FILE} could not be loaded or is corrupted: {e}",
                                  error=True)
            return False

        # Convert retrieved lists to numpy arrays of SpectrometerEmulator
        self._wavelengths = np.array(sample_spectrum_wavelengths)
        self._sample_spectrum = np.array(sample_spectrum_intensities)
        cfg.WAVELENGTH_MIN = sample_spectrum_wavelengths[0]
        cfg.WAVELENGTH_MAX = sample_spectrum_wavelengths[-1]
        # print(f"{self._sample_spectrum=}")
        return True

    def _get_noisy_scaled_sample_spectrum(self, intensity_factor: float, noisiness: float) -> np.ndarray | None:
        """
        Modify the sample spectrum by adding noise and scaling intensities.
        :param intensity_factor: float scaling factor for the final intensity.
        :param noisiness: float in [0.0, 1.0+] controlling noise level before scaling.
        """
        if self._sample_spectrum is None:
            return None

        max_intensity = np.max(self._sample_spectrum)  # AI: find max intensity to scale noise
        noisy_scaled = []

        for intensity in self._sample_spectrum:
            noise = uniform(-noisiness, noisiness) * max_intensity  # AI: symmetric random noise
            modified_intensity = (intensity + noise) * intensity_factor  # AI: apply noise, then scale
            noisy_scaled.append(modified_intensity)

        return np.array(noisy_scaled)  # return the modified self._sample_spectrum

    def _simulate_quenching_ratio_at_experiment_time(self, timepoint_s: float) -> float | None:
        """
        Return flow(Catalyst)/flow(Quencher) at a given time point of files.experimentPumpProgram.
        """
        for entry in reversed(files.experimentPumpProgram):  # iterate backwards
            step_time_sec, _, flow_Catalyst, flow_Quencher = entry
            if timepoint_s > step_time_sec:  # find first experiment pump program step past timepoint_s time
                if flow_Catalyst == 0.0:
                    return 0.0 # return 0.0 if no catalyst(dye) present
                elif flow_Quencher == 0.0:
                    return 1.0 # return 1.0 if no quencher present
                else:
                    return flow_Catalyst / (flow_Catalyst + flow_Quencher) # compute and return ratio
        return 0.0  # return 0.0 if no valid entry found

    def integration_time_micros(self, integration_time_us: int):
        self._integration_time = integration_time_us

    def wavelengths(self) -> np.ndarray:
        return self._wavelengths

    def intensities(self) -> np.ndarray:
        time.sleep(self._integration_time / 1000000.0)
        if self._sample_spectrum is None:
            self._intensities = np.vectorize(self._emulator_spectrum_function)(self._wavelengths)
        else:
            if cfg.EXPERIMENT_IS_RUNNING:
                emulated_quenched_emission_intensity = cfg.LED_INTENSITY * self._simulate_quenching_ratio_at_experiment_time(files.lastSpectrumTimepoint)
            else:
                emulated_quenched_emission_intensity = cfg.LED_INTENSITY
            # print(f" ::: {emulated_quenched_emission_intensity=:.3f}")
            self._intensities = self._get_noisy_scaled_sample_spectrum(emulated_quenched_emission_intensity, 0.2) # this parameter could be made tunable from GUI if emulator is enabled
        return self._intensities
#### SpectrometerEmulator class end


#### DataReader class begin
# Ensures consistent connection to a single Ocean Optics spectrometer, handling disconnection and reconnection
class DataReader:
    def __init__(self, gui_handle, logger_handle):
        """
        Initializes the manager, including thread control and logger.
        """
        ### Storing logger and GUI handles
        self.logger = logger_handle
        self.gui = gui_handle
        self._status_label = None
        ### Initializing data reader thread control and spectrometer lock
        self._thread = None
        self._stop_event = Event()
        self._pause_event = Event()
        self._spec_lock = Lock()
        self._running = False
        self.spec = None
        self.spec_is_emulated = cfg.EMULATE_SPECTROMETER
        ### Flag to record the next spectrum as background
        self._waiting_for_background = False
        ### Initializing spectrometer variables
        # list of list variables to do numpy array to list conversion in get() and back in set()
        self.lists = ["timePoints", "emissionData", "overflownData"]
        # arrays for storing spectra
        self.wavelengths = None # wavelengths received from spectrometer
        self.intensities = None # emission intensities received from spectrometer
        self.intensitiesSMA = None # emission intensities received from spectrometer, with averaging applied
        self.background = None # emission intensities received from spectrometer, stored as background
        self.backgroundSMA = None # emission intensities received from spectrometer, stored as background, with averaging applied
        # variables and arrays for storing emission intensity over time
        self.acquisition_delay = cfg.DEFAULT_ACQUISITION_DELAY_MS
        self.time0 = None  # t0 of the test graph and then of the actual experiment
        self.timePoints = []
        self.emissionData = []
        self.overflownData = []
        # list of list variables to do special processing (numpy array to list conversion) in get() and set()
        self.lists = ["timePoints", "emissionData", "overflownData"]
        # for single wavelength emission detection mode (EMISSIONDETECT_SINGLE_WAVELENGTH)
        self.Lmax = 0 # Lmax (nm) of the last acquired spectrum
        # TODO: the following value is not used directly but as round(self.data_reader.intensitiesSMA[self.data_reader.Ymax_pos]
        # so this should be made an accessible attribute instead
        self.Ymax_position = None # x-position of the wavelengths array corresponding to Lmax (nm) of the last acquired spectrum
        # for integration over area emission detection mode (EMISSIONDETECT_INTEGRATE_OVER_WINDOW)
        self.detection_Lmin = cfg.WAVELENGTH_MIN
        self.detection_Lmax = cfg.WAVELENGTH_MAX
        # other global variables
        self.Xmin_pos = None # x-position of the wavelengths array corresponding to cfg.WAVELENGTH_MIN
        self.Xmax_pos = None # x-position of the wavelengths array corresponding to cfg.WAVELENGTH_MAX
        self.NumOfSpectraPerDatapoint = 1  # default value on startup (1 spectrum/datapoint, no averaging)
        self.integration_time = 100000  # default value on startup (100 ms)
        self.boxcarSMA = 10  # default value on startup
        self.EmissionDetectionMode = cfg.EMISSIONDETECT_SINGLE_WAVELENGTH
        self.OverflowFlag: bool = False
        # adding a step detector instance for analysis
        self.step_detector = StepDetector()

    def get(self, var_name):
        """
        Universal getter for attributes, returning lists as numpy arrays
        """
        if hasattr(self, var_name):
            if var_name in self.lists:
                return np.array(getattr(self, var_name))
            else:
                return getattr(self, var_name)
        raise AttributeError(f"SpectrometerManager object has no attribute '{var_name}'")

    def set(self, var_name, value):
        """
        Universal setter for attributes, converting incoming numpy array data into a regular list
        """
        if hasattr(self, var_name):
            if var_name in self.lists:
                setattr(self, var_name, value.tolist())
            else:
                setattr(self, var_name, value)
            self.logger.add_entry("spectrometer", f"Set {var_name} = {value}")
        else:
            raise AttributeError(f"SpectrometerManager object has no attribute '{var_name}'")

    def set_status_label(self, label_widget):
        """
        Sets a Tkinter label for displaying live status.
        """
        self._status_label = label_widget

    def _update_status_label(self, new_status: str):
        if self._status_label and cfg.ALLOW_SPECTROMETER_STATUS_UPDATES:
            self._status_label.config(text=new_status)

    def start(self):
        """Starts the background acquisition thread."""
        if self._thread and self._thread.is_alive():  # check if not starting an already existing thread
            self.logger.add_entry("spectrometer", "start() reentered: data reader thread is already running!",
                                  error=True)
            return
        if not self._running:
            self._running = True
            self._stop_event.clear()
            self._pause_event.clear()
            self._thread = Thread(target=self._data_reader_loop, daemon=True)
            self._thread.start()
            self.logger.add_entry("spectrometer", "Data reader thread started")

    def stop(self):
        """Stops the background acquisition thread and cleans up."""
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join()
            self._thread = None
        self.logger.add_entry("spectrometer", "Data reader thread stopped")

    def pause(self):
        """Pauses acquisition without stopping the thread."""
        self._pause_event.set()
        self.logger.add_entry("spectrometer", "Data reading paused")

    def resume(self):
        """Resumes acquisition if it was paused."""
        self._pause_event.clear()
        self.logger.add_entry("spectrometer", "Data reading resumed")

    def restart(self):
        """Resumes acquisition if it was paused, but erasing the previously accumulated data."""
        cfg.SPECTRUM_RECORDED_OK = False
        self.step_detector.reset() # erase all previously saved step data
        self.time0 = None
        self.timePoints = []
        self.emissionData = []
        self.overflownData = []
        self._pause_event.clear()
        self.logger.add_entry("spectrometer", "Spectrometer data reading restarted, previous emission data erased")

    def reanalyze(self):
        """Performs a new step detector analysis on te entire dataset, if the experiment is running or finished"""
        if cfg.EXPERIMENT_IS_RUNNING or cfg.EXPERIMENT_FINISHED_OK:
            if self.step_detector.process_full_dataset(self.timePoints, self.emissionData):
                print(f" ::: {self.timePoints=}")
                print(f" ::: {self.emissionData=}")
                steps = self.step_detector.get_steps()
                print(f" ::: {steps=}")
                self.logger.add_entry("analysis", "The existing dataset was re-analyzed with updated parameters.")
                return
        self.logger.add_entry("analysis", "The existing dataset is not ready for analysis.", error=True)

    def _data_reader_loop(self):
        """
        Main data reader loop: handles acquisition and reconnection logic.
        """
        while not self._stop_event.is_set(): # do not enter while stopping the thread
            with self._spec_lock: # maintain single spectrometer context
                if self.spec:
                    # if paused, run a dummy cycle
                    if self._pause_event.is_set():
                        time.sleep(cfg.DATA_READER_THREAD_LOOP_DELAY)
                        continue
                    # otherwise, record a regular or background spectrum, depending on the _waiting_for_background flag
                    if self._waiting_for_background:
                        # awaiting background spectrum to be recorded in the next data reader loop iteration
                        self._acquire_background_spectrum()
                        self._waiting_for_background = False
                    else:
                        # acquire regular spectrum
                        self._acquire_and_process_spectrum()
                        self.gui.update_plot_flag = True  # new spectrum acquired: matplotlib plot will be redrawn by GUI's updater in its next loop
                        self._report_spectrometer_status()
                    time.sleep(self.acquisition_delay / 1000.0)
                else:
                    cfg.SPECTROMETER_CONNECTED_OK = False  # clear "spectrometer is connected" global flag
                    self._attempt_connect()
                    time.sleep(cfg.RECONNECT_DELAY_S)

    def _attempt_connect(self):
        """
        Tries to safely connect to the spectrometer.
        """
        try:
            if self.spec_is_emulated:
                self.spec = SpectrometerEmulator(self.logger)
                self.logger.add_entry("spectrometer", "Spectrometer output will be simulated")
            else:
                self.spec = Spectrometer.from_first_available()
        except seabreeze._exc.SeaBreezeError:
            self.logger.add_entry("spectrometer", "Spectrometer not ready yet, reconnecting...")
            self.spec = None
            pass
        else:
            self._initialize_spectrometer()


    def _initialize_spectrometer(self):
        """
        Initializes spectrometer parameters after connection.
        """
        self.gui.update_spectrometer_model_ID(model=self.spec.model, serial_number=self.spec.serial_number)
        cfg.SPECTROMETER_CONNECTED_OK = True # set "spectrometer is connected" global flag
        status_text = f"Found model: {self.spec.model}, serial number: {self.spec.serial_number}"
        if self._status_label:
            self._status_label.config(text=status_text) # display the status_text in GUI
        self.logger.add_entry("spectrometer", status_text)
        self._load_spectrometer_limits()
        self.update_integration_time()
        self._set_detection_limits()
        self._zero_background_spectrum()

    def _load_spectrometer_limits(self):
        """
        Loads the spectrometer hardware limits into the corresponding global variables.
        """
        # loads device limits into the corresponding config.py global variables
        # TODO: these will have to be moved into the SpectrometerManager class
        [cfg.INTEGRATION_TIME_US_MIN, cfg.INTEGRATION_TIME_US_MAX] = self.spec.integration_time_micros_limits
        cfg.EMISSION_INTENSITY_LIMIT_MAX = self.spec.max_intensity
        self.logger.add_entry("spectrometer",
                              f"Integration time device limits = [{cfg.INTEGRATION_TIME_US_MIN} us ... {cfg.INTEGRATION_TIME_US_MAX} us]")
        self.logger.add_entry("spectrometer",
                              f"Emission intensity limit = {cfg.EMISSION_INTENSITY_LIMIT_MAX:.1f} a.u.")

    def _set_detection_limits(self):
        """
        Sets the spectrometer detection limits in the class attributes.
        These are either hardware limits if cfg.WAVELENGTH_CROP_RANGE == False,
        or are set within [cfg.WAVELENGTH_MIN, cfg.WAVELENGTH_MAX] if cfg.WAVELENGTH_CROP_RANGE == True (normal use case).
        All data array attributes will be truncated and will be saved or displayed within these limits.
        """
        self.wavelengths = self.spec.wavelengths()  # Spectrometer.wavelengths() returns a numpy array of Float
        self.logger.add_entry("spectrometer",
                              f"Detection limits (device): [{self.wavelengths[0]:.1f} nm ... {self.wavelengths[-1]:.1f} nm]")
        if cfg.WAVELENGTH_CROP_RANGE:
            # get wavelengths corresponding to the limits set in config.py
            self.Xmin_pos = np.searchsorted(self.wavelengths, cfg.WAVELENGTH_MIN)  # index of first wavelength value (float) above WAVELENGTH_MIN
            self.Xmax_pos = np.searchsorted(self.wavelengths, cfg.WAVELENGTH_MAX, side="right")  # index of last wavelength value (float) below WAVELENGTH_MAX
            # all arrays are truncated to stay within crop limits
            self.wavelengths = self.wavelengths[self.Xmin_pos:self.Xmax_pos]
            self.logger.add_entry("spectrometer",
                                  f"Detection limits cropped to: [{self.wavelengths[0]:.1f} nm ... {self.wavelengths[-1]:.1f} nm]")

    def _zero_background_spectrum(self):
        """
        Creates zero-filled background spectrum,
        truncated to [cfg.WAVELENGTH_MIN, cfg.WAVELENGTH_MAX] if cfg.WAVELENGTH_CROP_RANGE == True.
        """
        self.background = np.zeros_like(self.spec.intensities())
        self.backgroundSMA = np.zeros_like(self.background)
        # all arrays are truncated to stay within crop limits
        if cfg.WAVELENGTH_CROP_RANGE:
            self.background = self.background[self.Xmin_pos:self.Xmax_pos]
            self.backgroundSMA = self.backgroundSMA[self.Xmin_pos:self.Xmax_pos]

    def update_integration_time(self):
        """
        Updates integration time of the spectrometer from the value of SpectrometerManager integration_time attribute
        """
        self.spec.integration_time_micros(self.integration_time)
        self.logger.add_entry("spectrometer", f"Integration time = {self.integration_time} us")

    def record_background(self):
        self._waiting_for_background = True

    def _acquire_background_spectrum(self):
        """
        Creates a new background spectrum from a single recorded spectrum,
        truncated to [cfg.WAVELENGTH_MIN, cfg.WAVELENGTH_MAX] if cfg.WAVELENGTH_CROP_RANGE == True.
        """
        self.background = self.spec.intensities()
        self.backgroundSMA = MovingAverage(self.background, self.boxcarSMA)
        # all arrays are truncated to stay within crop limits
        if cfg.WAVELENGTH_CROP_RANGE:
            self.background = self.background[self.Xmin_pos:self.Xmax_pos]
            self.backgroundSMA = self.backgroundSMA[self.Xmin_pos:self.Xmax_pos]
        msg = "New baseline has been recorded"
        self.logger.add_entry("spectrometer", msg)
        self._update_status_label(msg)

    def _acquire_new_spectrum(self):
        """
        Acquires a single recorded spectrum (or an average of NumOfSpectraPerDatapoint spectra),
        truncated to [cfg.WAVELENGTH_MIN, cfg.WAVELENGTH_MAX] if cfg.WAVELENGTH_CROP_RANGE == True.
        Checks for overflow based on saved device limits and cfg.DETECTOR_LINEARITY_LIMIT (set in config.py)
        """
        # record at least 1 spectrum
        i = 1
        self.intensities = self.spec.intensities()  # Spectrometer.intensities() returns a numpy array of Float
        # if NumOfSpectraPerDatapoint > 1, record an average of NumOfSpectraPerDatapoint spectra
        while i < self.NumOfSpectraPerDatapoint:
            self.intensities = np.add(self.intensities, self.spec.intensities())
            i += 1
        if i > 1:
            self.intensities = np.divide(self.intensities, i)
        # mark as overflow if the values fall outside of linearity range
        self.OverflowFlag = math.isclose(self.intensities.max(), cfg.EMISSION_INTENSITY_LIMIT_MAX,
                                         rel_tol=1 - cfg.DETECTOR_LINEARITY_LIMIT)
        self.overflownData.append(self.OverflowFlag)
        self.intensitiesSMA = MovingAverage(self.intensities, self.boxcarSMA)
        # all arrays are truncated to stay within crop limits
        if cfg.WAVELENGTH_CROP_RANGE:
            self.intensities = self.intensities[self.Xmin_pos:self.Xmax_pos]
            self.intensitiesSMA = self.intensitiesSMA[self.Xmin_pos:self.Xmax_pos]

    def _record_time_point(self):
        # TODO: this works for debugging purposes but should be synchronized with experiment timing
        if not self.time0:
            # for the first acquired spectrum, assign time0 (with 0.1s precision)
            self.time0 = round(time.monotonic(), 1)
            print(">>> time0: ", self.time0)
            self.timePoints.append(0)
        else:
            # otherwise, add another time point (with 0.1s precision)
            self.timePoints.append(round(time.monotonic(), 1) - self.time0 - cfg.EXPERIMENT_TOTAL_PAUSE_DURATION_S)

    def _process_acquired_spectrum(self):
        # subtract the stored backgrounds
        self.intensities = np.subtract(self.intensities, self.background)
        self.intensitiesSMA = np.subtract(self.intensitiesSMA, self.backgroundSMA)
        # find lambda_max[nm] for the recorded spectrum
        Ymax_pos = np.argmax(self.intensitiesSMA) - 1
        self.Lmax = round(self.wavelengths[Ymax_pos])
        self.Ymax_position = round(self.intensitiesSMA[Ymax_pos]) # this is accessible attribute to display (Lmax; Ymax_position) marker in plotted spectrum
        self.logger.add_entry("spectrometer",
                              f"New spectrum: max intensity {self.intensitiesSMA[Ymax_pos]:.1f} a.u. at Lmax {self.Lmax:.1f} nm")
        # record the emission data
        if len(self.timePoints) == 0:
            return
        if self.EmissionDetectionMode == cfg.EMISSIONDETECT_SINGLE_WAVELENGTH:
            #   if in single wavelength detection mode, append Ymax to the emissionsData array
            self.emissionData.append(np.max(self.intensitiesSMA))
        elif self.EmissionDetectionMode == cfg.EMISSIONDETECT_INTEGRATE_OVER_WINDOW:
            # get wavelengths indices corresponding to detection_Lmin:detection_Lmax limits
            Lmin_pos = np.searchsorted(self.wavelengths,
                                       self.detection_Lmin)  # index of first wavelength value (float) above detection_Lmin
            Lmax_pos = np.searchsorted(self.wavelengths, self.detection_Lmax,
                                       side="right")  # index of last wavelength value (float) below detection_Lmax
            self.emissionData.append(np.sum(self.intensitiesSMA[Lmin_pos:Lmax_pos]) / (
                        self.detection_Lmax - self.detection_Lmin + 1))  # can also be normalized to the width - discuss with MB
        else:
            # should not arrive here unless config.py is misedited
            self.logger.add_entry("spectrometer", "Unknown detection mode", error=True)
        self.logger.add_entry("spectrometer",
                              f"New emission data point: {self.emissionData[-1]:.1f} a.u. at {self.timePoints[-1]:.1f} s")
        # send the new datapoint to step detector, if an experiment is running and we have data
        if cfg.EXPERIMENT_IS_RUNNING and len(self.timePoints) > 0:
            if cfg.SINGLE_PASS_ANALYSIS:
                self.step_detector.process_full_dataset(self.timePoints, self.emissionData)
            else:
                self.step_detector.add_value(self.timePoints[-1], self.emissionData[-1])
            # self.logger.add_entry("analysis", f"{self.timePoints=} s,\n{self.emissionData=} a.u.")
            steps_detected = len(self.step_detector.steps)
            self.logger.add_entry("analysis", f"{steps_detected} step{'' if steps_detected == 1 else 's'} detected")
            # for step in self.step_detector.steps.values():
            #    self.logger.add_entry("analysis", f"{step.step_t_min=:.1f} s,\n{step.step_t_max=:.1f} s,\n{step.value_average=:.3f} a.u.,\n{step.value_stddev=:.3f} a.u.")


    def _acquire_and_process_spectrum(self):
        """
        Acquires and processes a new spectrum and handles abrupt spectrometer disconnection
        """
        if seabreeze.spectrometers.SeaBreezeDevice.is_open:
            # the device is connected and open
            self._acquire_new_spectrum()
            self._record_time_point()
            self._process_acquired_spectrum()
            # record the current spectrum into the experiment 2D spectrum file if the experiment is running
            if cfg.EXPERIMENT_IS_RUNNING and cfg.SPECTRUM_RECORDED_OK:
                files.spectrum2DFileAddSpectrum(self.timePoints[-1], self.intensitiesSMA)
            # record the current emission datapoint to the emissions over time results file
            if cfg.EXPERIMENT_IS_RUNNING and len(self.timePoints) > 0:
                files.emissionDataSaveDatapoint(self.timePoints[-1], self.emissionData[-1])
        else:
            # the device has been disconnected, will attempt to reconnect in the next data reader loop
            self.spec = None
            self.logger.add_entry("spectrometer", f"Spectrometer has been disconnected!", error=True)

    def _report_spectrometer_status(self):
        """
        Updates GUI status and logger with info on the last acquired spectrum
        """
        now = datetime.now()
        date_time_str = now.strftime("%Y-%m-%d %H:%M:%S")
        time_points_count = len(self.timePoints)
        if time_points_count > 0:
            cfg.SPECTRUM_RECORDED_OK = True  # at least one spectrum has been recorded successfully, can now change spectrometer settings in GUI
            status_text = f"spectrum recorded at {round(self.timePoints[-1], 1)} s"
            if time_points_count > 1:
                status_text += f" (+{round(self.timePoints[-1] - self.timePoints[-2], 1)} s)"
            if self.OverflowFlag:
                status_text += " - OVERFLOW!"
            self.logger.add_entry("spectrometer", status_text)
        else:
            status_text = "spectrum not yet recorded"
            self.logger.add_entry("spectrometer", status_text, error=True)
        self._update_status_label(f"[{date_time_str}]: {status_text}")

#### DataReader class end
