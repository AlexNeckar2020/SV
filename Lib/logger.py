import tkinter as tk
from datetime import datetime

import Lib.config as cfg
from Lib.uart import RaspberryPiUART

class Logger():
    def __init__(self, app):
        self._enabled = bool(cfg.LOGGER_MODE) # False for empty dictionary {}, True for non-empty set {a, b...}
        if not self._enabled:
            return
        self._window = cfg.LOG_WINDOW in cfg.LOGGER_MODE
        self._file = cfg.LOG_FILE in cfg.LOGGER_MODE
        self._uart = cfg.LOG_UART in cfg.LOGGER_MODE
        self._debug = cfg.LOG_CONSOLE in cfg.LOGGER_MODE
        self._queue = []
        if self._window:
            self.logger_window = app.log_window
        if self._file:
            self.logger_file = LogFile()
            now = datetime.now()
            log_file_extension = ".html" if cfg.LOG_FILE_TYPE == cfg.LOG_FILE_HTML else ".csv"
            log_file_name = now.strftime("log_%Y-%m-%d_%H-%M-%S") + log_file_extension
            if not self.logger_file.create_open(cfg.LOGS_DIR / log_file_name):
                self._file = False
                app.update_status(f"Logger error: could not create and open file in {cfg.LOGS_DIR}", color="red")
                if self._window:
                    self.queue_entry("logger", f"could not create and open file {cfg.LOGS_DIR}/{log_file_name}", error=True)
        if self._uart:
            self.logger_uart = LogUART()
            if not self.logger_uart.initialize_uart("UART0", cfg.SERIAL_DEBUG_BAUDRATE):
                self._uart = False
                app.update_status(f"Logger error: could not initialize logging over UART (UART0 must be busy)", color="red")
                if self._window:
                    self.queue_entry("logger", f"could not initialize logging over UART (UART0 must be busy)", error=True)

    def queue_entry(self, agent: str, log_entry: str, error=False):
        if self._enabled:
            self._queue.append({"agent": agent, "log_entry": log_entry, "error": error})

    def add_entry(self, agent: str, log_entry: str, error=False):
        # processing queued entries first, if _queue is not empty
        if self._enabled:
            while self._queue:
                entry = self._queue.pop(0)  # FIFO dequeuing
                # call _write_entry for each queued item
                self._write_entry(agent=entry["agent"], log_entry=entry["log_entry"], error=entry["error"])
            else:
                self._write_entry(agent, log_entry, error)

    def _write_entry(self, agent: str, log_entry: str, error: bool):
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        if self._window:
            self.logger_window.write(timestamp, agent, log_entry, error)
        # if self._file:
        #     self.logger_file.write(f"{timestamp}\t{"ERROR:" if error else ""}{agent}\t{log_entry}")
        if self._file:
            if cfg.LOG_FILE_TYPE == cfg.LOG_FILE_HTML:
                self.logger_file.write_html(timestamp, agent, log_entry, error)
            else:
                self.logger_file.write_csv(f"{timestamp}\t{'ERROR:' if error else ''}{agent}\t{log_entry}")
        if self._uart:
            self.logger_uart.write(f"{timestamp} - {"ERROR:" if error else ""}{agent} - {log_entry}{cfg.LOG_UART_NEWLINE}")
        if self._debug:
            print(f"{timestamp} - {"ERROR:" if error else ""}{agent} - {log_entry}")

class LogWindow(tk.Toplevel):
    """Logger console window"""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Log console")
        self._icon_log = tk.PhotoImage(file=f"{cfg.RESOURCES_DIR}/Log.png")
        self.iconphoto(False, self._icon_log)
        self.geometry("700x500+400+200")
        self.withdraw() # hide this window
        self.create_widgets()
        self.protocol("WM_DELETE_WINDOW", self.hide) # intercept closing by window manager, hiding this window instead

    def close(self):
        self.destroy()  # destructor

    def show(self):
        self.deiconify() # show window

    def hide(self):
        self.withdraw() # hide window

    def create_widgets(self):
        self.frame = tk.Frame(self)
        self.frame.pack(expand=True, fill=tk.BOTH)

        self.scrollbar = tk.Scrollbar(self.frame)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.text_widget = tk.Text(self.frame, bg="black", fg="white", font=("Courier", 10), wrap=tk.WORD,
                                   yscrollcommand=self.scrollbar.set)
        self.text_widget.pack(expand=True, fill=tk.BOTH)

        self.scrollbar.config(command=self.text_widget.yview)

        self.text_widget.configure(state=tk.DISABLED)

        for (agent_name, color) in cfg.logColorScheme.items():
            self.text_widget.tag_configure(agent_name, foreground=color)

    def write(self, timestamp: str, agent: str, log_entry: str, error: bool):
        # Enable editing temporarily
        self.text_widget.configure(state=tk.NORMAL)
        # Check if the scrollbar is at the bottom: yview returns a tuple (top_fraction, bottom_fraction)
        at_bottom = self.text_widget.yview()[1] == 1.0
        # Append new log entry
        self.text_widget.insert(tk.END, f"[{timestamp}] {"ERROR:"if error else ""}{agent}: {log_entry}\n", "error" if error else agent)
        # Disable editing again
        self.text_widget.configure(state=tk.DISABLED)
        # Only autoscroll if at bottom before insertion; otherwise, leave the user's scroll position
        if at_bottom:
            self.text_widget.see(tk.END)


class LogFile():
    def __init__(self):
        self._file = None
        self._file_path = None
        self._html_mode = (cfg.LOG_FILE_TYPE == cfg.LOG_FILE_HTML)
        if self._html_mode:
            self._html_header = f"""<!DOCTYPE html>
            <html>
            <head>
              <meta charset="UTF-8">
              <title>Log File</title>
              <style>
                body {{
                  background-color: black;
                  color: white;
                  font-family: Courier, monospace;
                }}
                .log-container {{
                  height: 98vh;
                  overflow-y: auto;
                  border: 1px solid #444;
                }}
                table {{
                  width: 100%;
                  border-collapse: collapse;
                  table-layout: auto;
                }}
                th, td {{
                  padding: 4px;
                  border: 1px solid #555;
                  text-align: left;
                }}
                td:nth-child(3) {{
                  word-break: break-word;
                }}
                thead th {{
                  position: sticky;
                  top: 0;
                  background-color: #222;
                  z-index: 1;
                }}
              </style>
            </head>
            <body>
              <div class="log-container">
                <table>
                  <thead>
                    <tr><th>Timestamp</th><th>Agent</th><th>Message</th></tr>
                  </thead>
                  <tbody>
            """
            self._html_footer = "</tbody></table></div></body></html>"

    def create_open(self, file_path: str) -> bool:
        """
        Creates a new text file and opens it for writing.
        :param file_path: Path and name of the file to be created.
        :return: True if the file is successfully created and opened, False otherwise.
        """
        try:
            self._file = open(file_path, 'w')
            self._file_path = file_path
            if self._html_mode:
                self._file.write(self._html_header) # write HTML header+CSS first if output to HTML
            return True
        except Exception as e:
            print(f"Error creating file: {e}")
            return False

    def close(self) -> bool:
        """
        Closes the file if it is open.
        :return: True if the file is successfully closed, False otherwise.
        """
        if self._file:
            try:
                if self._html_mode:
                    self._file.write(self._html_footer) # finalize HTML file before closing it
                self._file.close()
                self._file = None
                return True
            except Exception as e:
                print(f"Error closing file: {e}")
                return False
        return False

    # def write(self, log_entry_complete: str) -> bool:
    #     """
    #     Writes a single line of text to the file.
    #     :param text: Text to be written to the file.
    #     :return: True if writing succeeds, False otherwise.
    #     """
    #     if self._file:
    #         try:
    #             self._file.write(log_entry_complete + '\n')
    #             self._file.flush()
    #             return True
    #         except Exception as e:
    #             print(f"Error writing to file: {e}")
    #             return False
    #     return False

    def write_csv(self, log_entry_complete: str) -> bool:
        """
        Writes a single line of text to the CSV file.
        :param text: Text to be written to the file (formatted by the caller).
        :return: True if writing succeeds, False otherwise.
        """
        if self._file:
            try:
                self._file.write(log_entry_complete + '\n')
                self._file.flush()
                return True
            except Exception as e:
                print(f"Error writing CSV log: {e}")
                return False
        return False

    def write_html(self, timestamp: str, agent: str, message: str, error: bool) -> bool:
        """
        Writes a single entry into the HTML log table using the same color scheme as LogWindow.
        Parameters are table column values passed from the Logger.
        :return: True if writing succeeds, False otherwise.
        """
        if self._file and self._html_mode:
            try:
                message_html = message.replace('\n', "<br>")
                message_html = message_html.replace('[{', "[<br>{")
                message_html = message_html.replace('},', "},<br>")
                message_html = message_html.replace('}]', "}<br>]")
                agent_color = cfg.logColorScheme.get(agent, "white")
                message_color = cfg.logColorScheme.get("error" if error else agent, "white")
                error_prefix = "<strong>ERROR:</strong> " if error else ""
                row = (
                    f"<tr>"
                    f"<td>{timestamp}</td>"
                    f"<td style='color: {agent_color}'>{agent}</td>"
                    f"<td style='color: {message_color}'>{error_prefix}{message_html}</td>"
                    f"</tr>\n"
                )
                self._file.write(row)
                self._file.flush()
                return True
            except Exception as e:
                print(f"Error writing HTML log: {e}")
                return False
        return False

class LogUART(RaspberryPiUART):
    def __init__(self):
        super().__init__()

# Example usage:
if __name__ == "__main__":
    # log = LogFile()
    # if log.create_open(cfg.LOG_FILES_PATH+"testlog.txt"):
    #     log.write("This is a test log entry.")
    #     log.close()
    # root = tk.Tk()
    # app = LogWindow(root)
    # root.mainloop()
    # uart = LogUART()
    # uart.write("This is a test log output over UART.")
    root = tk.Tk()
    app = LogWindow(root)
    test_logger = Logger(root)
    test_logger.queue_entry("test", "This is a test logger message")
    root.mainloop()
