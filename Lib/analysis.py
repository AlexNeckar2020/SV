import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, Dict

import Lib.config as cfg


@dataclass
class StepData:
    step_t_min: float
    step_t_max: float
    step_t_mid: float # step midpoint
    value_count: int # number of data points
    value_average: float # average
    value_stddev: float # standard deviation
    value_sem: float # standard error of mean


@dataclass
class SternVolmerData:
    conc_quencher_M: float
    ratio_I0_I: float
    ser_I0_I: float # standard error of the ratio (applying delta method)


class StepDetector:
    def __init__(self):
        self.buffer: List[Tuple[float, float]] = []
        self.steps: Dict[int, StepData] = {}
        self.current_step_values: List[float] = []
        self.current_step_times: List[float] = []
        self.window_values: List[float] = []
        self.outlier_count: int = 0
        self.inside_step: bool = False
        self.step_index: int = 0
        self._experimentData = None
        self._SVdata: List[SternVolmerData] = []

    def reset(self):
        self.__init__()

    def add_value(self, timestamp: float, value: float):
   #     self.buffer.append((timestamp, value))
        self._process(timestamp, value)

    def process_full_dataset(self, time_points: list[float] | np.ndarray, emission_data: list[float] | np.ndarray) -> bool:
        """
        Processes an entire dataset from scratch using the current step detection logic.

        Resets the detector, loads the buffer from the given numpy arrays,
        and replays the full signal through the step detection pipeline.

        :param time_points: np.ndarray: 1D numpy array of time values as floats.
        :param emission_data: np.ndarray: 1D numpy array of emission data values as floats.
        :return: True if arrays are of equal lengths and processing was done, False otherwise.
        """
        # --- Ensure the arrays are non-empty and have at least enough points for a single step ---
        min_len = min(len(time_points), len(emission_data))
        if min_len < cfg.ANALYSIS_MIN_STEP_DURATION:
            return False

        # --- Reset the detector state to ensure clean reprocessing ---
        self.reset()

        # --- Iterate through the dataset, simulating live input ---
        for timestamp, value in zip(time_points[:min_len], emission_data[:min_len]):
            # Use the existing _process() logic directly
            self._process(timestamp, value)

        return True

    def get_steps(self):
        return self.steps

    def _rms(self, values: List[float]) -> float:
        if not values:
            return 0.0
        mean = np.mean(values)
        return np.sqrt(np.mean([(x - mean) ** 2 for x in values]))

    def _process(self, timestamp: float, value: float):
        # --- 1. Add current sample to full buffer of (timestamp, value) pairs ---
        self.buffer.append((timestamp, value))

        # --- 2. Add the value to the sliding window (used for RMS computation only) ---
        self.window_values.append(value)

        # --- 3. Ensure the window stays at most WINDOW_SIZE elements long ---
        if len(self.window_values) > cfg.ANALYSIS_WINDOW_SIZE:
            self.window_values.pop(0)

        # --- 4. If the window is not full yet, we cannot compute RMS reliably ---
        # However, we should NOT return here because we may still be inside a step!
        if len(self.window_values) < cfg.ANALYSIS_WINDOW_SIZE:
            if self.inside_step:
                # If we're already inside a step, we still accumulate
                self.current_step_values.append(value)
                self.current_step_times.append(timestamp)
            return  # Wait for first RMS decision

        # --- 5. At this point, we have a full RMS window ---
        rms = self._rms(self.window_values)

        # --- 6. If the window appears stable (RMS below threshold) ---
        if rms < cfg.ANALYSIS_RMS_TOLERANCE:
            if not self.inside_step:
                # --- 6a. Start of a new stable region (new step) ---

                # Extract the last ANALYSIS_WINDOW_SIZE entries from buffer to seed the step
                # This gives us correct timestamps and values for the starting window
                recent_buffer = self.buffer[-cfg.ANALYSIS_WINDOW_SIZE:]

                # Initialize the step data lists with these values
                self.current_step_times = [t for t, _ in recent_buffer]
                self.current_step_values = [v for _, v in recent_buffer]

                self.inside_step = True

                # --- 6b. Additionally, check if buffer before the window was also stable ---
                # This will retroactively include earlier values into the step (avoids loss)
                # We walk backward before the window and add values as long as they seem stable
                i = len(self.buffer) - cfg.ANALYSIS_WINDOW_SIZE - 1
                while i >= 0:
                    prev_value = self.buffer[i][1]
                    # Include values if they don't introduce instability
                    # You may use a simpler heuristic here instead of full RMS
                    extended_window = [prev_value] + self.current_step_values[:cfg.ANALYSIS_WINDOW_SIZE - 1]
                    if self._rms(extended_window) < cfg.ANALYSIS_RMS_TOLERANCE:
                        self.current_step_times.insert(0, self.buffer[i][0])
                        self.current_step_values.insert(0, prev_value)
                        i -= 1
                    else:
                        break  # Stop including once instability is found

            else:
                # --- 6c. Continuing an ongoing step: append current sample ---
                self.current_step_times.append(timestamp)
                self.current_step_values.append(value)

        else:
            # --- 7. If signal is now unstable (RMS above threshold) ---
            if self.inside_step:
                # Finalize the current step, excluding the current unstable value
                self._finalize_step()
                self.inside_step = False

                # Reset the window to just this value to allow fresh detection
                self.window_values = [value]

    def _finalize(self):
        """Finalize the current step if it's still in progress at the end of the data stream."""
        # TODO: call it only once for the final datapoint in add_data()
        if self.inside_step:
            self._finalize_step()
            self.inside_step = False

    def _finalize_step(self):
        number_of_datapoints = len(self.current_step_values)
        if number_of_datapoints >= cfg.ANALYSIS_MIN_STEP_DURATION:
            avg = float(np.mean(self.current_step_values))
            std = float(np.std(self.current_step_values, ddof=1))
            sem = std / np.sqrt(number_of_datapoints)
            t_min = self.current_step_times[0]
            t_max = self.current_step_times[-1]
            t_mid = (t_min + t_max) / 2
            step_data = StepData(t_min, t_max, t_mid, number_of_datapoints, avg, std, sem)
            self.steps[self.step_index] = step_data
            self.step_index += 1

        # Clear state for next step
        self.current_step_values.clear()
        self.current_step_times.clear()

    def _get_quencher_concentration_at_t(self, timepoint_s: float) -> float | None:
        timepoint_step_end_s = 0.0
        timepoint_step_params = None
        stock_quencher_C_mM = float(self._experimentData["Syringes"][cfg.PUMP_NAMES[cfg.PUMP_QUENCHER]]["concentration (mM)"]) # C of stock quencher soln in syringe (mM)
        print(f" ::: {stock_quencher_C_mM=} ")
        for program_step_params in self._experimentData["Program"].values():
            timepoint_step_end_s += float(program_step_params["time (min)"]) * 60
            if timepoint_s < timepoint_step_end_s:
                timepoint_step_params = program_step_params
                break
        if timepoint_step_params is None: # timepoint is beyond the end of experiment program
            return None
        flow_solvent_mLmin = float(timepoint_step_params["PUMP1 flow (mL/min)"])
        flow_catalyst_mLmin = float(timepoint_step_params["PUMP2 flow (mL/min)"])
        flow_quencher_mLmin = float(timepoint_step_params["PUMP3 flow (mL/min)"])
        tmp_var = stock_quencher_C_mM * flow_quencher_mLmin / (flow_solvent_mLmin + flow_catalyst_mLmin + flow_quencher_mLmin) # this will raise exception if all flows = 0
        print(f" ::: [Q] at {timepoint_s:.2f} s = {tmp_var}")
        return tmp_var

    def _get_experiment_I0_step_key(self) -> int:
        """
        Returns key (int number) of the step having max intensity from the step list - this step should correspond to emission of catalyst without any quencher added.
        Later, additional definitions or checks as to the step order may be defined here
        :return: Max average emission intensity from the detected steps.
        """
        # return max(step.value_average for step in self.steps.values()) <--- this would return the max value_average itself
        return max(self.steps, key=lambda k: self.steps[k].value_average)

    def _get_I0_from_twopoint_extrapolation(self, I1: float, I2: float, C1: float, C2: float) -> float | None:
        """
        Calculates the estimated emission intensity at zero quencher concentration if the corresponding step is absent from StepData.
        This will need a separate warning line in SVresultsFile output.
        :return: I0 extrapolated from two data points (I1; C1), (I2; C2), None if I1 * C1 = I2 * C2 results in division by zero.
        """
        try:
            return 1 + I1 * (I2 - I1) / (I1 * C1 - I2 * C2)
        except ZeroDivisionError:
            return None


    def calculateSVdata(self, exp_data) -> list[SternVolmerData]:
        # TODO: this needs an extra check and rethinking! otherwise reports wrong data, because the assumption in _get_experiment_I0_step_key() is wrong
        #  If c(quencher) != 0 in first step, I0 must be extrapolated from two pairs (I1; C1), (I2; C2) with the highest I
        self._experimentData = exp_data
        I0_step_key = self._get_experiment_I0_step_key() # identifying the step with catalyst without quencher by highest emission brightness
        I0 = self.steps[I0_step_key].value_average # I0 intensity value from this step
        I0_N = self.steps[I0_step_key].value_count # value count of this step
        I0_sem = self.steps[I0_step_key].value_sem # standard error of mean from this step
        print(f" ::: I0 data: {I0_N=}, {I0=:.2f}, {I0_sem=:.2f}")
        for step in self.steps.values():
            I = step.value_average
            # simple sanity check to avoid division by zero and value blowups
            if I * 100 < I0:
                continue
            I_N = step.value_count
            I_sem = step.value_sem
            print(f" ::: I data: {I_N=}, {I=:.2f}, {I_sem=:.2f}")
            self._SVdata.append(SternVolmerData(self._get_quencher_concentration_at_t(step.step_t_mid),
                                I0 / I,
                                I0 / I * np.sqrt((I0_sem / I0) ** 2 + (I_sem / I) ** 2)) )
        return self._SVdata

