import time
from threading import Thread, Event
from dataclasses import dataclass
from typing import Callable, List
import functools # only for debug helper decorators

import Lib.config as cfg
from Lib.ne1000 import SyringePump
import Lib.files as files

#### DEBUG HELPER FUNCTIONS BEGIN

def get_list_representation_of_nested_attribute(obj_list, fields):
    """Format a list of objects as [{field1: val1, field2: val2}, ...]."""
    result = []
    for item in obj_list:
        entry = {}
        for field in fields:
            try:
                entry[field] = getattr(item, field, None)
            except Exception:
                entry[field] = "get_list_representation_of_nested_attribute() exception"
        result.append(entry)
    return result

# Main decorator factory: takes a list of class attribute names, logging agent name and whether the logging is done before of after executing the method
def log_class_attributes(attr_config, log_agent, log_before_execution=False):
    """
    Decorator to log selected class attributes before or after method execution.
    :param attr_config: list of str or (str, [fields]) for list-of-object attributes.
    :param log_agent: logger agent name.
    :param log_before_execution: whether to log before (True) or after (False, default) method call.
    """

    # This is the actual decorator applied to a method
    def decorator(method):

        # Decorator preserves the original method's name, docstring, etc.
        @functools.wraps(method)
        def wrapper(self, *args, **kwargs):
            # only execute the wrapper code on the methods of the class if the corresponding debug flag is set in config.py
            debug_flags = {
                "PumpScheduler": cfg.DEBUG_PUMP_SCHEDULER,
                "PumpController": cfg.DEBUG_PUMP_CONTROLLER,
            }
            if not debug_flags.get(self.__class__.__name__, True):
                return method(self, *args, **kwargs)

            if not log_before_execution:
                result = method(self, *args, **kwargs)

            if hasattr(self, '_logger'):
                log_lines = [f"[{'BEFORE' if log_before_execution else 'AFTER'}] {method.__name__}():\n"]
                for item in attr_config:
                    if isinstance(item, tuple):
                        attr, fields = item
                        val = getattr(self, attr, [])
                        formatted = get_list_representation_of_nested_attribute(val, fields or [])
                        log_lines.append(f"{attr}={formatted}")
                    else:
                        try:
                            val = getattr(self, item, None)
                            if item == "_running" and hasattr(val, "is_set"):
                                val = val.is_set()
                            log_lines.append(f"{item}={val}")
                        except Exception as e:
                            log_lines.append(f"{item}=<log_class_attribute() exception: {e}>")
                log_msg = "\n".join(log_lines)
                self._logger.add_entry(log_agent, log_msg)

            if log_before_execution:
                result = method(self, *args, **kwargs)
            return result

        return wrapper

    return decorator

#### DEBUG HELPER FUNCTIONS END

@dataclass
class PumpAction:
    """
    AI: Represents a scheduled action to be executed after a time delay.
    """
    time_offset: float # AI: Original raw offset from sequence start
    action: Callable[[], None]
    description: str = ""
    executed: bool = False
    time_offset_corrected: float = 0.0  # AI: Offset adjusted for pause/resume injections


class PumpScheduler:
    """
    AI: A reusable time-based dispatcher for executing scheduled actions with precise delays.
    GUI-aware, but pump-agnostic.
    """
    def __init__(self, logger_handle):
        self._logger = logger_handle
        self._actions: List[PumpAction] = []
        self._thread = None
        self._running = Event()
        self._start_time = None
        self._pause_start_time = None  # recorded by pause()
        self._total_pause_duration = 0.0  # total accumulated pause time, used for correction tracking
        self._current_action_index = 0
        self._sequence_name: str = ""
        self._progress_label = None  # Tkinter Label widget to show real-time progress

    # === Public interface ===

    def set_progress_label(self, label_widget):
        """
        AI: Set a Tkinter label for displaying live progress (optional).
        """
        self._progress_label = label_widget

    def set_sequence_name(self, sequence_name: str):
        """
        Set the current scheduler sequence name.
        """
        self._sequence_name = sequence_name

    def get_sequence_name(self) -> str:
        """
        Get the current scheduler sequence name.
        """
        return self._sequence_name

    def add_action(self, delay: float, action: Callable[[], None], description: str = ""):
        """
        Adds an 'action' to be run 'delay' seconds from scheduler start.
        :param delay: time the scheduled action will be executed (in s from scheduler start)
        :param action: a pump function or a lambda, if the pump function has to be passed with a parameter
        :param description: name of the scheduled action for logging purposes
        """
        self._actions.append(PumpAction(delay, action, description))

    @log_class_attributes([("_actions", ["time_offset", "time_offset_corrected", "description"]),
                          "_start_time",
                          "_pause_start_time",
                          "_total_pause_duration",
                          "_current_action_index"],
                         "debug:scheduler")
    def clear(self):
        """
        Clear any previously scheduled actions and reset scheduler state.
        NB: does not freeze the dispatcher loop! so it should not be called while the scheduler is running
        """
        if self.is_running():
            self._logger.add_entry("scheduler", "Attempt to clear actions sequence while the scheduler is running", error=True)
        self._actions.clear()
        self._current_action_index = 0
        self._start_time = None
        self._pause_start_time = None
        self._total_pause_duration = 0.0

    @log_class_attributes([("_actions", ["time_offset", "description"]),
                           "_start_time",
                           "_pause_start_time",
                           "_total_pause_duration",
                           "_current_action_index"],
                          "debug:scheduler")
    def start(self):
        """
        Sorts the scheduled actions by staring time and begins executing the sequence in a new background thread.
        First ensures that: 1) an empty sequence will not start and 2) a second scheduler thread will not be created
        """
        if not self._actions:
            self._logger.add_entry("scheduler", "No actions scheduled to run", error=True)
            return
        if self._thread and self._thread.is_alive():
            self._logger.add_entry("scheduler", "Dispatcher thread is already running", error=True)
            return

        self._actions.sort(key=lambda a: a.time_offset) # sorts scheduled actions by increasing starting time offset
        for a in self._actions:
            a.time_offset_corrected = a.time_offset  # no timeline correction necessary at start
        self._start_time = time.monotonic() # register the starting time
        self._total_pause_duration = 0.0  # zero the pause duration, since a new sequence hasn't been resumed after pause
        self._running.set() # unblock the dispatcher loop
        self._logger.add_entry("scheduler", f"Pump scheduler starting '{self._sequence_name}' sequence")
        cfg.EXPERIMENT_TOTAL_PAUSE_DURATION_S = 0.0
        self._thread = Thread(target=self._run_dispatcher, daemon=True)
        self._thread.start()

    @log_class_attributes([("_actions", ["time_offset", "time_offset_corrected", "description"]),
                           "_start_time",
                           "_pause_start_time",
                           "_total_pause_duration",
                           "_current_action_index"],
                          "debug:scheduler")
    def stop(self):
        """
        Interrupts the currently running action sequence and terminates the dispatcher thread.
        """
        self._running.clear()
        if self._thread:
            self._thread.join(timeout=2.0)  # Wait up to 2 seconds for thread to exit
            if self._thread.is_alive():
                self._logger.add_entry("scheduler",
                                       f"Scheduler thread did not terminate cleanly during '{self._sequence_name}' sequence",
                                       error=True)
            self._thread = None  # Reset thread handle safely
        else:
            self._logger.add_entry("scheduler", "stop() called but no scheduler thread exists", error=True)
        self._logger.add_entry("scheduler", f"Pump scheduler thread stopped during '{self._sequence_name}' sequence")
        self._sequence_name = ""

    @log_class_attributes([("_actions", ["time_offset", "time_offset_corrected", "description"]),
                           "_start_time",
                           "_pause_start_time",
                           "_total_pause_duration",
                           "_current_action_index"],
                          "debug:scheduler")
    def pause(self):
        """
        Pause: freeze dispatcher and note starting time of the pause.
        TODO: rename this method. It only notes the pause start time and lets the thread finish.
        """
        self._running.clear()
        self._pause_start_time = time.monotonic()
        self._logger.add_entry("scheduler", f"Pump scheduler paused during '{self._sequence_name}' sequence")

    @log_class_attributes([("_actions", ["time_offset", "time_offset_corrected", "description"]),
                           "_start_time",
                           "_pause_start_time",
                           "_total_pause_duration",
                           "_current_action_index"],
                          "debug:scheduler")
    def resume(self):
        """
        Resume dispatcher after pause, correcting timeline and starting a new thread.
        TODO: rewrite (and probably rename) this method. It readjusts the sequence timings and restarts the thread.
            It must maintain the actual timeline (non-adjusted, for timing purposes) and adjusted timeline (for displaying and reporting purposes)
        """
        if self._pause_start_time:
            pause_duration = time.monotonic() - self._pause_start_time
            self._total_pause_duration += pause_duration
            cfg.EXPERIMENT_TOTAL_PAUSE_DURATION_S = self._total_pause_duration
            self._pause_start_time = None

            # AI: Shift all remaining unexecuted corrected offsets by pause duration
            for i in range(self._current_action_index, len(self._actions)): # think! we may need to get the number of added restore actions
                # self._actions[i].time_offset_corrected += pause_duration
                self._actions[i].time_offset += pause_duration

            self._logger.add_entry("scheduler", f"Pump scheduler resumed after {pause_duration:.2f} s pause")

        self._running.set()
        self._logger.add_entry("scheduler", f"Pump scheduler resuming '{self._sequence_name}' sequence")
        self._thread = Thread(target=self._run_dispatcher, daemon=True)
        self._thread.start()

    def is_running(self) -> bool:
        """
        Check if scheduler is actively dispatching.
        """
        return self._running.is_set()

    # === Internal dispatch logic ===

    def _update_progress_label(self, now: float):
        if self._progress_label and self._actions:
            # total_time = self._actions[-1].time_offset_corrected  # use corrected time offset for the sequence progress %
            total_time = self._actions[-1].time_offset
            percent = min((now / total_time) * 100, 100.0)
            if total_time > 60:
                (ttime_min, ttime_s) = divmod(total_time, 60)
                (now_min, now_s) = divmod(now, 60)
                msg = f"{self._sequence_name}, {now_min:.0f} min {now_s:.1f} s of {ttime_min:.0f} min {ttime_s:.0f} s ({percent:.0f}%)..."
            else:
                msg = f"{self._sequence_name}, {now:.1f} s of {total_time:.1f} s ({percent:.0f}%)..."
            self._progress_label.config(text=msg)

    def _run_dispatcher(self):
        self._last_debug_time = 0.0

        while self._running.is_set() and self._current_action_index < len(self._actions):
            self._running.wait()  # pause dispatcher here if _running Event is cleared
            now = time.monotonic() - self._start_time
            current = self._actions[self._current_action_index]
            adjusted_action_time = current.time_offset_corrected  # AI: Use corrected offset

            #if round(now * 2) != round(self._last_debug_time * 2): # this is just a temporary debug ticker
            #    self._last_debug_time = now
            #    print(f" ::: {now:.2f}")

            if now >= current.time_offset: ### correct?
                try:
                    current.action()
                    current.executed = True
                    self._logger.add_entry("scheduler",
                                           f"Executed at {now:.2f} s (scheduled at {adjusted_action_time:.2f} s): {current.description}")
                except Exception as e:
                    self._logger.add_entry("scheduler",
                                           f"Failed at {now:.2f} s (scheduled at {adjusted_action_time:.2f} s): {current.description} ({e})",
                                           error=True)
                self._current_action_index += 1
                print(f"{current.time_offset:.2f}, {now:.2f}, {current.description}, {current.action}, {current.executed}")

            self._update_progress_label(now)

            time.sleep(cfg.PUMP_SCHEDULER_THREAD_LOOP_DELAY)

        self._running.clear()
        if self._progress_label:
            self._progress_label.config(text="Pump scheduler finished")
        self._logger.add_entry("scheduler", f"Pump scheduler finished all actions of '{self._sequence_name}' sequence")
        cfg.ALLOW_SPECTROMETER_STATUS_UPDATES = True # allow status update from spectrometer now

class PumpController:
    """
    AI: Manages a 3-pump system using a scheduler and provides high-level control logic
    like initialization, priming, and shutdown.
    """

    def __init__(self, gui_app, logger_handle, log_pump_commands=()):
        self.gui = gui_app
        self.logger = logger_handle

        self._state = cfg.PUMP_SCHEDULER_IDLE  # Internal state tracker of PumpScheduler

        # Initial state variable for GUI state polling
        self.pump_states = [cfg.PUMP_STATE_DISCONNECTED] * 3

        # flow rates saved by pause_sequence() before pausing the pumps, to be restored by resume_sequence
        self._paused_target_flows = [0.0, 0.0, 0.0]

        # Create and initialize UART connectivity for 3 syringe pumps
        self.pumps = [
            SyringePump(logger_handle, cfg.PUMP_UARTS[cfg.PUMP_SOLVENT], log_commands=(cfg.PUMP_SOLVENT in log_pump_commands)),
            SyringePump(logger_handle, cfg.PUMP_UARTS[cfg.PUMP_CATALYST], log_commands=(cfg.PUMP_CATALYST in log_pump_commands)),
            SyringePump(logger_handle, cfg.PUMP_UARTS[cfg.PUMP_QUENCHER], log_commands=(cfg.PUMP_QUENCHER in log_pump_commands))
        ]

        # Shared scheduler for all pump actions
        self.scheduler = PumpScheduler(logger_handle)


    def set_progress_label(self, label_widget):
        """
        AI: Attach a Tkinter Label widget to the scheduler for live progress feedback.
        """
        self.scheduler.set_progress_label(label_widget)


    def poll_state(self):
        """
        AI: Periodically called from GUI to refresh pump states.
        """
        # IMPORTANT! do not call any pump methods with the scheduler running to avoid racing conditions
        # Just read the current/last registered state using get_pump_states()
        if self._state == cfg.PUMP_SCHEDULER_IDLE:
            for pump in self.pumps:
                pump.poll()
        for i, pump in enumerate(self.pumps):
            self.pump_states[i] = pump.get_state()

    def get_pump_states(self):
        return self.pump_states

    def initialize_pumps(self):
        """
        AI: Run reset/version/unit initialization sequence for all 3 pumps.
        """
        self.scheduler.clear()
        t = 0.0
        for i, pump in enumerate(self.pumps):
            self.scheduler.add_action(t, pump.reset, f"Reset {cfg.PUMP_NAMES[i]}")
            t += cfg.PUMP_INIT_STEP_DELAY
            self.scheduler.add_action(t, pump.get_version, f"Get version {cfg.PUMP_NAMES[i]}")
            t += cfg.PUMP_INIT_STEP_DELAY
            self.scheduler.add_action(t, lambda p=pump: p.set_volume_units("ML"), f"Set units {cfg.PUMP_NAMES[i]}")
            t += cfg.PUMP_INIT_STEP_DELAY

        # Print schedule <--- TEMPORARY FOR DEBUGGING ONLY
        print("\n--- Initialization Schedule ---")
        for action in self.scheduler._actions:
            print(f"{action.time_offset:.2f}, {action.description}, {action.action}")

        self.scheduler.set_sequence_name("Initializing pumps")
        self.scheduler.start()


    def _handle_sequence_completion(self):
        """
        Called at the very end of scheduler sequence to finalize state and set flags.
        """
        if self._state == cfg.PUMP_SCHEDULER_PRIMING:
            cfg.PUMPS_PRIMED_OK = True
            self.logger.add_entry("controller", "Priming completed successfully")
            if self.gui:
                self.gui.status_label.config(text="Priming complete")

        elif self._state == cfg.PUMP_SCHEDULER_RUNNING_EXPERIMENT:
            cfg.EXPERIMENT_FINISHED_OK = True
            # closing files and logging the events
            spectrum2D_file_path = files.spectrum2DFileClose()
            if spectrum2D_file_path:
                self.logger.add_entry("files", f"Saved and closed a 2D spectrum file '{spectrum2D_file_path}'")
            else:
                self.logger.add_entry("files", f"Could not save 2D spectrum file '{spectrum2D_file_path}.", error=True)

            emissionData_file_path = files.emissionDataFileClose()
            if emissionData_file_path:
                self.logger.add_entry("files", f"Saved and closed fluorescence emission file '{emissionData_file_path}'")
            else:
                self.logger.add_entry("files", f"Could not save fluorescence emission file.", error=True)

            files.experimentStepsResult = self.gui.data_reader.step_detector.get_steps()
            if len(files.experimentStepsResult) > 0:
                self.logger.add_entry("analysis", f"Calculating Stern-Volmer analysis results for experiment {files.experimentData["Name"]}")
                files.experimentSVdataResult = self.gui.data_reader.step_detector.calculateSVdata(files.experimentData)
            SVData_file_path = files.rewriteSVdataFile()
            if SVData_file_path is not None:
                if SVData_file_path:
                    self.logger.add_entry("files", f"Saved the Stern-Volmer analysis data in '{SVData_file_path}'")
                else: # files.rewriteSVdataFile() returns an empty string if the empty file was deleted
                    self.logger.add_entry("analysis", f"No steps detected, Stern-Volmer results file will not be created.")
            else:
                self.logger.add_entry("files", f"Could not save Stern-Volmer results file.", error=True)
            self.logger.add_entry("controller", "Experiment sequence completed")
            if self.gui:
                self.gui.status_label.config(text="Experiment finished")

        self._state = cfg.PUMP_SCHEDULER_IDLE
        # TODO! check if this flag is to be cleared here!
        cfg.EXPERIMENT_IS_RUNNING = False


    def _poll_and_check(self):
        """
        Unified polling and error handler for any scheduler phase.
        """
#        print(f" *>>>>> _poll_and_check state {self._state}")
        any_error = False

        for i, pump in enumerate(self.pumps):
            pump.poll()
            state = pump.get_state()
            self.pump_states[i] = state

            if state == cfg.PUMP_STATE_ERROR:
                self.logger.add_entry("controller", f"{cfg.PUMP_NAMES[i]} in ERROR state - aborting", error=True)
                any_error = True

        if any_error:
            for p in self.pumps:
                p.stop()
            self.scheduler.stop()

            if self._state == cfg.PUMP_SCHEDULER_PRIMING:
                cfg.PUMPS_PRIMED_OK = False
                # print(f" *>>>>> {cfg.PUMPS_PRIMED_OK=}")

            if self.gui:
                self.gui.status_label.config(text="Pump error - sequence aborted")

            self._state = cfg.PUMP_SCHEDULER_IDLE


    def prime_pumps(self):
        """
        Runs a step-by-step priming sequence. Stops and marks failed on pump error.
        Sets cfg.PUMPS_PRIMED_OK = True only on successful finish.
        """
        self.scheduler.clear()
        self._state = cfg.PUMP_SCHEDULER_PRIMING  # Enter PRIMING phase
        cfg.PUMPS_PRIMED_OK = False  # Reset priming success flag

        t = 0.0

        for step_index, (step_pump, step_volume, step_flowrate) in enumerate(files.primingPumpProgram):
            pump = self.pumps[step_pump]
            self.scheduler.add_action(t, lambda p=pump, d=files.syringeDiameters[step_pump]: p.set_diameter(d),
                                      f"Set diameter {cfg.PUMP_NAMES[step_pump]}")
            t += cfg.PUMP_PRIMING_STEP_DELAY
            self.scheduler.add_action(t, lambda p=pump, v=step_volume: p.set_volume(v),
                                      f"Set volume {cfg.PUMP_NAMES[step_pump]}")
            t += cfg.PUMP_PRIMING_STEP_DELAY
            self.scheduler.add_action(t, lambda p=pump, r=step_flowrate: p.set_pumping_rate(r),
                                      f"Set rate {cfg.PUMP_NAMES[step_pump]}")
            t += cfg.PUMP_PRIMING_STEP_DELAY
            self.scheduler.add_action(t, pump.run, f"Run {cfg.PUMP_NAMES[step_pump]}")
            t += cfg.PUMP_PRIMING_STEP_DELAY
            step_duration = (step_volume / step_flowrate) * 60  # seconds
            tp = t
            step_end = t + step_duration
            while tp < step_end:
                self.scheduler.add_action(tp, self._poll_and_check, f"Poll {cfg.PUMP_NAMES[step_pump]} at {tp:.2f}s")
                tp += cfg.PUMP_POLLING_INTERVAL

            self.scheduler.add_action(step_end, pump.stop, f"Stop {cfg.PUMP_NAMES[step_pump]}")
            t = step_end + cfg.PUMP_PRIMING_STEP_DELAY
            self.scheduler.add_action(t, lambda p=pump: p.set_volume(0),
                                      f"Clear volume {cfg.PUMP_NAMES[step_pump]}")
            t += cfg.PUMP_PRIMING_STEP_DELAY

        self.scheduler.add_action(t, self._handle_sequence_completion, "Finalize sequence state")

        #### Print schedule <--- TEMPORARY FOR DEBUGGING ONLY
        # print("\n--- Priming Schedule ---")
        # for action in self.scheduler._actions:
        #     print(f"{action.time_offset:.2f}, {action.description}, {action.action}")

        self.scheduler.set_sequence_name("Priming pumps")
        self.scheduler.start()


    def run_experiment_program(self):
        self.scheduler.clear()
        self._state = cfg.PUMP_SCHEDULER_RUNNING_EXPERIMENT  # Enter EXPERIMENT phase
        cfg.EXPERIMENT_FINISHED_OK = False  # Reset experiment finished flag

        steps = files.experimentPumpProgram
        n = len(steps)
        previous_flows = [0.0, 0.0, 0.0] # since we only want to run the pump when its flow rate changes from 0 to non-zero

        for step_index in range(n):
            step_t0, f1, f2, f3 = steps[step_index]
            flows = [f1, f2, f3]

            # === Schedule setting flow rate
            for i, flow in enumerate(flows):
                self.scheduler.add_action(step_t0, lambda p=self.pumps[i], r=flow: p.set_pumping_rate(r),
                                          f"Set flow {flow} on {cfg.PUMP_NAMES[i]}")
                step_t0 += cfg.PUMP_EXPERIMENT_STEP_DELAY
            step_t1 = steps[step_index + 1][0] if step_index + 1 < n else step_t0 + cfg.PUMP_POST_EXPERIMENT_PADDING_TIME_S
 
            # === Schedule run for pumps that transition from 0 to non-zero
            for i, flow in enumerate(flows):
                if previous_flows[i] == 0.0 and flow > 0.0:
                    self.scheduler.add_action(step_t0 + cfg.PUMP_EXPERIMENT_STEP_DELAY,
                                              self.pumps[i].run,
                                              f"Run {cfg.PUMP_NAMES[i]}")

            # === Schedule polling throughout this segment
            tp = step_t0
            while tp < step_t1:
                self.scheduler.add_action(tp, self._poll_and_check, f"Poll at {tp:.2f}s")
                tp += cfg.PUMP_POLLING_INTERVAL

            previous_flows = flows

        # === Stop unconditionally all pumps at the end
        # TODO: change this AI-generated finalization logic to full_stop() methods stopping each pump twice unit it responds with 00S.
        final_t = steps[-1][0] + cfg.PUMP_POST_EXPERIMENT_PADDING_TIME_S
        for i in range(3):
            self.scheduler.add_action(final_t, self.pumps[i].stop, f"Final stop {cfg.PUMP_NAMES[i]}")
            self.scheduler.add_action(final_t + 0.1, self._poll_and_check, f"Poll after stop {cfg.PUMP_NAMES[i]}")
            self.scheduler.add_action(final_t + cfg.PUMP_EXPERIMENT_STEP_DELAY,
                                      self.pumps[i].stop,
                                      f"Second stop {cfg.PUMP_NAMES[i]}")
            self.scheduler.add_action(final_t + cfg.PUMP_EXPERIMENT_STEP_DELAY + 0.1,
                                      self._poll_and_check,
                                      f"Poll after second stop {cfg.PUMP_NAMES[i]}")

        # === Finalization logic
        self.scheduler.add_action(final_t + cfg.PUMP_EXPERIMENT_STEP_DELAY, self._handle_sequence_completion, "Finalize sequence state")

        #### Print schedule <--- TEMPORARY FOR DEBUGGING ONLY
        # print("\n--- Experiment Schedule ---")
        # for action in self.scheduler._actions:
        #    print(f"{action.time_offset:.2f}, {action.description}, {action.action}")

        self.scheduler.set_sequence_name(f"Experiment {files.experimentData['Name']}")
        self.scheduler.start()

    def pause_sequence(self):
        """
        AI: Pause the experiment sequence: stop scheduler and pumps, adjust timeline.
        Only affects a running experiment, does not interfere with other sequences.
        """
        if self._state != cfg.PUMP_SCHEDULER_RUNNING_EXPERIMENT:
            return

        if not self.scheduler.is_running():
            self.logger.add_entry("controller", "Cannot pause: scheduler not running", error=True)
            return

        self.scheduler.pause()

        # === Save current target flows for restoring when the sequence is resumed
        self._paused_target_flows = [self.pumps[i].pumpFlowRate for i in range(3)]

        # Set all pumps flow to zero
        for pump in self.pumps:
            # pump.set_pumping_rate(0.0)
            pump.stop()

        if self.gui:
            self.gui.status_label.config(text="Pump sequence paused")

        self.logger.add_entry("controller", "Pump sequence paused")
        self._state = cfg.PUMP_SCHEDULER_PAUSED
        cfg.EXPERIMENT_IS_PAUSED = True

    def resume_sequence(self):
        """
        AI: Resume the paused experiment sequence.
        The short sequence restoring the pump flows and restarting pumps (injected_actions) is injected on top of the paused sequence.
        Then the sequence timings are readjusted for its duration, and the scheduler is restarted.
        """
        if self._state != cfg.PUMP_SCHEDULER_PAUSED:
            self.logger.add_entry("controller", "Cannot resume: sequence not paused", error=True)
            return

        paused_action_index = self.scheduler._current_action_index
        paused_action_time_offset = self.scheduler._actions[paused_action_index].time_offset
        restore_time = 0
        # print(f"{self.scheduler._actions[paused_action_index].time_offset=}")
        injected_actions = []

        # === Build restoring actions (set flow + run if necessary) for each pump with non-zero flowrate
        for i, pump in enumerate(self.pumps):
            target_flow = self._paused_target_flows[i]
            if target_flow > 0.0:
                injected_actions.append(PumpAction(paused_action_time_offset + restore_time, lambda p=pump, r=target_flow: p.set_pumping_rate(r), f"Restore flow {target_flow} on {cfg.PUMP_NAMES[i]}"))
                restore_time += cfg.PUMP_EXPERIMENT_STEP_DELAY
                injected_actions.append(PumpAction(paused_action_time_offset + restore_time, pump.run, f"Run {cfg.PUMP_NAMES[i]}"))
                restore_time += cfg.PUMP_EXPERIMENT_STEP_DELAY
            injected_actions.append(PumpAction(paused_action_time_offset + restore_time, pump.poll, f"Poll {cfg.PUMP_NAMES[i]}"))
            restore_time += cfg.PUMP_EXPERIMENT_STEP_DELAY

        # === Shift all existing actions by total restore_time
        # print(f"{restore_time=}")
        for action in self.scheduler._actions[paused_action_index:]:
            action.time_offset += restore_time

        # === Inject restore actions into scheduler
        self.scheduler._actions[paused_action_index:paused_action_index] = injected_actions

        # === Adjust the scheduler clock
        self.scheduler.resume()

        if self.gui:
            self.gui.status_label.config(text="Pump sequence resumed")

        self.logger.add_entry("controller",
                              f"Pump sequence resumed after injecting {len(injected_actions)} restore actions")
        self._state = cfg.PUMP_SCHEDULER_RUNNING_EXPERIMENT
        cfg.EXPERIMENT_IS_PAUSED = False


    def abort_sequence(self):
        """
        AI: Abort the running pump sequence immediately and safely.
        """
        self.scheduler.stop()  # Terminate any further dispatch
        self.scheduler.clear()

        t = 0.5
        for i, pump in enumerate(self.pumps):
            self.scheduler.add_action(t, pump.stop, f"Stop {cfg.PUMP_NAMES[i]}")
            t += cfg.PUMP_INIT_STEP_DELAY
            self.scheduler.add_action(t, pump.stop, f"Second stop {cfg.PUMP_NAMES[i]}")
            t += cfg.PUMP_INIT_STEP_DELAY

        self.scheduler.add_action(t, lambda: self._handle_sequence_completion(),
                                  "Finalize sequence state")

        self.scheduler.set_sequence_name("Aborting sequence")
        self.scheduler.start()

        if self.gui:
            self.gui.status_label.config(text="Pump sequence aborted")

        self.logger.add_entry("controller", "Pump sequence aborted")
        self._state = cfg.PUMP_SCHEDULER_IDLE
        cfg.EXPERIMENT_IS_PAUSED = False
        cfg.EXPERIMENT_IS_RUNNING = False


    def close(self):
        """
        AI: Stop and detach all pumps gracefully.
        """
        self.scheduler.clear()
        t = 0.0
        for i, pump in enumerate(self.pumps):
            self.scheduler.add_action(t, pump.stop, f"Stop {cfg.PUMP_NAMES[i]}")
            t += cfg.PUMP_CLOSE_STEP_DELAY
            self.scheduler.add_action(t, pump.detach, f"Detach {cfg.PUMP_NAMES[i]}")
            t += cfg.PUMP_CLOSE_STEP_DELAY
        self.scheduler.set_sequence_name(f"Closing pump controller")
        self.scheduler.start()