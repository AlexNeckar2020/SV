from pathlib import Path

"""Platform and hardware selection options"""
# Platform selection options
PLATFORM_MS_WINDOWS = 0 # tested on Windows 10 and 11
PLATFORM_RASPBERRY_PI = 1 # tested on Raspberry Pi 4B
PLATFORM_DEBUG_EMULATION = 2 # for testing, debugging and further development purposes
# The platform is selected here:
PLATFORM = PLATFORM_MS_WINDOWS

# LED control hardware configuration options
LED_MANUAL_ONLY = 0 # LED is not controlled from the software but by manual LED CC driver, e.g. SLA-1000-2 from Mightex:
                    # https://www.mightexsystems.com/product/sla-series-two-channel-led-drivers-with-manual-and-analog-input-controls/
LED_OVER_SERIAL = 1 # LED is controlled from the software using a custom CC driver board through a serial port (e.g., COMx on PC, /dev/ttyUSBx on Raspberry Pi)
                    # Repository: https://github.com/AlexNeckar2020/SV-hardware/LEDdriver-C031K6T6-Serial (RS232 with DB9 9-pin connector - needs a USB-to-RS232 adapter)
                    # Repository: https://github.com/AlexNeckar2020/SV-hardware/LEDdriver-C071KBT6-USBVCP (with a virtual COM port over USB)
                    # Repository: https://github.com/AlexNeckar2020/SV-hardware/LEDdriver-RS232Board-USBVCP (with 4x virtual COM port over USB, can be used together with PUMPS_OVER_SERIAL option)
LED_OVER_RPI_GPIO = 2 # LED is controlled from the software together with the pumps directly by Raspberry Pi,
                      # using a custom controller board:
                      # Repository: https://github.com/AlexNeckar2020/SV-hardware/LEDdriver-RS232BoardRPi
# Pumps control hardware configuration options
PUMPS_OVER_SERIAL = 0 # Pumps are controlled over 3x serial ports (e.g., COMx on PC, /dev/ttyUSBx on Raspberry Pi) using a 4-port USB to DB9 RS232 serial adapter hub,
                      # e.g. ICUSB2324 or ICUSB2324I from StarTech.com: https://www.startech.com/en-de/cards-adapters/icusb2324i
                      # Suitable both for Windows and Raspberry Pi platform; this option is also to be chosen with NE-1000 pump emulator
PUMPS_OVER_RPI_UARTS = 1 # Pumps are controlled from the software together with LED directly by Raspberry Pi,
                         # using a custom controller board:
                         # Repository: https://github.com/AlexNeckar2020/SV-hardware/LEDdriver-RS232BoardRPi
                         # Suitable only for Raspberry Pi platform (should be used together with LED_OVER_RPI_GPIO option)
# Pumps and LED control hardware is selected here:
HARDWARE_INTERFACE = {"LED": LED_OVER_SERIAL,
                      "PUMPS": PUMPS_OVER_SERIAL}

"""Global constants"""
# Main window geometry
MAINWINDOW_POSITION_X = 100
MAINWINDOW_POSITION_Y = 100
MAINWINDOW_SIZE_WIDTH = 800
MAINWINDOW_SIZE_HEIGHT = 500 # 450
MAINWINDOW_LEFTFRAME_WIDTH = 200
if PLATFORM == PLATFORM_RASPBERRY_PI:
    PUMPSETTINGSWINDOW_SIZE_WIDTH = 550
    PUMPSETTINGSWINDOW_SIZE_HEIGHT = 150
else:
    PUMPSETTINGSWINDOW_SIZE_WIDTH = 500
    PUMPSETTINGSWINDOW_SIZE_HEIGHT = 135  

# emission detection mode options
EMISSIONDETECT_SINGLE_WAVELENGTH = 1
EMISSIONDETECT_INTEGRATE_OVER_WINDOW = 2
MAX_SPECTRA_PER_DATAPOINT = 50
MAX_BOXCAR_SIZE = 100
DETECTOR_LINEARITY_LIMIT = 0.9

# default timings for spectrometer
DATA_READER_THREAD_LOOP_DELAY = 0.1 # 100 ms delay per data reader thread loop (in paused state)
RECONNECT_DELAY_S = 1
DEFAULT_ACQUISITION_DELAY_MS = 3000
MIN_ACQUISITION_DELAY_MS = 100
MAX_ACQUISITION_DELAY_MS = 10000

# default data analysis settings
ANALYSIS_RMS_TOLERANCE = 500   # Threshold for emission signal data stability check
ANALYSIS_WINDOW_SIZE = 10      # Sliding window size
ANALYSIS_MAX_OUTLIERS = 3      # Max allowed sequential outliers
ANALYSIS_MIN_STEP_DURATION = 5 # Minimum duration for a valid step
SINGLE_PASS_ANALYSIS = False   # True if analysis parameters window is open and reanalyze() method is being used

# default file names and locations
BASE_DIR = Path(__file__).resolve().parent.parent   # root folder with SV.py
LOGS_DIR = BASE_DIR / "logs"
RESULTS_DIR = BASE_DIR / "results"
RESOURCES_DIR = BASE_DIR / "Rsc"
SYRINGES_CSV_FILE = RESOURCES_DIR / "syringes.csv"
SAMPLE_SPECTRUM_CSV_FILE = RESOURCES_DIR / "4CzIPN-EtOH.csv"

# logger options
LOG_WINDOW = 0 # logger output into log window
LOG_FILE = 1 # logger output into log file
LOG_UART = 2 # logger output into UART0
LOG_CONSOLE = 3 # logger output into Python console via print()
LOGGER_MODE = {LOG_CONSOLE, LOG_FILE} # set containing none, one, several or all of the logger options above
LOG_FILE_CSV = 0 # file logger: log into a tab-delimited .CSV file
LOG_FILE_HTML = 1 # file logger: log into an HTML file with a scrollable table
LOG_FILE_TYPE = LOG_FILE_HTML # type of output log file
LOG_UART_NEWLINE = '\n' # Suggested end-of-line character(s) for UART logger: Linux: '\n' (LF, 0x0A), DOS/Windows: '\r\n' (CR+LF, 0x0D+0x0A)

# UART options
SERIAL_DEBUG_BAUDRATE = 9600
SYRINGE_PUMP_BAUDRATE = 19200
UART_STATE_READY = 0        # UART is available for a new query
UART_STATE_BUSY = 1         # UART is currently processing a query
UART_STATE_TIMEOUT = 2      # The last query ended in a timeout

if PLATFORM == PLATFORM_RASPBERRY_PI:
    UART_DEVICES = {  # GPIO configuration for Raspberry Pi 4B:
                        "UART0": { "device": "/dev/ttyS0", "name": "Serial/Debug"},  # UART0: RX on pin 10 (GPIO16), TX on pin 8 (GPIO15) (/dev/serial0 is alias for /dev/ttyS0 or /dev/ttyAMA0)
                        "UART3": { "device": "/dev/ttyAMA3", "name": "Pump1 (Solvent)"}, # UART3: RX on pin 29 (GPIO21), TX on pin 7 (GPIO7)
                        "UART4": { "device": "/dev/ttyAMA4", "name": "Pump2 (Catalyst)"},  # UART4: RX on pin 21 (GPIO13), TX on pin 24 (GPIO10)
                        "UART5": { "device": "/dev/ttyAMA5", "name": "Pump3 (Quencher)"}   # UART5: RX on pin 33 (GPIO23), TX on pin 32 (GPIO26)
                   }
elif PLATFORM == PLATFORM_MS_WINDOWS:
    UART_DEVICES = {  # for Windows on PC, UART devices communicate over COM ports with names "COMxx" or "\Device\yyyyy"
                      # use command "chgport" or "mode" to retrieve this information
                      # Here is a sample configuration using a USB to 4x RS232 bridge (StarTech.com ICUSB2324I) for 3x pumps and LED:
                      # Windows driver assigns the first available COM port numbers to the bridge, COM5-COM8 in this example:
                      # COM90 <-> COM80 pipe is configured in null-modem emulator (com0com), so that all debug UART traffic can be read at COM80
                      "UART0": { "device": "COM90", "name": "Serial/Debug"},
                      "UART3": { "device": "COM7", "name": "Pump1 (Solvent)"},
                      "UART4": { "device": "COM9", "name": "Pump2 (Catalyst)"},
                      "UART5": { "device": "COM10", "name": "Pump3 (Quencher)"},
                      "UART6": { "device": "COM8", "name": "LED serial controller"}
                   }
elif PLATFORM == PLATFORM_DEBUG_EMULATION:
    UART_DEVICES = {  # for Windows on PC, with 3x NE-1000 pump emulators and 3x com0com pipes running
                      "UART0": { "device": "NUL", "name": "Serial/Debug"},
                      "UART3": { "device": "COM90", "name": "Pump1 (Solvent)"}, # <-> COM80
                      "UART4": { "device": "COM91", "name": "Pump2 (Catalyst)"}, # <-> COM81
                      "UART5": { "device": "COM92", "name": "Pump3 (Quencher)"}, # <-> COM82
                      "UART6": { "device": "COM8", "name": "LED serial controller"}
                   }
else:
    raise OSError(f"Unknown platform requested: PLATFORM value set to {PLATFORM}\n{' ':>9}See 'Platform selection options' in config.py for permitted values.")

# LED options
LED_UART = "UART6"
LED_RPI_GPIO_PWM_PIN = 19   # GPIO19 (pin 35 of the 40-pin connector) supports software PWM
LED_RPI_GPIO_PWM_FREQ = 250 # 250 Hz frequency (100...500 Hz recommended for LDD-1000L Meanwell 1A LED CC driver)

# pump options
PUMP_SOLVENT = 0
PUMP_CATALYST = 1
PUMP_QUENCHER = 2
PUMP_UARTS = {PUMP_SOLVENT: "UART3", PUMP_CATALYST: "UART4", PUMP_QUENCHER: "UART5"}
PUMP_NAMES = {PUMP_SOLVENT: "Pump1 (Solvent)", PUMP_CATALYST: "Pump2 (Catalyst)", PUMP_QUENCHER: "Pump3 (Quencher)"}
PUMP_VOLUME_UNITS_MILLILITERS = "ML"
PUMP_VOLUME_UNITS_MICROLITERS = "UL"
PUMP_DIRECTION_INFUSE = 0
PUMP_DIRECTION_WITHDRAW = 1
PUMP_STATE_DISCONNECTED = 0
PUMP_STATE_STOPPED = 1
PUMP_STATE_RUNNING = 2
PUMP_STATE_PAUSED = 3
PUMP_STATE_ERROR = 4
PUMP_MAX_COMMAND_RETRY_ATTEMPTS = 3
PUMP_MAX_ALLOWED_COMMAND_QUEUE_LENGTH = 3
PUMP_MAX_RESPONSE_WAITING_TIME_MS = 1000
LOG_PUMP_COMMANDS_AND_RESPONSES = {PUMP_SOLVENT, PUMP_CATALYST, PUMP_QUENCHER} # individual pumps {PUMP_SOLVENT, ...} can be added to track their UART data exchange
LOG_PUMP_IGNORE_POLLING = True # do not log UART data exchanged over polling requests

# pump scheduler and controller options
PUMP_PRIMING_ORDER = [PUMP_CATALYST, PUMP_QUENCHER, PUMP_SOLVENT] # order of priming in the priming sequence
PUMP_SCHEDULER_THREAD_LOOP_DELAY = 0.01 # 10 ms delay per pump scheduler thread loop
PUMP_PRIMING_STEP_DELAY = 0.3 # 300 ms delay between all steps of pump priming sequence
PUMP_EXPERIMENT_STEP_DELAY = PUMP_PRIMING_STEP_DELAY
PUMP_STOPPING_DELAY = PUMP_PRIMING_STEP_DELAY
PUMP_INIT_STEP_DELAY = 0.5 # 500 ms delay between all steps of pump initialization sequence
PUMP_CLOSE_STEP_DELAY = 0.3 # 300 ms delay between all steps of pump close/detach sequence
PUMP_POLLING_INTERVAL = 1.0 # poll pump states during scheduler runs to check for errors and abort if needed
PUMP_POST_EXPERIMENT_PADDING_TIME_S = 2.0

# pump scheduler states: either idle or the reason of it being started by PumpController
PUMP_SCHEDULER_IDLE = 0
PUMP_SCHEDULER_PAUSED = 1
PUMP_SCHEDULER_PRIMING = 2
PUMP_SCHEDULER_RUNNING_EXPERIMENT = 3

# detailed debug flags
DEBUG_PUMP_SCHEDULER = False
DEBUG_PUMP_CONTROLLER = False
EMULATE_SPECTROMETER = False

# log color scheme
logColorScheme = {
    "UART0": "#ffffff",            # white
    "UART3": "#ffff00",            # yellow
    "UART4": "#90ee90",            # lightgreen
    "UART5": "#add8e6",            # lightblue
    "uart": "#cccccc",             # gray80
    "gui": "#cccccc",              # gray80
    "files": "#cccccc",            # gray80
    "LED": "#1e90ff",              # dodgerblue
    "spectrometer": "#dda0dd",     # plum1
    "analysis": "#ee00ee",         # magenta2
    "scheduler": "#ffa500",        # orange
    "controller": "#ffa500",       # orange
    "debug:scheduler": "#f7cba1",  # custom light orange
    "debug:controller": "#f7cba1", # custom light orange
    "error": "#ff0000"             # red
}

# GUI options
guiColorScheme = {"buttons":
                      {# HomePage
                       "btnSpectrometerLED": {"bg": "ghost white", "fg": "black"},
                       "btnBaseline": {"bg": "gray70", "fg": "black"},
                       "btnLoadExperiment": {"bg": "PaleGreen2", "fg": "black"},
                       "btnPumps": {"bg": "sky blue", "fg": "black"},
                       "btnStartPauseExperiment": {"bg": "light goldenrod", "fg": "black"},
                       "btnStopExperiment": {"bg": "firebrick1", "fg": "black"},
                       "btnAnalysisParameters": {"bg": "orchid1", "fg": "black"},
                       "btnViewLog": {"bg": "gray10", "fg": "white"},
                       # MessageBoxConfirmExitWindow
                       "yes_button": {},
                       "no_button": {},
                       # PumpSettingsWindow
                       "btnPrimePumps": {"bg": "sky blue", "fg": "black"}
                       # SpectrometerPage
                          # "btnUpdateSettings"
                          # "btnReturn"
                      },
                  "statusPumpStatusColors": ["gray60", "dodger blue", "lawn green", "yellow", "red"] # PUMP_STATE_DISCONNECTED, PUMP_STATE_STOPPED, PUMP_STATE_RUNNING, PUMP_STATE_PAUSED, PUMP_STATE_ERROR
                 }
GUI_SAVEIMAGE_OUTPUT_DPI = 300
GUI_PLOT_UPDATE_INTERVAL_MS = 500

""" Global variables """
LED_INTENSITY: float = 1.0
WAVELENGTH_MIN = 200
WAVELENGTH_MAX = 900
WAVELENGTH_CROP_RANGE: bool = True
INTEGRATION_TIME_US_MIN = None # will be filled with the value read from spectrometer
INTEGRATION_TIME_US_MAX = None # will be filled with the value read from spectrometer
EMISSION_INTENSITY_LIMIT_MAX = None # Float; will be filled with the value read from spectrometer
ALLOW_SPECTROMETER_STATUS_UPDATES: bool = True # will be set to False to suppress spectrometer status updates during priming?
SPECTROMETER_CONNECTED_OK: bool = False # will be set ot True once spectrometer is connected
SPECTRUM_RECORDED_OK: bool = False # will be set to True once the first spectrum is recorded, reset to False if the DataReader is restarted
EXPERIMENT_LOADED_OK: bool = False
EXPERIMENT_IS_RUNNING: bool = False
EXPERIMENT_IS_PAUSED: bool = False
PUMPS_PRIMED_OK: bool = False # will be set to True once priming is successful
EXPERIMENT_FINISHED_OK: bool = False # will be set to True once the experiment run finished successfully
EXPERIMENT_TOTAL_PAUSE_DURATION_S: float = 0.0 # total delay incurred by all pause/restart experiment delays to synchronize spectrometer with pump scheduler
