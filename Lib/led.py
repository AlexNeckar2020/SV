from threading import Thread, Event, Lock
from queue import Queue, Empty
from typing import Optional, Callable

import Lib.config as cfg
from Lib.uart import RaspberryPiUART

if (cfg.PLATFORM == cfg.PLATFORM_RASPBERRY_PI) and (cfg.HARDWARE_INTERFACE["LED"] == cfg.LED_OVER_RPI_GPIO):
    import RPi.GPIO as GPIO

class LEDController(RaspberryPiUART):
    """
    Manages a fibre-coupled LED light source controlled over Serial or USB (Custom HID) interface
    """

    def __init__(self, gui_app, logger_handle, uart_name: str):
        # init and logger configuration
        super().__init__(logger_handle)  # initializes the Raspberry Pi UART attributes and makes the logger handle accessible through the parent
        self.gui = gui_app
        self.logger = logger_handle

        # LED status attributes
        # self._LED_is_ON = False
        self._LED_is_ON = (cfg.PLATFORM == cfg.PLATFORM_DEBUG_EMULATION) # do not start with LED "off" if in debug/emulation mode
        self._LED_brightness_percent = 0

        # Do not initialize the UART and the relevant LEDController attributes if LED is controlled manually by user
        if cfg.HARDWARE_INTERFACE["LED"] == cfg.LED_MANUAL_ONLY:
            self.logger.add_entry("LED", f"LED intensity will be controlled manually, {uart_name} will not be initialized")
            return

        # Do not initialize the UART and the relevant LEDController attributes if LED is controlled over GPIO of Raspberry Pi
        # Instead, initialize the PWM on the GPIO pin selected in config.py
        if cfg.HARDWARE_INTERFACE["LED"] == cfg.LED_OVER_RPI_GPIO:
            # Setup hardware
            GPIO.setmode(GPIO.BCM)                      # Use Broadcom pin numbering (GPIOxx)
            GPIO.setup(cfg.LED_RPI_GPIO_PWM_PIN, GPIO.OUT)  # Set GPIOxx as output (see config.py)
            # Start PWM output
            self._pwm = GPIO.PWM(cfg.LED_RPI_GPIO_PWM_PIN, cfg.LED_RPI_GPIO_PWM_FREQ)  # Create PWM instance on the selected GPIOxx
            self._pwm.start(100 - self._LED_brightness_percent)  # signal is inverted when using MOSFET or optocoupler to control the driver PWM input
            self._LED_is_ON = True  # if LED is controlled over GPIO, we assume it's always ON and only the brightness can be adjusted
            self.logger.add_entry("LED", f"LED intensity will be controlled over Raspberry Pi GPIO{cfg.LED_RPI_GPIO_PWM_PIN} at {cfg.LED_RPI_GPIO_PWM_FREQ} Hz")
            return

        # LED controller thread configuration
        self.thread: Optional[Thread] = None
        self._running = False

        # LED UART configuration
        self.uart_name = uart_name
        self.device_name = cfg.UART_DEVICES[uart_name]['name']

        # LED controller queue attributes
        self._response_queue = Queue()
        self._response_lock = Lock()
        self._command_event = Event()

        # AI: Command dispatch mapping
        self._command_dispatch: dict[str, Callable[[str], None]] = {}
        self._register_command_handlers()

        uart_OK = super().initialize_uart(uart_name) # use default configuration (9600 baud, 8N1), no SOP, no EOP
        if uart_OK:
            self.logger.add_entry(uart_name, f"{self.device_name} initialized at {self.serial.baudrate} baud")
            self.start_thread()  # start the LED controller thread if UART has been initialized
        else:
            # TODO: this is actually critical failure if it happens - think how to report it to the user
            self.logger.add_entry(uart_name, f"device '{cfg.UART_DEVICES[uart_name]['device']}' could not be initialized",
                                  error=True)

    def detach(self):
        """
        Terminates the LED controller thread and closes its UART.
        """
        # Do not do anything if LED is controlled manually by user
        if cfg.HARDWARE_INTERFACE["LED"] == cfg.LED_MANUAL_ONLY:
            return
        self.stop_thread()
        super().close_uart()

    def __del__(self):
        try:
            super().close_uart()  # to make sure the corresponding serial port is closed even if the resource was not cleaned manually
        except Exception:
            pass  # ignore exceptions at garbage collection stage

    def start_thread(self):
        """
        Starts the LED controller background thread.
        """
        if not self._running:
            self._running = True
            self.thread = Thread(target=self._thread_loop, daemon=True)
            self.thread.start()

    def stop_thread(self):
        """
        Stops the LED controller thread.
        """
        self._running = False
        if self.thread:
            self.thread.join()

    def _round_integer(self, x: int, base=5):
        return int(base * round(float(x) / base))

    # def _process_newline_char(self, msg: str, NL_stub: str) -> str:
    #     """
    #     Replaces all non-final newline characters in the message with a visible stub string.
    #
    #     :param msg: Raw message string possibly containing newline characters.
    #     :param NL_stub: Visible replacement for newline characters (e.g., '␤').
    #     :return: Cleaned message with final newline stripped and embedded ones replaced.
    #     """
    #     # AI: If there's a final newline, strip it for clean processing
    #     if msg.endswith('\n'):
    #         msg = msg[:-1]
    #         # AI: Replace any remaining (non-final) newlines with the stub
    #         if '\n' in msg:
    #             msg = msg.replace('\n', NL_stub)
    #     else:
    #         # AI: No final newline; treat all as embedded and replace
    #         msg = msg.replace('\n', NL_stub)
    #     return msg

    def _register_command_handlers(self):
        """
        AI: Registers known static and dynamic UART commands and maps them to handling methods.
        """
        self._command_dispatch = {
            "LED ON": lambda _: self._set_led_state(True),
            "LED OFF": lambda _: self._set_led_state(False),
            "UART OK": self._handle_uart_ok,
            "OK": self._handle_ok,
            "?": self._handle_error,
        }

    def _set_led_state(self, state: bool):
        # AI: Updates internal LED on/off status
        self._LED_is_ON = state
        self.logger.add_entry("LED", f"LED manually switched {'ON' if state else 'OFF'}")

    def _handle_ok(self, _: str):
        with self._response_lock:  # AI: Lock used to safely access the shared response queue
            self._response_queue.put("OK")  # AI: Enqueue positive response
            self._command_event.set()  # AI: Signal waiting sender that response has arrived

    def _handle_error(self, _: str):
        with self._response_lock:  # AI: Lock used to safely access the shared response queue
            self._response_queue.put("?")  # AI: Enqueue error response
            self._command_event.set()  # AI: Signal waiting sender that response has arrived

    def _handle_uart_ok(self, _: str):
        with self._response_lock:  # AI: Lock used to safely access the shared response queue
            self._response_queue.put("UART OK")  # AI: Enqueue UART OK signal
            self._command_event.set()  # AI: Signal that reset response arrived

    def _handle_led_brightness(self, command: str):
        """
        AI: Handles brightness commands of the form 'LED <value>' where <value> is expected to be 0-100 in steps of 5.

        :param command: Full command string, e.g., 'LED 50'
        """
        try:
            brightness = int(command.split()[1])
            if 0 <= brightness <= 100 and brightness % 5 == 0:
                self._LED_brightness_percent = brightness
                self.logger.add_entry("LED", f"LED brightness manually adjusted to {brightness}%")
            else:
                corrected = min(max(0, brightness), 100)
                if corrected % 5 != 0:
                    corrected = self._round_integer(corrected)
                self._LED_brightness_percent = corrected
                self.logger.add_entry("LED", f"Unexpected response from the LED controller ({command}), corrected to 'LED {corrected}'", error=True)
        except ValueError:
            self.logger.add_entry("LED", f"Unusual response from the LED controller ({command})", error=True)

    def _thread_loop(self):
        """
        Internal method run by the background thread to handle incoming UART messages.
        """
        while self._running:
            raw_msg = self.read(timeout_ms=1000)
            if raw_msg:
                # AI: Split message into separate commands on newline and process in order
                for command in raw_msg.split('\n'):
                    print(f"_thread_loop((): <<< {command=}")
                    command = command.strip()
                    if not command:
                        continue

                    # AI: Match and dispatch command
                    if command in self._command_dispatch:
                        self._command_dispatch[command](command)
                    elif command.startswith("LED "):
                        self._handle_led_brightness(command)
                    else:
                        self.logger.add_entry("LED", f"Unknown command received: {command}", error=True)

    def _send_LED_brightness_over_UART_and_wait_for_response(self, value: int):
        cmd = f"LED {value}\n"
        print(f"_send_LED_brightness_over_UART_and_wait_for_response(): >>> {cmd=}")
        self.write(cmd.encode())

        self._command_event.clear()  # AI: Clear event before sending command to prepare for new response

        try:
            if self._command_event.wait(timeout=1.0):  # AI: Wait (blocking) up to 1 second
                with self._response_lock:  # AI: Lock used to protect queue access between threads
                    try:
                        response = self._response_queue.get_nowait()  # AI: Attempt to retrieve response without blocking
                        print(f"LED_brightness_percent(): <<< {response=}")
                        if response == "OK":
                            self._LED_brightness_percent = value  # AI: Update internal state on success
                            self.logger.add_entry("LED", f"LED brightness adjusted to {value}%")
                        else:
                            self.logger.add_entry("LED", f"Command rejected by LED controller: '{cmd.strip()}'",
                                                  error=True)
                    except Empty:
                        self.logger.add_entry("LED", "No response in queue from LED controller", error=True)
            else:
                self.logger.add_entry("LED", "Timeout waiting for LED controller response", error=True)
        finally:
            self._command_event.clear()  # AI: Ensure event is cleared in any case


    @property
    def LED_is_ON(self) -> bool:
        """
        Property getter for LED on/off status.
        :return: True if LED is on, False otherwise.
        """
        return self._LED_is_ON


    @property
    def LED_brightness_percent(self) -> int:
        """
        Property getter for current LED brightness level.
        :return: Integer brightness level (0 to 100).
        """
        # Just return the value from config.py if LED is controlled manually by user
        if cfg.HARDWARE_INTERFACE["LED"] == cfg.LED_MANUAL_ONLY:
            self._LED_brightness_percent = int(cfg.LED_INTENSITY*100)
        return self._LED_brightness_percent


    @LED_brightness_percent.setter
    def LED_brightness_percent(self, value: int):
        """
        Property setter for LED brightness. Sends the command "LED <value>\n" and only updates on success.
        :param value: Integer brightness value (0 to 100, step 5).
        """
        if not (0 <= value <= 100 and value % 5 == 0):
            self.logger.add_entry("LED", f"Invalid brightness value requested: {value}", error=True)
            return

        # Pass the value to variables if LED is controlled manually by user
        if cfg.HARDWARE_INTERFACE["LED"] == cfg.LED_MANUAL_ONLY:
            self._LED_brightness_percent = value
            cfg.LED_INTENSITY = value / 100
            return

        # Adjust the PWM value if LED is controlled with RPi 4 GPIO using a custom board
        if cfg.HARDWARE_INTERFACE["LED"] == cfg.LED_OVER_RPI_GPIO:
            self._pwm.ChangeDutyCycle(100 - value)
            self._LED_brightness_percent = value
            cfg.LED_INTENSITY = value / 100
            return

        # Only send the command over UART if no other LED control options were processed above
        self._send_LED_brightness_over_UART_and_wait_for_response(value)



    def reset_LED_controller(self, timeout_s=2.0) -> bool:
        """
        Resets the LED controller by sends the command "RESET\n".
        Waits for up to 1 s to receive "UART OK\n" to confirm that the serial connection has been restored.
        :param timeout_s: response timeout in seconds (blocking the communication thread)
        :return True if the controller has confirmed reconnection, false otherwise.
        """
        # Do not do anything if LED is controlled manually by user
        if (cfg.HARDWARE_INTERFACE["LED"] == cfg.LED_MANUAL_ONLY) or (cfg.HARDWARE_INTERFACE["LED"] == cfg.LED_OVER_RPI_GPIO):
            return True

        cmd = f"RESET\n"
        self.write(cmd.encode())
        print(f"reset_LED_controller(): >>> {cmd=}")
        self._command_event.clear()  # Clear event before sending command to prepare for new response
        result = False

        try:
            if self._command_event.wait(timeout=timeout_s):  # Wait (blocking) up to timeout_s seconds
                with self._response_lock:  # Lock used to protect queue access between threads
                    try:
                        response = self._response_queue.get_nowait()  # Attempt to retrieve response without blocking
                        print(f"reset_LED_controller(): <<< {response=}")
                        if response == "UART OK":
                            self.logger.add_entry("LED", "LED controller reset and reconnected")
                            result = True
                        else:
                            self.logger.add_entry("LED", f"Unexpected response from LED controller upon reset ({response})",
                                                  error=True)
                    except Empty:
                        self.logger.add_entry("LED", f"Connection with LED controller not confirmed upon reset", error=True)
            else:
                self.logger.add_entry("LED", f"No response from LED controller upon reset (timeout > {timeout_s:.1f} s)", error=True)
        finally:
            self._command_event.clear()  # AI: Ensure event is cleared in any case
        return result
