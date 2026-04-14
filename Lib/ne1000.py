""" This code was developed with assistance from ChatGPT (OpenAI, 2025) """

from dataclasses import dataclass
from typing import Optional, Callable, Any
import queue
import time
from math import isclose
from threading import Thread

import Lib.config as cfg
from Lib.uart import RaspberryPiUART

@dataclass
class PumpResponse:
    """
    Represents a parsed pump response.
    """
    address: Optional[int] # pump address on the network, expected to be 0x00, unless the pumps are chained on the same serial port
    status: Optional[str] # one-letter pump status, see _ne1000_status for options
    data: Optional[str] # remaining pump response string past the status char
    error: Optional[str] # remaining pump response string past the question mark, see _ne1000_error for options

@dataclass
class PumpCommand:
    """
    Represents a command to be sent to the NE-1000 syringe pump and the stored pump response (a single queue entry).
    """
    # TODO: rethink value_to_confirm - we must be able to compare both string and floats!!
    name: str
    base_code: str
    expects_confirmation: bool = False
    value_to_confirm: Optional[str] = None
    retry_code: Optional[str] = None
    value: Optional[str] = None
    unit: Optional[str] = None
    retries_left: int = cfg.PUMP_MAX_COMMAND_RETRY_ATTEMPTS
    response_action: Optional[Callable[[Any], bool]] = None
    response_result: Optional[PumpResponse] = None

    def format(self, currentPumpState: int) -> str:
        """
        Assembles the full command string to be sent to the pump.
        Handles substitution of value and unit placeholders.
        """
        if self.value:
            # RAT command requires modification if no value is given
            if self.base_code == "RAT":
                if currentPumpState == cfg.PUMP_STATE_RUNNING:
                    return f"{self.base_code} C {self.value}"
                else:
                    return f"{self.base_code} {self.value}{self.unit}"
            # standard processing for all other commands
            if self.unit:
                return f"{self.base_code} {self.value}{self.unit}"
            else:
                return f"{self.base_code} {self.value}"
        else:
            if self.unit:
                return f"{self.base_code} {self.unit}"
            else:
                return self.base_code

    def decrement_retries(self) -> bool:
        """
        Decrements the retry counter and returns True if more retries are allowed.
        """
        self.retries_left -= 1
        return self.retries_left > 0


class SyringePump(RaspberryPiUART):
    """
    NE-1000 Syringe Pump interface with command queue, retry logic, pump state value and busy flag.
    """

    _ne1000_error = {"OOR": "value out of range",
                     "NA": "not applicable (pump is running?)",
                     "COM": "communication error",
                     "IGN": "command ignored by the pump",
                     "": "unknown command",
                     "R": "pump reset (power failure?)",
                     "S": "pump stalled",
                     "T": "safe mode communication timeout",
                     "E": "pumping program error",
                     "O": "pumping program phase out of range"
                     }  # dictionary for logging NE1000 errors and alarms
    _ne1000_status = {"I": "INFUSE",
                      "W": "WITHDRAW",
                      "P": "PAUSED",
                      "S": "STOPPED",
                      "T": "TIMED PHASE",
                      "U": "USER WAIT",
                      "X": "PURGE",
                      "A": "ALARM"
                      } # dictionary for logging NE1000 pump statuses
    _ne1000_units = {"ML": "mL",
                     "UL": "\u03BCL",  # microliters
                     "MM": "mL/min",
                     "MH": "mL/h",
                     "UM": "\u03BCL/min",  # microliters/min
                     "UH": "\u03BCL/h"  # microliters/h
                     } # dictionary for logging NE1000 unit abbreviations

    def __init__(self, logger_handle, uart_name: str, log_commands=False):
        # init and logger configuration
        super().__init__(logger_handle)  # initializes the Raspberry Pi UART attributes and makes the logger handle accessible through the parent
        self.log_commands = log_commands  # this flag is set if outgoing commands are to be logged
        # pump thread configuration
        self.thread: Optional[Thread] = None
        self.running = False # thread loop is running
        # pump state and command communication configuration
        self.pumpState = cfg.PUMP_STATE_DISCONNECTED
        self.pumpFlowRate: float = 0.0 # current pumping rate in mL/min, continuously updated for restoring when controller is paused
        self.command_queue: queue.Queue[PumpCommand] = queue.Queue(maxsize=cfg.PUMP_MAX_ALLOWED_COMMAND_QUEUE_LENGTH)
        self.busy = False
        self._ne1000_commands = {
            "poll": {"code": "", "action": self._handle_poll},
            "reset": {"code": "* RESET", "action": self._handle_reset},
            "get_version": {"code": "VER", "action": self._handle_get_version},
            "set_diameter": {"code": "DIA", "action": self._handle_set_diameter},
            "set_volume": {"code": "VOL", "action": self._handle_set_volume},
            "set_volume_units": {"code": "VOL", "action": self._handle_set_volume_units},
            "set_pumping_rate": {"code": "RAT", "action": self._handle_set_pumping_rate},
            "set_pumping_direction": {"code": "DIR", "action": self._handle_set_pumping_direction},
            "run": {"code": "RUN", "action": self._handle_run},
            "stop": {"code": "STP", "action": self._handle_stop},
        }
        # pump UART configuration
        self.uart_name = uart_name
        self.pump_name_str = cfg.UART_DEVICES[uart_name]['name'] # does not change after initialization
        uart_OK = super().initialize_uart(uart_name, baudrate=cfg.SYRINGE_PUMP_BAUDRATE, start_packet_byte=0x02,
                                          end_packet_byte=0x03)
        if uart_OK:
            self.logger.add_entry(uart_name,
                                  f"{cfg.UART_DEVICES[uart_name]['name']}, initialized at {cfg.SYRINGE_PUMP_BAUDRATE} baud")
            self.start_thread()  # start the pump thread if UART has been initialized
        else:
            # TODO: this is actually critical failure if it happens - think how to report it to the user
            self.logger.add_entry(uart_name, f"device {cfg.UART_DEVICES[uart_name]['device']} could not be initialized",
                                  error=True)

    def start_thread(self):
        """
        Start sending commands and receiving pump data in a separate thread.
        """
        if self.thread and self.thread.is_alive():  # check if not starting an already existing thread
            self.logger.add_entry(self.uart_name,
                                  f"{self.pump_name_str}: start() reentered: Pump thread is already running!",
                                  error=True)
            return
        self.running = True
        self.thread = Thread(target=self._process_commands, daemon=True)
        self.thread.start()
        self.logger.add_entry(self.uart_name, f"{self.pump_name_str}: Pump thread started")

    def _purge_command_queue(self):
        """
        Safely and immediately purges the command queue.
        """
        while not self.command_queue.empty():
            try:
                self.command_queue.get_nowait()
                self.command_queue.task_done()
            except queue.Empty:
                break

    def stop_thread(self):
        """
        Stops processing remaining commands, purges the queue and terminates the thread.
        """
        self.running = False
        self._purge_command_queue()
        if self.thread and self.thread.is_alive():
            self.thread.join()
        self.logger.add_entry(self.uart_name, f"{self.pump_name_str}: Pump thread stopped")

    def detach(self):
        """
        Terminates the pump's thread and closes its UART.
        """
        self.stop_thread()
        super().close_uart()

    def __del__(self):
        try:
            super().close_uart()  # to make sure the corresponding serial port is closed even if the resource was not cleaned manually
        except Exception:
            pass  # ignore exceptions at garbage collection stage

    def _parse_pump_response(self, response_raw: str, response_parsed: PumpResponse):
        """
        Parses pump response into the PumpResponse dataclass instance, filling either the "data" or "error" key
        :param response_raw: raw response string returned by the pump
        """
        response_parsed.address = int(response_raw[:2], 10)
        response_parsed.status = response_raw[2]
        if '?' in response_raw:
            _, _, err = response_raw.partition('?')
            response_parsed.error = err
            response_parsed.data = None
        else:
            response_parsed.data = response_raw[3:]
            response_parsed.error = None


    def _parse_value_with_unit(self, s: str) -> tuple[float, str]:
         unit = s[-2:]
         if unit.isalpha():
             value = float(s[:-2])
         else:
             unit = ""
             value = float(s)
         return value, unit


    def _process_commands(self):
        """
        Pump thread loop function, handling sending and receiving pump commands over UART (with blocking)
        and choosing suitable action depending on the parsed response.
        """
        while self.running:
            try:
                # retrieve next command from the pump command queue, if the last has been processed successfully
                cmd: PumpCommand = self.command_queue.get(timeout=0.5)
            except queue.Empty:
                # run empty loop as long as the queue is empty
                self.busy = False
                time.sleep(0.01)
                continue

            cmd_action_success = False
            while not cmd_action_success and cmd.retries_left > 0:
                # convert current PumpCommand instance from the queue into the formatted pump command string and send it to the pump's UART
                cmd_formatted = cmd.format(self.pumpState) # format the command as: "base_code [value][units]"
                self.write(cmd_formatted + '\r')
                # log outgoing command if the option is enabled
                if self.log_commands:
                    if cmd.name != "poll" or not cfg.LOG_PUMP_IGNORE_POLLING:  # do not log polling if the debug flag is not set
                        self.logger.add_entry(self.uart_name, f"<<< {cmd_formatted} ({cmd.name})")
                # wait for response holding the thread until the permitted timeout (1 s for now)
                time0 = time.time()
                pump_response_str = self.read(cfg.PUMP_MAX_RESPONSE_WAITING_TIME_MS)
                pump_response_delay_ms = (time.time() - time0) * 1000.0
                # log incoming command if the option is enabled
                # TODO: here, no response within 1 s can also be reported
                if self.log_commands and pump_response_str:
                    if cmd.name != "poll" or not cfg.LOG_PUMP_IGNORE_POLLING:  # again, do not log polling if the debug flag is not set
                        self.logger.add_entry(self.uart_name, f">>> {cmd.name} took {round(pump_response_delay_ms, 2)} ms, response: {pump_response_str}")
                self._parse_pump_response(pump_response_str, cmd.response_result) # filling the self.pump_response with pump response values

                if cmd.response_action:
                    try:
                        cmd_action_success = cmd.response_action(cmd)
                    except Exception as e:
                        handler_name = getattr(cmd.response_action, '__name__', str(cmd.response_action)) # retrieving the name of the failed _handle_... method
                        self.logger.add_entry(self.uart_name, f"Unhandled exception {e} in {handler_name}", error=True)

                if not cmd_action_success and not cmd.decrement_retries():
                    # TODO: Queued command failed on max retries: this is a critical error and should be reported up to interrupt the current sequence
                    self.logger.add_entry(self.uart_name, f"Command '{cmd.name}' failed after retries", error=True)
                    break

            self.command_queue.task_done()
            self.busy = not self.command_queue.empty()


    def _enqueue_command(self, command_name: str, value: Optional[str] = None, unit: Optional[str] = None):
        ne1000_command = self._ne1000_commands[command_name]
        cmd = PumpCommand(
            name=command_name,
            value=value,
            unit=unit,
            base_code=ne1000_command["code"],
            response_action=ne1000_command["action"],
            response_result=PumpResponse(None, None, None, None)
        )
        try:
            self.command_queue.put_nowait(cmd)
            self.busy = True
        except queue.Full:
            # TODO: Queue overflow: this is a critical error and should be reported up to interrupt the current sequence
            self.logger.add_entry(self.uart_name, f"{self.pump_name_str} command queue overflow, could not enqueue '{command_name}'", error=True)

    def get_state(self):
        return self.pumpState

    def poll(self):
        """
        Polls the associated NE1000 for the response with empty command, requesting its current state.
        """
        self._enqueue_command("poll")

    def reset(self):
        """
        Resets the associated NE1000 pump to default settings, stops the current program.
        Caution as it will also switch the volume units to uL.
        """
        self._enqueue_command("reset")

    def get_version(self):
        """
        Requests the model and firmware version from NE1000 pump, the data are sent to the logger but not stored.
        """
        self._enqueue_command("get_version")

    def run(self):
        """
        Turns on NE1000 pumping, with direction as set by set_pumping_direction() (default: infuse).
        """
        self._enqueue_command("run")

    def stop(self):
        """
        Turns off NE1000 pump motor, switching it into PAUSED state.
        Calling it again switches the pump into STOPPED state.
        """
        self._enqueue_command("stop")

    def set_diameter(self, diameter_mm: float):
        """
        Sets the syringe diameter for the associated NE1000 pump.
        The command will fail if the pump is in RUNNING state.
        :param diameter_mm: Syringe plunger diameter (in mm).
        """
        # if self.pumpState == cfg.PUMP_STATE_RUNNING: <--- do not do this by default with the proper command queue!
        #    self.stop() # pause pump first if it is running
        self._enqueue_command("set_diameter", value=format(round(diameter_mm, 2), ".2f")) # diameter rounded to 0.01 mm with tailing zeros, no units required
        # NB: the tailing zeros are needed to be able to compare the requested value with pump response directly as strings

    def set_volume_units(self, volume_units: str = "ML"):
        """
        Sets the volume units for the associated NE1000 pump.
        The possible volume units are defined as PUMP_VOLUME_UNITS_MILLILITERS and PUMP_VOLUME_UNITS_MICROLITERS in config.py.
        The command will fail if any unit name string other than "ML" or "UL" is passed, so no need for additional checks.
        :param volume_units: "ML" for volumes in mL, "UL" for volumes in uL (use constants from config.py).
        """
        self._enqueue_command("set_volume_units", unit=volume_units)

    def set_volume(self, volume_mL: float):
        """
        Sets the volume to be delivered by the associated NE1000 pump.
        The command will fail if the pump is in RUNNING state.
        :param volume_mL: Volume to be infused or withdrawn (in mL).
        """
        self._enqueue_command("set_volume", value=format(round(volume_mL, 2), ".2f"))  # volume rounded to 0.01 mL with tailing zeros, no units required
        # NB: the tailing zeros are needed to be able to compare the requested value with pump response directly as strings

    def set_pumping_rate(self, rate_mL_min: float):
        """
        Sets the pumping rate for the associated NE1000 pump.
        :param rate_mL_min: Pumping rate (in mL/min); other units are not processed.
        """
        self._enqueue_command("set_pumping_rate", value=format(round(rate_mL_min, 2), ".3f"), unit="MM")  # rate rounded to 0.010 mL/min with tailing zeros, with no units required
        # NB: the tailing zeros are needed to be able to compare the requested value with pump response directly as strings

    def set_pumping_direction(self, direction: int):
        """
        Sets the pumping direction for the associated NE1000 pump.
        (withdraw mode is not useful for the experiment, but may potentially be implemented for syringe refill)

        :param direction: infuse (cfg.PUMP_DIRECTION_INFUSE) or withdraw (cfg.PUMP_DIRECTION_WITHDRAW) mode.
        """
        if direction == cfg.PUMP_DIRECTION_WITHDRAW:
            direction_parameter = "WDR"
        else:  # "REV" and "STK" options will not be processed
            direction_parameter = "INF"
        # the direction parameter will be passed as value
        self._enqueue_command("set_pumping_direction", value=direction_parameter)

    def _handle_poll(self, current_pump_command: PumpCommand) -> bool:
        """
        Handles the parsed response to polling the pump with an empty command.
        Updates internal pump state based on the status code in the response.
        """
        status = current_pump_command.response_result.status
        if status in {'I', 'W', 'X'}:
            self.pumpState = cfg.PUMP_STATE_RUNNING
        elif status == 'S':
            self.pumpState = cfg.PUMP_STATE_STOPPED
        elif status == 'P':
            self.pumpState = cfg.PUMP_STATE_PAUSED
        elif status == 'A':
            self.pumpState = cfg.PUMP_STATE_ERROR
        else:
            self.logger.add_entry(self.uart_name,
                                  f"{self.pump_name_str}: pump is polled in unusual state",
                                  error=True)
            return False
        return True

    def _handle_reset(self, current_pump_command: PumpCommand) -> bool:
        """
        Handles the parsed response to reset command
        """
        pump_response: PumpResponse = current_pump_command.response_result
        if (pump_response.address != 0) or (pump_response.status != "S"):
            # the response has unexpected structure, log the error and repeat the command
            self.logger.add_entry(self.uart_name,
                                  f"{self.pump_name_str}: could not reset the pump, retrying...",
                                  error=True)
            # self.pumpState = cfg.PUMP_STATE_ERROR
            return False
        self.logger.add_entry(self.uart_name,
                              f"{self.pump_name_str}: reset to address 00, pump stopped")
        self.pumpState = cfg.PUMP_STATE_STOPPED
        return True

    def _handle_get_version(self, current_pump_command: PumpCommand) -> bool:
        """
        Handles the parsed response to get_version command
        """
        pump_response_data = current_pump_command.response_result.data
        if 'V' in pump_response_data:
            # the response has the expected structure, log it
            model, _, firmware_ver = pump_response_data.partition('V')  # split at 'V'
            self.logger.add_entry(self.uart_name,
                                  f"{self.pump_name_str}: model {model}, firmware version {firmware_ver}")
            return True
        else:
            # the response has unexpected structure, log the crude response string and repeat the command
            self.logger.add_entry(self.uart_name,
                                  f"{self.pump_name_str}: unexpected response to VER",
                                  error=True)
            return False

    def _handle_run(self, current_pump_command: PumpCommand) -> bool:
        """
        Handles the parsed response to run command
        """
        pump_response_status = current_pump_command.response_result.status
        if pump_response_status in {'I', 'W'}:  # the expected response is the direction in status char
            self.logger.add_entry(self.uart_name,
                                  f"{self.pump_name_str}: pump is running (mode: {self._ne1000_status[pump_response_status]})")
            self.pumpState = cfg.PUMP_STATE_RUNNING
            return True
        elif pump_response_status == 'A':  # the pump responded with an alarm
            pump_response_error_meaning = self._ne1000_error.get(current_pump_command.response_result.error, "unknown error")
            self.logger.add_entry(self.uart_name,
                                  f"{self.pump_name_str}: could not start the pump ({pump_response_error_meaning})",
                                  error=True)
        else:
            try:  # otherwise, something is wrong and we report either the received status (stopped, paused etc.)
                self.logger.add_entry(self.uart_name,
                                      f"{self.pump_name_str}: pump is NOT running (mode: {self._ne1000_status[pump_response_status]})",
                                      error=True)
            except KeyError:  # or just unknown status
                self.logger.add_entry(self.uart_name,
                                      f"{self.pump_name_str}: could not start the pump, communication error? (unknown status {pump_response_status})",
                                      error=True)
        self.pumpState = cfg.PUMP_STATE_ERROR
        return False

    def _handle_stop(self, current_pump_command: PumpCommand) -> bool:
        """
        Handles the parsed response to stop command.
        Single STP sent to the NE1000 in RUNNING state will switch it into PAUSED state.
        For now, we accept both outcomes and handle the difference at the sequence level.
        This behavior can be later modified here, to force transition into the STOPPED state.
        """
        pump_response_status = current_pump_command.response_result.status
        # the expected response is the Paused or Stopped state in status char
        if pump_response_status == 'S':
            self.logger.add_entry(self.uart_name,
                                  f"{self.pump_name_str}: pump is stopped")
            self.pumpFlowRate = 0.0
            self.pumpState = cfg.PUMP_STATE_STOPPED
            return True
        elif pump_response_status == 'P':
            self.logger.add_entry(self.uart_name,
                                  f"{self.pump_name_str}: pump is paused")
            self.pumpFlowRate = 0.0
            self.pumpState = cfg.PUMP_STATE_PAUSED
            return True # <--- change this line to "return False" to force transition into the STOPPED state
        elif pump_response_status == 'A':  # the pump responded with an alarm
            pump_response_error_meaning = self._ne1000_error.get(current_pump_command.response_result.error, "unknown error")
            self.logger.add_entry(self.uart_name,
                                  f"{self.pump_name_str}: Could not stop the pump ({pump_response_error_meaning})",
                                  error=True)
        else:
            try:  # otherwise, something is wrong and we report either the received status (infuse, withdraw etc.)
                self.logger.add_entry(self.uart_name,
                                      f"{self.pump_name_str}: pump is NOT stopping (mode: {self._ne1000_status[pump_response_status]})",
                                      error=True)
            except KeyError:  # or just unknown status
                self.logger.add_entry(self.uart_name,
                                      f"{self.pump_name_str}: could not stop the pump, communication error? (unknown status {pump_response_status})",
                                      error=True)
        self.pumpState = cfg.PUMP_STATE_ERROR
        return False

    def _handle_set_diameter(self, current_pump_command: PumpCommand) -> bool:
        """
        Handles the parsed response to set_diameter command.
        The correctness of setting is confirmed by repeating the same command DIA without value and checking the returned value
        """
        pump_response_data = current_pump_command.response_result.data
        if current_pump_command.expects_confirmation:
            # this is the reply to the command, repeated to check the set value
            (value, unit) = self._parse_value_with_unit(pump_response_data)
            try:
                if isclose(float(value), float(current_pump_command.value_to_confirm), abs_tol = 0.01):
                    self.logger.add_entry(self.uart_name,
                                          f"{self.pump_name_str}: syringe diameter set to {pump_response_data} mm")
                    return True
                else:
                    self.logger.add_entry(self.uart_name,
                                          f"{self.pump_name_str}: could not confirm syringe diameter setting, wrong value was returned ({pump_response_data} mm)",
                                          error=True)
                    self.pumpState = cfg.PUMP_STATE_ERROR
                    return False
            except ValueError:
                self.logger.add_entry(self.uart_name,
                                      f"{self.pump_name_str}: could not confirm syringe diameter setting: an invalid value ({pump_response_data} was returned, communication error?)",
                                      error=True)
                self.pumpState = cfg.PUMP_STATE_ERROR
                return False
        # this is newly sent command, check that no error is returned, modify the command and return False to have it repeated
        if not pump_response_data:
            pump_response_error = current_pump_command.response_result.error
            if pump_response_error is None:
                # no data and no error returned, the value has been accepted but need to confirm
                current_pump_command.expects_confirmation = True
                current_pump_command.value_to_confirm = current_pump_command.value
                current_pump_command.value = None
                return False
            else:
                # error returned
                pump_response_error_meaning = self._ne1000_error.get(current_pump_command.response_result.error,
                                                                     "unknown error")
                self.logger.add_entry(self.uart_name,
                                      f"{self.pump_name_str}: could not set syringe diameter ({pump_response_error_meaning})",
                                      error=True)
                self.pumpState = cfg.PUMP_STATE_ERROR
                return False
        else:
            self.logger.add_entry(self.uart_name,
                                  f"{self.pump_name_str}: unexpected response ({pump_response_data}) to DIA xx.xx, communication error?",
                                  error=True)
            return False

    def _handle_set_volume(self, current_pump_command: PumpCommand) -> bool:
        """
        Handles the parsed response to set_volume command
        """
        pump_response_data = current_pump_command.response_result.data
        if current_pump_command.expects_confirmation:
            # this is the reply to the command, repeated to check the set value
            (value, unit) = self._parse_value_with_unit(pump_response_data)
            try:
                if isclose(float(value), float(current_pump_command.value_to_confirm), abs_tol = 0.01):
                    self.logger.add_entry(self.uart_name,
                                          f"{self.pump_name_str}: volume set to {value} {unit}")
                    return True
                else:
                    self.logger.add_entry(self.uart_name,
                                          f"{self.pump_name_str}: could not confirm volume setting, wrong value returned ({value} {self._ne1000_units[unit]})",
                                          error=True)
                    self.pumpState = cfg.PUMP_STATE_ERROR
                    return False
            except ValueError:
                self.logger.add_entry(self.uart_name,
                                      f"{self.pump_name_str}: could not confirm volume setting: an invalid value ({pump_response_data} was returned, communication error?)",
                                      error=True)
                self.pumpState = cfg.PUMP_STATE_ERROR
                return False
        # this is newly sent command, check that no error is returned, modify the command and return False to have it repeated
        if not pump_response_data:  # data part of response contains the accepted diameter
            pump_response_error = current_pump_command.response_result.error
            if pump_response_error is None:
                # no data and no error returned, the value has been accepted but need to confirm
                current_pump_command.expects_confirmation = True
                current_pump_command.value_to_confirm = current_pump_command.value
                current_pump_command.value = None
                return False
            else:
                # error returned
                pump_response_error_meaning = self._ne1000_error.get(current_pump_command.response_result.error,
                                                                     "unknown error")
                self.logger.add_entry(self.uart_name,
                                      f"{self.pump_name_str}: could not set volume ({pump_response_error_meaning})",
                                      error=True)
                # self.pumpState = cfg.PUMP_STATE_ERROR
                return False
        else:
            self.logger.add_entry(self.uart_name,
                                  f"{self.pump_name_str}: unexpected response ({pump_response_data}) to VOL xx.xx, communication error?",
                                  error=True)
            return False

    def _handle_set_volume_units(self, current_pump_command: PumpCommand) -> bool:
        """
        Handles the parsed response to set_volume_units command
        """
        pump_response_data = current_pump_command.response_result.data
        if current_pump_command.expects_confirmation:
            # this is the reply to the command, repeated to check the set value
            (value, unit) = self._parse_value_with_unit(pump_response_data)
            if unit == current_pump_command.value_to_confirm:
                self.logger.add_entry(self.uart_name,
                                      f"{self.pump_name_str}: volume units set to {unit}")
                return True
            else:
                self.logger.add_entry(self.uart_name,
                                      f"{self.pump_name_str}: could not confirm volume unit setting, wrong value returned ({self._ne1000_units[unit]})",
                                      error=True)
                self.pumpState = cfg.PUMP_STATE_ERROR
                return False
        # this is newly sent command, check that no error is returned, modify the command and return False to have it repeated
        if not pump_response_data:  # data part of response contains the accepted diameter
            pump_response_error = current_pump_command.response_result.error
            if pump_response_error is None:
                # no data and no error returned, the volume unit has been accepted but need to confirm
                current_pump_command.expects_confirmation = True
                current_pump_command.value_to_confirm = current_pump_command.unit
                current_pump_command.unit = None
                return False
            else:
                # error returned
                pump_response_error_meaning = self._ne1000_error.get(current_pump_command.response_result.error,
                                                                     "unknown error")
                self.logger.add_entry(self.uart_name,
                                      f"{self.pump_name_str}: could not set volume unit ({pump_response_error_meaning})",
                                      error=True)
                self.pumpState = cfg.PUMP_STATE_ERROR
                return False
        else:
            self.logger.add_entry(self.uart_name,
                                  f"{self.pump_name_str}: unexpected response ({pump_response_data}) to VOL ML, communication error?",
                                  error=True)
            return False

    def _handle_set_pumping_rate(self, current_pump_command: PumpCommand) -> bool:
        """
        Handles the parsed response to set_pumping_rate command
        """
        pump_response_data = current_pump_command.response_result.data
        if current_pump_command.expects_confirmation:
            # this is the reply to the command, repeated to check the set value
            #    NB: due to the following peculiar behavior of NE-1000 pump, a separate check is needed:
            #    after the command "RAT C 0" while the pump is RUNNING state, the rate returned by "RAT" command is not 0 but the value set by the last "RAT x.xxxMM" command
            #    Because of that, after RAT commands with value=0, current_pump_command.response_result.data == "S" has to be checked and not current_pump_command.response_result.data
            (value, unit) = self._parse_value_with_unit(pump_response_data)
            try:
                if float(current_pump_command.value_to_confirm) == 0.0: # setting pumping rate to zero was requested by the command we are confirming
                    if current_pump_command.response_result.status == "S":
                        self.logger.add_entry(self.uart_name,
                                              f"{self.pump_name_str}: pumping rate set to {current_pump_command.value_to_confirm} {self._ne1000_units[unit]}")
                        self.pumpFlowRate = 0.0
                        return True
                    else:
                        self.logger.add_entry(self.uart_name,
                                              f"{self.pump_name_str}: pumping rate could not be set to zero, pump was not stopped ({pump_response_data} was returned)",
                                              error=True)
                        self.pumpState = cfg.PUMP_STATE_ERROR
                        return False
                elif isclose(float(value), float(current_pump_command.value_to_confirm), abs_tol = 0.01) and (unit == "MM"):
                    self.logger.add_entry(self.uart_name,
                                          f"{self.pump_name_str}: pumping rate set to {value} {self._ne1000_units[unit]}")
                    self.pumpFlowRate = float(value)
                    return True
                else:
                    self.logger.add_entry(self.uart_name,
                                          f"{self.pump_name_str}: could not confirm pumping rate setting, wrong value returned ({value} {self._ne1000_units[unit]})",
                                          error=True)
                    self.pumpState = cfg.PUMP_STATE_ERROR
                    return False
            except ValueError:
                self.logger.add_entry(self.uart_name,
                                      f"{self.pump_name_str}: could not confirm pumping rate setting: an invalid value ({pump_response_data} was returned, communication error?)",
                                      error=True)
                self.pumpState = cfg.PUMP_STATE_ERROR
                return False
        # this is newly sent command, check that no error is returned, modify the command and return False to have it repeated
        if not pump_response_data:  # data part of response contains the accepted diameter
            pump_response_error = current_pump_command.response_result.error
            if pump_response_error is None:
                # no data and no error returned, the volume unit has been accepted but need to confirm
                current_pump_command.expects_confirmation = True
                current_pump_command.value_to_confirm = current_pump_command.value
                current_pump_command.value = None
                current_pump_command.unit = None
                return False
            else:
                # error returned
                pump_response_error_meaning = self._ne1000_error.get(current_pump_command.response_result.error,
                                                                     "unknown error")
                self.logger.add_entry(self.uart_name,
                                      f"{self.pump_name_str}: could not set pumping rate ({pump_response_error_meaning})",
                                      error=True)
                self.pumpState = cfg.PUMP_STATE_ERROR
                return False
        else:
            self.logger.add_entry(self.uart_name,
                                  f"{self.pump_name_str}: unexpected response ({pump_response_data}) to RAT x.xxxMM, communication error?",
                                  error=True)
            return False

    def _handle_set_pumping_direction(self, current_pump_command: PumpCommand) -> bool:
        """
        Handles the parsed response to set_pumping_direction command
        """
        pump_response_data = current_pump_command.response_result.data
        if current_pump_command.expects_confirmation:
            # this is the reply to the command, repeated to check the set value
            if pump_response_data == current_pump_command.value_to_confirm:
                self.logger.add_entry(self.uart_name,
                                      f"{self.pump_name_str}: pumping direction set to {pump_response_data}")
                return True
            else:
                self.logger.add_entry(self.uart_name,
                                      f"{self.pump_name_str}: could not confirm pumping direction setting, wrong value returned ({pump_response_data})",
                                      error=True)
                self.pumpState = cfg.PUMP_STATE_ERROR
                return False
        # this is newly sent command, check that no error is returned, modify the command and return False to have it repeated
        if not pump_response_data:  # data part of response contains the accepted diameter
            pump_response_error = current_pump_command.response_result.error
            if pump_response_error is None:
                # no data and no error returned, the volume unit has been accepted but need to confirm
                current_pump_command.expects_confirmation = True
                current_pump_command.value_to_confirm = current_pump_command.value
                current_pump_command.value = None
                return False
            else:
                # error returned
                pump_response_error_meaning = self._ne1000_error.get(current_pump_command.response_result.error,
                                                                     "unknown error")
                self.logger.add_entry(self.uart_name,
                                      f"{self.pump_name_str}: could not set pumping direction ({pump_response_error_meaning})",
                                      error=True)
                self.pumpState = cfg.PUMP_STATE_ERROR
                return False
        else:
            self.logger.add_entry(self.uart_name,
                                  f"{self.pump_name_str}: unexpected response ({pump_response_data}) to DIR, communication error?",
                                  error=True)
            return False