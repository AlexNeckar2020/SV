""" This code was developed with assistance from ChatGPT (OpenAI, 2025)
"""

import os
import csv
import json
from datetime import datetime
from typing import Dict, List

import Lib.config as cfg
from Lib.analysis import StepData, SternVolmerData

""" global variables: names and paths of the currently used files """
# current experiment file and pump program
experimentFilePath = None
experimentFileName = None
experimentData = {}
experimentPumpProgram = [] # entries: (step_duration in s, pump1_flow, pump2_flow, pump3_flow in mL/min)
experimentProgramTotalTime = 0 # in s
experimentProgramMaxFlow = 0 # in mL/min
lastSpectrumTimepoint = 0.0 # used by SpectrometerEmulator for simulating quenched emission from experimentPumpProgram

# analysis results
experimentStepsResult: Dict[int, StepData] = {}
# experimentSVdataResult: Dict[int, SternVolmerData] = {}
experimentSVdataResult: List[SternVolmerData] = []

# result file names
SVresultsFile = None # Stern-Volmer results file handle
emissionDataFile = None # emission over time file handle
UVVis2dDataFile = None # 2D spectrum file handle

# priming program
primingPumpProgram = [] # entries: (pump UART, volume in mL, flow in mL/min)

# settings for syringes
syringesData = {} # default settings for syringes
syringeDiameters = [0, 0, 0] # syringe diameters: [pump1_diam, pump2_diam, pump3_diam in mm]

def parseExperimentCSV(file_path):
    global experimentData, experimentPumpProgram, experimentProgramTotalTime, experimentProgramMaxFlow, experimentFileName
    experimentData = {}
    experimentPumpProgram = []
    experimentProgramTotalTime = 0
    experimentProgramMaxFlow = 0
    cfg.EXPERIMENT_LOADED_OK = False

    try:
        with open(file_path, newline='', encoding='utf-8') as csvfile:
            reader = list(csv.reader(csvfile))  # Convert reader to a list for easier index manipulation

            # Entry 1: A1 as key, B1 as value - experiment name
            entry1_key = reader[0][0]  # A1 (Name)
            assert entry1_key == "Name", "A1: 'Name' is expected"
            entry1_value = reader[0][1] if len(reader[0]) > 1 else ""  # B1 (Experiment name)
            experimentData[entry1_key] = entry1_value

            # Ensure row 2 is empty
            assert not any(reader[1]), "A2: row 2 is not empty" # Row 2 is expected to be empty

            # Entry 2: A3 as key, B3-D3 as headers -  Syringes configuration structure
            entry2_key = reader[2][0]  # A3
            assert entry2_key == "Syringes", "A3: 'Syringes' is expected"
            headers = reader[2][1:3]  # B3, C3
            assert headers == ["Volume (mL)", "concentration (mM)"], "B3:C3: headers for Syringes table columns are expected" # to be corrected later, according to what info is needed here
            entry2_dict = {}

            # Read subentries A4-A6 as keys, B4-D6 as values
            pump_names = [reader[i][0] for i in range(3, 6)]  # A4 to A6 (0-based indexing)
            assert pump_names == [cfg.UART_DEVICES[uart]["name"] for uart in cfg.PUMP_UARTS.values()], "A4:A6: headers for Syringes table rows are expected"
            for i in range(3, 6):  # Rows 4 to 6 (0-based index)
                sub_key = reader[i][0]  # A4, A5, A6
                values = reader[i][1:3]  # B4..6, C4..6
                # the input contains only positive floats written with decimal dot
                assert all(s.replace('.', '', 1).isdigit() and float(s) >= 0 for s in values), "A4:D6: non-float input in Syringes table"
                entry2_dict[sub_key] = dict(zip(headers, values))

            experimentData[entry2_key] = entry2_dict

            # Ensure row 7 is empty
            assert not any(reader[6]) # Row 7 is expected to be empty

            # Entry 3: A8 as key
            entry3_key = reader[7][0]  # A8
            assert entry3_key == "Program", "A8: 'Program' is expected"

            # Read B9-E9 as dictionary headers (limit to four columns max)
            headers = reader[8][1:5]  # B9, C9, D9, E9
            assert headers == ["time (min)", "PUMP1 flow (mL/min)", "PUMP2 flow (mL/min)", "PUMP3 flow (mL/min)"], "B9:E9: headers for Program table columns are expected" # to be corrected later if needed
            entry3_dict = {}

            # Read subentries starting from A10, until an empty row is encountered
            i = 9  # Row index (10 in 1-based Excel indexing)
            while i < len(reader) and any(reader[i]):
                sub_key = reader[i][0]  # A10, A11, ...
                assert sub_key.isdigit() and int(sub_key) == i-8, "A10...: Program step numbers are not in order" # make sure that experiment steps start with 1 and are properly numbered
                values = reader[i][1:5]  # B10, C10, D10, E10 (limit to 4 columns, corresponding to the headers above)
                assert all(s.replace('.', '', 1).isdigit() and float(s) >= 0 for s in
                           values), "B10...:E10...: non-float input in Program table"  # the input contains only positive floats written with decimal dot or zeros
                entry3_dict[sub_key] = dict(zip(headers, values))
                i += 1

            experimentData[entry3_key] = entry3_dict

    except AssertionError as error_msg:
        experimentData = {}
        # print(error_msg)
        return error_msg
    else:
        print(experimentData)
        RecordExperimentProgram()
        cfg.EXPERIMENT_LOADED_OK = True  # experiment CSV file has been parsed and the experiment program was recorded
        return ""

def RecordExperimentProgram():
    global experimentData, experimentProgramTotalTime, experimentProgramMaxFlow, experimentPumpProgram

    experimentPumpProgram = []
    for programStepEntry, (program_step_key, program_step_entry) in enumerate(experimentData["Program"].items(), start=1):
        program_step_length_s = float(program_step_entry["time (min)"])*60
        experimentPumpProgram.append((experimentProgramTotalTime, float(program_step_entry["PUMP1 flow (mL/min)"]),
                                      float(program_step_entry["PUMP2 flow (mL/min)"]), float(program_step_entry["PUMP3 flow (mL/min)"])))
        experimentProgramMaxFlow = max(experimentProgramMaxFlow, sum(experimentPumpProgram[-1][-3:])) # adding up all flowrates from the last element of the list using tuple slicing
        experimentProgramTotalTime += program_step_length_s
    # adding final entry which also stop pumps at the end
    experimentPumpProgram.append((experimentProgramTotalTime, 0.0, 0.0, 0.0))
    # print(f" ::: pump program: {experimentPumpProgram}")
    # print(f" ::: experiment total time: {experimentProgramTotalTime} s, max flow: {experimentProgramMaxFlow}")

def LoadSyringesCSV() -> str:
    global syringesData
    try:
        with open(cfg.SYRINGES_CSV_FILE, newline='', encoding='utf-8') as csvfile:
            reader = list(csv.reader(csvfile))  # Convert reader to a list for easier index manipulation
            headers = reader[0][0:7]  # A1, B1, C1, D1, E1, F1
            assert headers == ["Volume (mL)", "Plunger diameter (mm)", "Max volume (mL)", "Max flow rate (mL/min)",
                               "Prime volume (mL)", "Prime flow rate (mL/min)"], "A1:F1: headers for default syringe settings table are expected"  # to be corrected later, according to what info is needed here
            # Read subentries starting from A2, until an empty row is encountered
            i = 1  # Row index (2 in 1-based Excel indexing)
            while i < len(reader) and any(reader[i]):
                syringe_volume_key = reader[i][0]  # A2, A3, ...
                assert syringe_volume_key.isdigit() and int(syringe_volume_key) > 0, "A2...: Syringe volume must be a positive integer"  # make sure that experiment steps start with 1 and are properly numbered
                values = reader[i][1:7]  # B10, C10, D10, E10, F10 (limit to 5 columns, corresponding to the headers above)
                assert all(s.replace('.', '', 1).isdigit() and float(s) >= 0 for s in
                           values), "B2...:F2...: non-float input in default syringe settings table"  # the input contains only positive floats written with decimal dot or zeros
                syringesData[syringe_volume_key] = dict(zip(headers[1:], values))
                i += 1

    except AssertionError as error_msg:
        syringesData = {}
        # print(error_msg)
        return str(error_msg)
    else:
        return ""

# returns a dictionary with settings, or None if no syringe with syringe_volume found in syringesData
def GetDefaultSyringeSettings(syringe_volume):
    # print(f"{syringe_volume} syringe: {syringesData.get(str(syringe_volume))}")
    return syringesData.get(str(syringe_volume))

# loads syringeDiameters with values
def UpdateSyringeDiameters(syringe_volume_pump1, syringe_volume_pump2, syringe_volume_pump3):
    syringe_data = syringesData.get(str(syringe_volume_pump1))
    syringeDiameters[0] = float(syringe_data["Plunger diameter (mm)"])
    syringe_data = syringesData.get(str(syringe_volume_pump2))
    syringeDiameters[1] = float(syringe_data["Plunger diameter (mm)"])
    syringe_data = syringesData.get(str(syringe_volume_pump3))
    syringeDiameters[2] = float(syringe_data["Plunger diameter (mm)"])
    # print(syringeDiameters)

# truncates filename longer with max_length to max_length-3 and appends them with "..." for displaying in GUI
def truncate_long_filename(fname_str: str, max_length: int) -> str:
    if len(fname_str) <= max_length:
        return fname_str
    else:
        return fname_str[:max_length - 3] + '...'

##### functions dealing with the 2D experiment spectrum file
def spectrum2DFileCreate(wavelengths) -> str:
    global UVVis2dDataFile, experimentData, experimentFileName
    now = datetime.now()
    file_path = cfg.RESULTS_DIR / (now.strftime("%Y-%m-%d_%H-%M-%S_") + experimentFileName + "_2Dspectrum.csv")
    UVVis2dDataFile = open(file_path, mode='w', newline='', encoding='utf-8')
    if UVVis2dDataFile:
        line = experimentData["Name"] + "\n"
        UVVis2dDataFile.write(line)  # write experiment name in A1 cell
        line = ",wavelength [nm]," + ",".join(f"{wavelength_nm:.3f}" for wavelength_nm in wavelengths) + "\n"
        UVVis2dDataFile.write(line)  # write a caption for X-values (B2) and wavelengths as X-headers (C2, D2 ...)
        line = "time [s]" + "\n"
        UVVis2dDataFile.write(line)  # write a caption for X-values (A3)
        return file_path
    return ""  # could not open spectrum2DFile

def spectrum2DFileAddSpectrum(timepoint: float, spectrum) -> bool:
    global UVVis2dDataFile, lastSpectrumTimepoint
    lastSpectrumTimepoint = timepoint
    if UVVis2dDataFile:
        new_line = f"{timepoint:.2f},," + ",".join(f"{value:.3f}" for value in spectrum) + "\n" # filling the table aligned to headers created in spectrum2DFileCreate()
        UVVis2dDataFile.write(new_line)
        return True
    return False

def spectrum2DFileClose() -> str | None:
    global UVVis2dDataFile
    if UVVis2dDataFile:
        file_path = UVVis2dDataFile.name
        UVVis2dDataFile.close()
        UVVis2dDataFile = None
        return file_path
    return None


##### functions dealing with fluorescence emission over time file
def emissionDataFileCreate() -> str:
    global emissionDataFile, experimentData, experimentFileName
    now = datetime.now()
    file_path = cfg.RESULTS_DIR / (now.strftime("%Y-%m-%d_%H-%M-%S_") + experimentFileName + "_emission.csv")
    emissionDataFile = open(file_path, mode='w', newline='', encoding='utf-8')
    if emissionDataFile:
        line = experimentData["Name"] + "\n"
        emissionDataFile.write(line)  # write experiment name in A1 cell
        line = "time [s], fluorescence intensity [a.u.]\n"
        emissionDataFile.write(line)  # write a caption for X-values (time, A2) and Y-values (intensity, B2)
        return file_path
    return ""  # could not open emissionDataFile

def emissionDataSaveDatapoint(timepoint: float, value: float) -> bool:
    global emissionDataFile, lastSpectrumTimepoint
    lastSpectrumTimepoint = timepoint
    if emissionDataFile:
        new_line = f"{timepoint:.2f},{value:.3f}\n" # add the timepoint and value aligned to headers created in emissionDataFileCreate()
        emissionDataFile.write(new_line)
        return True
    return False

def emissionDataFileClose() -> str | None:
    global emissionDataFile
    if emissionDataFile:
        file_path = emissionDataFile.name
        emissionDataFile.close()
        emissionDataFile = None
        return file_path
    return None

##### functions dealing with Stern-Volmer data results file
def rewriteSVdataFile() -> str | None:
    file_path = SVresultsFileCreate()
    if file_path:
        SVresultsFileWriteStepsData(experimentStepsResult)
        SVresultsFileWriteSVData(experimentSVdataResult)
        file_path = SVresultsFileClose()
    return file_path

def SVresultsFileCreate() -> str | None:
    global SVresultsFile, experimentData, experimentFileName
    now = datetime.now()
    file_path = cfg.RESULTS_DIR / (now.strftime("%Y-%m-%d_%H-%M-%S_") + experimentFileName + "_SVdata.csv")
    SVresultsFile = open(file_path, mode='w', newline='', encoding='utf-8')
    if SVresultsFile:
        line = experimentData["Name"] + "\n"
        SVresultsFile.write(line)  # write experiment name in A1 cell
        line = "time_start [s], time_end [s], N [samples], I(avg.) [a.u.], I(std.dev) [a.u.], I(sem) [a.u.]\n"
        SVresultsFile.write(line)  # write captions for: start time (A2), end time (B2), # of samples (C2), average intensity (D2) with standard deviation (E2) and standard error of mean (F2)
        return file_path
    return None  # could not open SVresultsDataFile

def SVresultsFileWriteStepsData(steps_data: Dict[int, StepData]) -> bool:
    global SVresultsFile, experimentStepsResult
    if SVresultsFile:
        if len(experimentStepsResult) > 0:
            for step in steps_data.values():
                new_line = f"{step.step_t_min:.2f},{step.step_t_max:.2f},{step.value_count},{step.value_average:.3f},{step.value_stddev:.3f},{step.value_sem:.3f}\n" # add step data to the file
                SVresultsFile.write(new_line)
        return True
    return False

def SVresultsFileWriteSVData(SVdata: List[SternVolmerData]) -> bool:
    # TODO: this is still buggy - exceptions when call post-run, fix it!
    global SVresultsFile, experimentSVdataResult
    if SVresultsFile:
        if len(experimentSVdataResult) > 0:
            new_line = "\n"+experimentData["Name"] + " Stern-Volmer results data:\n"
            SVresultsFile.write(new_line)  # write caption for Stern-Volmer results
            # UPDATE! save in mol/L data for Ksv extraction 
            new_line = "[Quencher] [mol/L], I0/I [a.u.], standard error [a.u.]\n"
            SVresultsFile.write(new_line)  # write headers for Stern-Volmer results
            for SVentry in SVdata:
                new_line = f"{SVentry.conc_quencher_M:.6f},{SVentry.ratio_I0_I:.2f},{SVentry.ser_I0_I:.6f}\n" # add Stern-Volmer data for plotting to the file
                SVresultsFile.write(new_line)
        return True
    return False

def SVresultsFileClose() -> str | None:
    global SVresultsFile
    if SVresultsFile:
        file_path = SVresultsFile.name
        SVresultsFile.close()
        SVresultsFile = None
        if len(experimentStepsResult) == 0:
            os.remove(file_path) # delete the file if it does not contain any steps data
            return ""
        return file_path
    return None


if __name__ == "__main__":

    ### test an experiment file
    cfg.SYRINGES_CSV_FILE = "C:/python/SV/Rsc/syringes.csv"
    LoadSyringesCSV()
    print(json.dumps(syringesData, indent=3))
    file_path_test = "C:/python/SV/data/experiment2.csv"
    result = parseExperimentCSV(file_path_test)
    if result != "":
        print("parseExperimentCSV() error: ", result)
    print(json.dumps(experimentData, indent=3))
    print(f"pump program: {experimentPumpProgram}")
    print(f"experiment total time: {experimentProgramTotalTime} s, max flow: {experimentProgramMaxFlow}")
    print(f"syringe diameters: {syringeDiameters}")

    ### test the syringes.csv file
    # cfg.SYRINGES_CSV_FILE = "C:/python/SV/Rsc/syringes.csv"
    # result = LoadSyringesCSV()
    # print(result)
    # print(json.dumps(syringesData, indent=3))
    # print(GetDefaultSyringeSettings(20))
