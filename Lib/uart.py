"""
To enable UARTs on Raspberry Pi 4B:

1) open the file config.txt, for example:
      sudo nano /boot/firmware/config.txt
      
2) add the following lines, if not present already:
      enable_uart=1
      dtoverlay=uart3
      dtoverlay=uart4
      dtoverlay=uart5
   and save the changes (CTRL+X, Y, Enter)
   
3) disable shell messages on the serial0:
      sudo raspi-config
   choose "Interfacing Options" -> "Serial Port" -> DISABLE serial login shell, ENABLE serial interface
   
4) reboot the Pi:
      sudo reboot
      
Now you can test the connectivity on all UARTs by running this script:
      python uart.py
"""
""" This code was developed with assistance from ChatGPT (OpenAI, 2025) """

import asyncio
import serial  # PySerial
import time # for synchronous read method
from serial.serialutil import EIGHTBITS, PARITY_NONE, STOPBITS_ONE

import Lib.config as cfg


class RaspberryPiUART:
    def __init__(self, logger=None):
        """
        Link logger and initialize RaspberryPiUART class attributes for each UART.
        """
        self.logger = logger
        self.uart_name = None
        self.serial = None                  # Placeholder for PySerial object
        self.state = cfg.UART_STATE_READY   # UART state, initially READY
        self.start_packet_byte = None       # Start-of-packet byte for this serial (optional, will be filtered from the response)
        self.end_packet_byte = None         # End-of-packet byte for this serial (optional, will be filtered from the response)

    def initialize_uart(self, uart_name, baudrate=9600, timeout=0.1, start_packet_byte: int = None, end_packet_byte: int = None) -> bool:
        """
        Initializes a UART device and assigns its serial object.

        :param uart_name: UART ID string (e.g., "UART3").
        :param baudrate: Baud rate for serial communication.
        :param timeout: Serial port timeout in seconds.
        :param start_packet_byte: Optional start byte to strip from response (e.g., 0x02 for syringe pump start-of-packet byte).
        :param end_packet_byte: Optional end byte to strip from response (e.g., 0x03 for syringe pump end-of-packet byte, or '\n' for debug serial with manual response input).
        :return: True if initialized successfully.
        """
        if uart_name in cfg.UART_DEVICES:
            self.uart_name = uart_name
            device_name = cfg.UART_DEVICES[uart_name]["device"]
            try:
                self.serial = serial.Serial(
                    device_name,
                    baudrate=baudrate,
                    timeout=timeout,
                    bytesize=EIGHTBITS,
                    parity=PARITY_NONE,
                    stopbits=STOPBITS_ONE
                )
                self.start_packet_byte = start_packet_byte
                self.end_packet_byte = end_packet_byte
                if self.logger:
                    self.logger.add_entry("uart", f"{device_name} initialized at {baudrate} baud")
                return True
            except serial.SerialException as e:
                if self.logger:
                    self.logger.add_entry("uart", f"device {device_name} could not be initialized", error=True)
                else:
                    print(f"Error initializing {uart_name}: {e}")
                return False
        else:
            if self.logger:
                self.logger.add_entry("uart", f"Unknown UART name ({uart_name}), cannot initialize", error=True)
            return False

    async def query(self, data, timeout_ms=1000) -> str | None:
        """
        Asynchronously send a command and await a response from the specified UART.

        :param data: Command to send (string or bytes).
        :param timeout_ms: Timeout for the whole operation in milliseconds.
        :return: Decoded response string or None if timeout occurs.
        """
        if not self.serial:
            if self.logger:
                self.logger.add_entry("uart", f"{self.uart_name} is not initialized, cannot query", error=True)
            return None

        # Prevent new query if UART is busy
        if self.state == cfg.UART_STATE_BUSY:
            if self.logger:
                self.logger.add_entry("uart", f"{self.uart_name} is still waiting for response, cannot query", error=True)
            return None

        # Mark UART as busy
        self.state = cfg.UART_STATE_BUSY
        response = None

        try:
            # Write command asynchronously
            await asyncio.to_thread(self.write, data)

            # Read response asynchronously, with framing logic
            response = await self._read_with_timeout(read_timeout_ms=timeout_ms)

            # Handle timeout state
            if response is None:
                self.state = cfg.UART_STATE_TIMEOUT
                if self.logger:
                    self.logger.add_entry("uart", f"{self.uart_name} query timed out", error=True)
                return None

            # Strip SOF byte if present
            if self.start_packet_byte is not None and response.startswith(chr(self.start_packet_byte)):
                response = response[1:]

            # Strip EOF byte if present
            if self.end_packet_byte is not None and response.endswith(chr(self.end_packet_byte)):
                response = response[:-1]

            # Successfully completed, return the response string
            return response.strip()

        except Exception as e:
            if self.logger:
                self.logger.add_entry("uart", f"exception raised during query on{self.uart_name}: {e}", error=True)
            else:
                print(f"Exception raised during query on {self.uart_name}: {e}")
            self.state = cfg.UART_STATE_READY
            return None

    async def _read_with_timeout(self, read_timeout_ms, poll_interval=0.01):
        """
        Coroutine to read from UART, waiting for start_packet_byte and/or end_packet_byte.

        :param read_timeout_ms: Timeout in milliseconds.
        :param poll_interval: Poll interval in seconds.
        :return: Decoded response string or None if timed out.
        """

        # Calculate the deadline timestamp
        deadline = asyncio.get_event_loop().time() + (read_timeout_ms / 1000)
        response = b''
        sof_detected = False

        while asyncio.get_event_loop().time() < deadline:
            # Check available bytes in UART buffer asynchronously
            bytes_waiting = await asyncio.to_thread(lambda: self.serial.in_waiting)
            if bytes_waiting > 0:
                # Read all available bytes
                data = await asyncio.to_thread(self.serial.read, bytes_waiting)

                # If SOF is defined and not detected yet
                if self.start_packet_byte is not None and not sof_detected:
                    # Look for SOF in received data
                    sof_index = data.find(bytes([self.start_packet_byte]))
                    if sof_index >= 0:
                        sof_detected = True
                        # Start buffering from SOF byte onward
                        response += data[sof_index:]
                    # If SOF not found, ignore data and continue polling
                else:
                    # Either SOF not required or already detected
                    response += data

                # If EOF is defined and detected in buffer, exit loop
                if self.end_packet_byte is not None and self.end_packet_byte in response:
                    break

            await asyncio.sleep(poll_interval)

        # If we never detected SOF and required it
        if self.start_packet_byte is not None and not sof_detected:
            return None

        # If no data was received
        if not response:
            return None

        # Decode full buffer to string for post-processing
        return response.decode(errors='ignore')

    def write(self, data):
        """
        Synchronous blocking UART write wrapped by asyncio.to_thread() externally.

        :param data: Data to send (string or bytes).
        """
        if isinstance(data, str):
            data = data.encode()
        self.serial.write(data)

    def read(self, timeout_ms, poll_interval=0.01, strip=True) -> str | None:
        """
        Synchronous blocking UART read that waits for SOF/EOF bytes if provided.

        :param timeout_ms: Timeout for entire operation in milliseconds.
        :param poll_interval: Poll interval for checking buffer (in seconds).
        :param strip: Strips off SOF/EOF bytes (default behavior).
        :return: Decoded response string or None if timed out.
        """

        # Track time elapsed for enforcing timeout
        deadline = time.time() + (timeout_ms / 1000)
        response = b''
        sof_detected = False

        while time.time() < deadline:
            # Check how many bytes are available
            if self.serial.in_waiting > 0:
                data = self.serial.read(self.serial.in_waiting)

                # Look for SOF if required and not yet detected
                if self.start_packet_byte is not None and not sof_detected:
                    sof_index = data.find(bytes([self.start_packet_byte]))
                    if sof_index >= 0:
                        sof_detected = True
                        response += data[sof_index:]  # Collect starting from SOF
                    # Else keep ignoring junk
                else:
                    # Already found SOF or SOF not required
                    response += data

                # If EOF byte is found, we can stop
                if self.end_packet_byte is not None and self.end_packet_byte in response:
                    break

            # Brief pause to avoid busy-wait loop
            time.sleep(poll_interval)

        # Handle timeout or SOF not found
        if self.start_packet_byte is not None and not sof_detected:
            return None

        if not response:
            return None

        # If strip=True, remove SOF and EOF from response
        if strip:
            if self.start_packet_byte is not None and response.startswith(bytes([self.start_packet_byte])):
                response = response[1:]  # Remove SOF byte
            if self.end_packet_byte is not None and response.endswith(bytes([self.end_packet_byte])):
                response = response[:-1]  # Remove EOF byte

        # Decode and return full response buffer
        return response.decode(errors='ignore')

    def get_uart_state(self):
        """
        Returns the current state (UART_STATE_READY, UART_STATE_BUSY, UART_STATE_TIMEOUT) of the associated UART.
        :return: One of the UART state constants.
        """
        return self.state # "if self.state else None" is implied but would be redundant

    def close_uart(self):
        """
        Closes the associated UART port.
        """
        if self.serial and self.serial.is_open:
            self.serial.close() # PySerial Serial.close()
            if self.logger:
                self.logger.add_entry("uart", f"{self.uart_name} (device {cfg.UART_DEVICES[self.uart_name]['name']}) closed")
        else:
            if self.logger:
                self.logger.add_entry("uart", f"{self.uart_name} is already closed or has not been opened", error=True)


"""
# Example usage (only runs if executed directly, e.g. "python3 uart.py")
# Tests the connectivity of Raspberry Pi 4B over 4 UART ports
async def main():
    uart = RaspberryPiUART()
    uart.initialize_uart("UART3", baudrate=115200)
    uart.initialize_uart("UART4", baudrate=9600)
    uart.initialize_uart("UART5", baudrate=19200)

    # Parallel queries!
    task1 = uart.query("UART3", "STATUS?", timeout=1500)
    task2 = uart.query("UART4", "PING", timeout=1000)
    task3 = uart.query("UART5", "READ", timeout=2000)

    responses = await asyncio.gather(task1, task2, task3)
    print(responses)

    uart.close_all()

if __name__ == "__main__":
    asyncio.run(main())
"""

"""
# Example usage (only runs if executed directly, e.g. "python3 uart.py")
# Tests the connectivity of a single NE-1000 syringe pump over UART3 (as set in config.py)
"""
if __name__ == "__main__":
   uart0 = RaspberryPiUART()
   uart3 = RaspberryPiUART()
   uart0.initialize_uart("UART0", baudrate=9600)
   result = uart3.initialize_uart("UART3", baudrate=19200, start_packet_byte=0x02, end_packet_byte=0x03)
   uart0.write(f"UART3: {'OK' if result else 'could not initialize!'}\n\r")
   i = 1
   test_command = "* RESET"
   while i <= 10:
       uart0.write(f"UART3 >>> {test_command} ({i} out of 10)\r")
       uart3.write(test_command+'\r')
       result = uart3.read(timeout_ms=1000)
       if result:
           break
       i += 1
   uart0.write(f"UART3 <<< {result}\r\n")
   if result == "00S":
       test_program = ["DIR WDR", "DIA 16.0", "RAT 3MM", "RUN"]
       for command in test_program:
           uart0.write(f"UART3 >>> {command}\r")
           uart3.write(command + '\r')
           result = uart3.read(timeout_ms=1000)
           uart0.write(f"UART3 <<< {result}\r\n")
       time.sleep(5)
       test_command = "STP"
       uart0.write(f"UART3 >>> {test_command}\r")
       uart3.write(test_command + '\r')
       result = uart3.read(timeout_ms=1000)
       uart0.write(f"UART3 <<< {result}\r\n")
   uart3.close_uart()

