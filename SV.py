from Lib.gui import MainWindow
from Lib.spectrometer import DataReader
from Lib.logger import Logger
from Lib.pumps import PumpController
from Lib.led import LEDController
import Lib.config as cfg

# main()
app = MainWindow()
logger = Logger(app)
data_reader = DataReader(app, logger)
pump_controller = PumpController(app, logger, cfg.LOG_PUMP_COMMANDS_AND_RESPONSES)
LED_controller = LEDController(app, logger, cfg.LED_UART)
app.link_data_reader(data_reader)
app.link_logger(logger)
app.link_pump_controller(pump_controller)
app.link_LED_controller(LED_controller)
logger.add_entry("SV", "|-> Starting the main application...")
data_reader.start()
app.mainloop()
