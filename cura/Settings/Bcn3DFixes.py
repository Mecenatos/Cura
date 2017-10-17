import re

from cura.Settings import GCodeUtils

from UM.Application import Application
from UM.Job import Job
from UM.Logger import Logger

from cura.Settings.ExtruderManager import ExtruderManager


class Bcn3DFixes(Job):
    def __init__(self, container, gcode_list):
        self._container = container
        self._gcode_list = gcode_list
        
        extruder_left = ExtruderManager.getInstance().getExtruderStack(0)
        extruder_right = ExtruderManager.getInstance().getExtruderStack(1)
        active_extruder = ExtruderManager.getInstance().getActiveExtruderStack()

        self._activeExtruders = active_extruder.getProperty("active_extruders", "value")
        self._fixToolChangeZHop = active_extruder.getProperty("fix_tool_change_retraction_hop", "value")
        self._fixFirstRetract = active_extruder.getProperty("fix_first_retract", "value")
        self._fixTemperatureOscilation = active_extruder.getProperty("fix_temperature_oscilation", "value")
        self._zHopDistance = active_extruder.getProperty("retraction_hop_height_after_extruder_switch", "value")
        self._smartPurge = active_extruder.getProperty("smart_purge", "value")
        self._minimumExtrusion = [extruder_left.getProperty("minimum_extrusion", "value"),
                                  extruder_right.getProperty("minimum_extrusion", "value")]
        self._purgeLength = [extruder_left.getProperty("purge_length", "value"),
                             extruder_right.getProperty("purge_length", "value")]
        self._retractReduction = active_extruder.getProperty("retract_reduction", "value")

        self._avoidGrindingFilament = active_extruder.getProperty("avoid_grinding_filament", "value")
        self._maxRetracts = [extruder_left.getProperty("max_retract", "value"),
                             extruder_right.getProperty("max_retract", "value")]

        self._startGcodeInfo = [";BCN3D Fixes applied"]

        self._message = None
        self.progress.connect(self._onProgress)
        self.finished.connect(self._onFinished)

    def run(self):
        Job.yieldThread()
        # Do not change actions order as some may alter others
        if self._activeExtruders or self._fixTemperatureOscilation or self._fixFirstRetract:
            self._both_extruders = False
            scanning = False
            printing = False
            self._idle_extruder = "T1"
            for layer in self._gcode_list:
                lines = layer.split("\n")
                for line in lines:
                    if scanning:
                        if line.startswith("T0") or (line.startswith("T1") and printing):
                            self._both_extruders = True
                            break
                        elif line.startswith("T1") and not printing:
                            self._idle_extruder = "T0"
                        elif GCodeUtils.charsInLine("GXYE", line):
                            printing = True
                    else:
                        if line.startswith(";LAYER_COUNT:"):
                            scanning = True
                if self._both_extruders:
                    break
            Logger.log("d", "gcode scanned")

        self._handleActiveExtruders()
        self._handleFixToolChangeZHop()
        self._handleFixFirstRetract()
        self._handleSmartPurge()
        self._handleFixTemperatureOscilation()
        self._handleRetractReduction()
        self._handleAvoidGrindingFilament()

        written_info = False
        # Write Sigma Vitamins info
        for index, layer in enumerate(self._gcode_list):
            lines = layer.split("\n")
            for temp_index in range(len(lines)):
                if layer.startswith(";Generated with Cura_SteamEngine ") and lines[temp_index].startswith(";Sigma ProGen"):
                    lines[temp_index] = lines[temp_index] + "\n" + "\n".join(self._startGcodeInfo)
                    written_info = True
            layer = "\n".join(lines)
            self._gcode_list[index] = layer
            if written_info:
                break

        self._gcode_list[0] += ";BCN3D_FIXES\n"
        scene = Application.getInstance().getController().getScene()
        setattr(scene, "gcode_list", self._gcode_list)
        self.setResult(self._gcode_list)
        # return self._gcode_list

    def _handleActiveExtruders(self):
        if self._activeExtruders and not self._both_extruders:
            self._startGcodeInfo.append("; - Heat only essentials")
            startGcodeCorrected = False
            for index, layer in enumerate(self._gcode_list):
                lines = layer.split("\n")
                temp_index = 0
                while temp_index < len(lines):
                    line = lines[temp_index]
                    if not startGcodeCorrected:
                        try:
                            if line.startswith("M108 P1"):
                                del lines[temp_index]
                                temp_index -= 1
                            line1 = lines[temp_index + 1]
                            line2 = lines[temp_index + 2]
                            line3 = lines[temp_index + 3]
                            line4 = lines[temp_index + 4]
                            line5 = lines[temp_index + 5]
                            if line.startswith(self._idle_extruder) and line1.startswith("G92 E0") and line2.startswith("G1 E") and line3.startswith("G92 E0") and line4.startswith("G4 P2000") and line5.startswith("G1 F2400 E-8"):
                                del lines[temp_index]
                                del lines[temp_index]
                                del lines[temp_index]
                                del lines[temp_index]
                                del lines[temp_index]
                                del lines[temp_index]
                                startGcodeCorrected = True
                                break
                        except:
                            pass
                    if self._idle_extruder != "T0":
                        if "T1" in line:
                            del lines[temp_index]
                            temp_index -= 1
                    elif self._idle_extruder != "T1":
                        if (line.startswith("M104 S") or line.startswith("M109 S")) and "T1" not in line:
                            del lines[temp_index]
                            temp_index -= 1
                    temp_index += 1
                layer = "\n".join(lines)
                self._gcode_list[index] = layer
            Logger.log("d", "active_extruders applied")
    
    def _handleFixToolChangeZHop(self):
        if self._fixToolChangeZHop and self._both_extruders:
            self._startGcodeInfo.append("; - Fix Tool Change Z Hop")
            # Fix hop
            for index, layer in enumerate(self._gcode_list):
                # Fix strange travel to X105 Y297
                regex = r"\n.*X" + str(int(self._container.getProperty("layer_start_x", "value"))) + " Y" + str(int(self._container.getProperty("layer_start_y", "value"))) + ".*"
                layer = re.sub(regex, "", layer)
                self._gcode_list[index] = layer

                lines = layer.split("\n")
                temp_index = 0
                while temp_index < len(lines):
                    try:
                        line = lines[temp_index]
                        if GCodeUtils.charsInLine(["G0", "X", "Y", "Z"], line):
                            zValue = GCodeUtils.getValue(line, "Z")
                        line1 = lines[temp_index + 1]
                        line2 = lines[temp_index + 2]
                        line3 = lines[temp_index + 3]
                        line4 = lines[temp_index + 4]
                        if (line == "T0" or line == "T1") and line1 == "G92 E0" and line2 == "G91" and "G1 F" in line3 and line4 == "G90":
                            lines[temp_index + 3] = line3.split("Z")[0] + "Z" + str(self._zHopDistance)
                            lineCount = 6  # According to extruder_start_gcode in Sigma Extruders definitions
                            while not lines[temp_index + lineCount].startswith(";TYPE"):
                                line = lines[temp_index + lineCount]
                                if line.startswith("G"):
                                    if lines[temp_index + lineCount + 1].startswith("G"):
                                        del lines[temp_index + lineCount]
                                        lineCount -= 1
                                    else:
                                        xValue = GCodeUtils.getValue(line, "X")
                                        yValue = GCodeUtils.getValue(line, "Y")
                                        lines[temp_index + lineCount] = "G0 F12000 X" + str(xValue) + " Y" + str(yValue) + "\nG0 Z" + str(zValue)
                                lineCount += 1
                            break
                        temp_index += 1
                    except:
                        break
                layer = "\n".join(lines)
                self._gcode_list[index] = layer
            Logger.log("d", "fix_tool_change_z_hop applied")
                
    def _handleFixFirstRetract(self):
        if self._fixFirstRetract:
            self._startGcodeInfo.append("; - Fix First Extrusion")
            startGcodeCorrected = False
            eValue = 0
            fixExtruder = "T0"
            for index, layer in enumerate(self._gcode_list):
                lines = layer.split("\n")
                temp_index = 0
                while temp_index < len(lines):
                    try:
                        line = lines[temp_index]
                        # Get retract value before starting the first layer
                        if not layer.startswith(";LAYER") and line.startswith("T1"):
                            lineCount = 0
                            while not lineCount > len(lines) - temp_index or lines[temp_index + lineCount].startswith("T0"):
                                line = lines[temp_index + lineCount]
                                if GCodeUtils.charsInLine(["G", "F", "E-"], line):
                                    eValue = GCodeUtils.getValue(line, "E")
                                lineCount += 1
                        # Fix the thing
                        elif layer.startswith(";LAYER:"):
                            line1 = lines[temp_index + 1]
                            line2 = lines[temp_index + 2]
                            line3 = lines[temp_index + 3]
                            line4 = lines[temp_index + 4]
                            line5 = lines[temp_index + 5]
                            # detect first tool printing and remove unintentional retract before T1
                            if temp_index == 0 and GCodeUtils.charsInLine(["G1 F", "E"], line1) and line2 == "G92 E0" and line4 == "T1" and line5 == "G92 E0":
                                del lines[temp_index + 1]
                                del lines[temp_index + 1]
                                temp_index -= 1
                                fixExtruder = "T1"
                            # Add proper prime command to T1
                            elif fixExtruder == "T0":
                                lineCount = 0
                                while not lines[temp_index + lineCount].startswith(";TYPE"):
                                    line = lines[temp_index + lineCount]
                                    if GCodeUtils.charsInLine(["G0", "F", "X", "Y"], line):
                                        primeCommandLine = "G1 F2400 E0\nG92 E0 ; T0fix"
                                        lines[temp_index + lineCount + 1] = lines[temp_index + lineCount + 1] + "\n" + primeCommandLine + "\n"
                                        if self._both_extruders:
                                            fixExtruder = "T1"
                                        else:
                                            fixExtruder = "none"
                                        break
                                    lineCount += 1
                                temp_index += lineCount
                            elif fixExtruder == "T1" and line == "T1" and line1 == "G92 E0" and line2 == "G91" and "G1 F" in line3 and line4 == "G90":
                                lineCount = 6  # According to extruder_start_gcode in Sigma Extruders definitions
                                while not lines[temp_index + lineCount].startswith(";TYPE"):
                                    line = lines[temp_index + lineCount]
                                    if GCodeUtils.charsInLine(["G0", "F", "X", "Y"], line):
                                        if GCodeUtils.charsInLine(["G1 F", " E"], lines[temp_index + lineCount + 1]):
                                            del lines[temp_index + lineCount + 1]
                                        primeCommandLine = "G1 F2400 E" + str(abs(eValue)) + "\nG92 E0 ; T1fix"
                                        lines[temp_index + lineCount + 1] = lines[temp_index + lineCount + 1] + "\n" + primeCommandLine + "\n"
                                        break
                                    lineCount += 1
                            startGcodeCorrected = True
                        temp_index += 1
                    except:
                        break
                layer = "\n".join(lines)
                self._gcode_list[index] = layer
                if startGcodeCorrected:
                    break
            Logger.log("d", "fix_retract applied")

    def _handleSmartPurge(self):
        if self._smartPurge and self._both_extruders:
            self._startGcodeInfo.append("; - Smart Purge")
            extraPurges = []
            for index, layer in enumerate(self._gcode_list):
                lines = layer.split("\n")
                temp_index = 0
                while temp_index < len(lines):
                    if not layer.startswith(";LAYER:0") and layer.startswith(";LAYER:") and (
                                lines[temp_index].startswith("T0") or lines[temp_index].startswith("T1")):
                        if lines[temp_index].startswith("T0"):
                            countingForTool = 0
                        elif lines[temp_index].startswith("T1"):
                            countingForTool = 1
                        lineCount = temp_index - 1
                        while lineCount >= 0:
                            line = lines[lineCount]
                            if GCodeUtils.charsInLine("GFE", line) and GCodeUtils.getValue(line, "E") < \
                                    self._minimumExtrusion[
                                        abs(countingForTool - 1)]:
                                extraPurges.append(index - 1)
                                break
                            lineCount -= 1
                        break
                    temp_index += 1
            for index, layer in enumerate(self._gcode_list):
                lines = layer.split("\n")
                applyFix = False
                if len(extraPurges) > 0:
                    if index == extraPurges[0]:
                        temp_index = 0
                        while temp_index < len(lines):
                            if lines[temp_index].startswith("T0") or lines[temp_index].startswith("T1"):
                                applyFix = True
                                if lines[temp_index].startswith("T0"):
                                    countingForTool = 0
                                elif lines[temp_index].startswith("T1"):
                                    countingForTool = 1
                            elif applyFix and lines[temp_index].startswith("M109 S"):
                                lineCount = temp_index
                                while not lines[lineCount].startswith("M104 S"):
                                    lineCount += 1
                                    if GCodeUtils.charsInLine(["G1", "F", "X", "Y", "E"], lines[lineCount]):
                                        lineCount = temp_index
                                        break
                                lines[temp_index] = lines[temp_index] + "\nM104 S" + str(
                                    GCodeUtils.getValue(lines[lineCount], "S")) + "\nG1 F2400 E" + str(
                                    8) + "\nG1 F" + str(GCodeUtils.getPurgeSpeed(lines, temp_index)) + " E" + str(
                                    8 + self._purgeLength[countingForTool]) + "\nG4 P2000\nG1 F2400 E" + str(
                                    self._purgeLength[countingForTool]) + "\nG92 E0"
                                break
                            temp_index += 1
                        del extraPurges[0]
                layer = "\n".join(lines)
                self._gcode_list[index] = layer
            Logger.log("d", "smart_purge applied")

    def _handleFixTemperatureOscilation(self):
        if self._fixTemperatureOscilation and self._both_extruders:
            self._startGcodeInfo.append("; - Fix Temperature Oscilation")
            # Scan all temperatures
            temperatures = []  # [(layerIndex, lineIndex, action, line)]
            for index, layer in enumerate(self._gcode_list):
                lines = layer.split("\n")
                temp_index = 0
                while temp_index < len(lines):
                    line = lines[temp_index]
                    if layer.startswith(";LAYER:"):
                        if line.startswith("M109"):
                            temperatures.append([index, temp_index, "heat", line])
                        elif line.startswith("T"):
                            temperatures.append([index, temp_index, "toolChange", line])
                        elif line.startswith("M104"):
                            temperatures.append([index, temp_index, "unknown", line])
                    temp_index += 1
            # Define "unknown" roles
            for elementIndex in range(len(temperatures)):
                action = temperatures[elementIndex][2]
                if action == "unknown":
                    if temperatures[elementIndex][3].startswith("M104 T"):
                        temp_index = elementIndex - 1
                        while temp_index >= 0:
                            if temperatures[temp_index][3].startswith("T"):
                                action = "coolDownIdle"
                                break
                            elif temperatures[temp_index][3].startswith("M104 T"):
                                action = "preheat"
                                break
                            temp_index -= 1
                    elif temperatures[elementIndex][3].startswith("M104 S"):
                        if elementIndex + 1 < len(temperatures):
                            if temperatures[elementIndex + 1][3].startswith("T"):
                                action = "coolDownActive"
                            else:
                                action = "setpoint"
                    temperatures[elementIndex][2] = action
            # Correct all temperatures
            for elementIndex in range(len(temperatures)):
                action = temperatures[elementIndex][2]
                temperature_inertia_initial_fix = self._container.getProperty("material_initial_print_temperature", "value") - self._container.getProperty("material_print_temperature", "value")
                temperature_inertia_final_fix = self._container.getProperty("material_final_print_temperature", "value") - self._container.getProperty("material_print_temperature", "value")
                if action == "preheat":
                    temp_index = elementIndex + 1
                    while temp_index < len(temperatures):
                        if temperatures[temp_index][2] == "preheat":
                            break
                        elif temperatures[temp_index][2] == "setpoint":
                            correctTemperatureValue = GCodeUtils.getValue(temperatures[temp_index][3], "S") + temperature_inertia_initial_fix
                            temperatures[elementIndex][3] = temperatures[elementIndex][3].split("S")[0] + "S" + str(correctTemperatureValue)
                            break
                        temp_index += 1
                elif action == "heat":
                    temp_index = elementIndex - 1
                    while temp_index >= 0:
                        if temperatures[temp_index][2] == "preheat":
                            correctTemperatureValue = GCodeUtils.getValue(temperatures[temp_index][3], "S")
                            temperatures[elementIndex][3] = temperatures[elementIndex][3].split("S")[0] + "S" + str(correctTemperatureValue)
                            break
                        temp_index -= 1
                elif action == "coolDownIdle":
                    correctTemperatureValue = max(
                        GCodeUtils.getValue(temperatures[elementIndex][3], "S") + temperature_inertia_initial_fix,
                        self._container.getProperty("material_standby_temperature", "value"))
                    temperatures[elementIndex][3] = temperatures[elementIndex][3].split("S")[0] + "S" + str(correctTemperatureValue)
                elif action == "coolDownActive":
                    temp_index = elementIndex - 1
                    while temp_index >= 0:
                        if temperatures[temp_index][2] == "coolDownActive":
                            break
                        if temperatures[temp_index][2] == "setpoint":
                            correctTemperatureValue = GCodeUtils.getValue(temperatures[temp_index][3], "S") + temperature_inertia_final_fix
                            temperatures[elementIndex][3] = temperatures[elementIndex][3].split("S")[0] + "S" + str(correctTemperatureValue)
                            break
                        temp_index -= 1
            # Set back new corrected temperatures
            for index, layer in enumerate(self._gcode_list):
                lines = layer.split("\n")
                temp_index = 0
                while temp_index < len(lines) and len(temperatures) > 0:
                    if index == temperatures[0][0] and temp_index == temperatures[0][1]:
                        lines[temp_index] = temperatures[0][3]
                        del temperatures[0]
                    temp_index += 1
                layer = "\n".join(lines)
                self._gcode_list[index] = layer
            Logger.log("d", "fix_temperature_oscilation applied")
                
    def _handleRetractReduction(self):
        if self._retractReduction:
            self._startGcodeInfo.append("; - Reduce Retraction")
            removeRetracts = False
            for index, layer in enumerate(self._gcode_list):
                lines = layer.split("\n")
                temp_index = 0
                if layer.startswith(";LAYER:") and not layer.startswith(";LAYER:0"):
                    while temp_index < len(lines):
                        line = lines[temp_index]
                        if line.startswith(";TYPE:WALL-OUTER") or line.startswith(";TYPE:SKIN") or line.startswith("T"):
                            removeRetracts = False
                        elif line.startswith(";TYPE:"):
                            removeRetracts = True
                        if removeRetracts:
                            if " E" in line and "G92" not in line:
                                eValue = GCodeUtils.getValue(line, "E")
                                lineCount = temp_index - 1
                                try:
                                    if not lines[temp_index + 1].startswith("G92"):
                                        while lineCount >= 0:
                                            line = lines[lineCount]
                                            if " E" in line and "G92" not in line:
                                                if eValue < GCodeUtils.getValue(line, "E"):
                                                    if removeRetracts:
                                                        del lines[temp_index]
                                                        temp_index -= 1
                                                break
                                            lineCount -= 1
                                except:
                                    break
                        temp_index += 1
                layer = "\n".join(lines)
                self._gcode_list[index] = layer
            Logger.log("d", "retract_reduction applied")
                
    def _handleAvoidGrindingFilament(self):
        if self._avoidGrindingFilament:
            self._startGcodeInfo.append("; - Prevent Filament Grinding")
            retractionsPerExtruder = [[], []]
            countingForTool = 0
            for index, layer in enumerate(self._gcode_list):
                lines = layer.split("\n")
                temp_index = 0
                if layer.startswith(";LAYER:"):
                    while temp_index < len(lines):
                        line = lines[temp_index]
                        if line.startswith("T0"):
                            countingForTool = 0
                        elif line.startswith("T1"):
                            countingForTool = 1
                        elif " E" in line and "G92" not in line:
                            eValue = GCodeUtils.getValue(line, "E")
                            lineCount = temp_index - 1
                            try:
                                if not lines[temp_index + 1].startswith("G92"):
                                    while lineCount >= 0:
                                        line = lines[lineCount]
                                        if " E" in line and "G92" not in line:
                                            if eValue < GCodeUtils.getValue(line, "E"):
                                                purgeLength = round(GCodeUtils.getValue(line, "E") - eValue, 5)
                                                retractionsPerExtruder[countingForTool].append(eValue)
                                                if len(retractionsPerExtruder[countingForTool]) > self._maxRetracts[
                                                    countingForTool]:
                                                    if (retractionsPerExtruder[countingForTool][-1] - retractionsPerExtruder[countingForTool][0]) < purgeLength:
                                                        # Delete extra travels
                                                        lineCount2 = temp_index + 1
                                                        while lines[lineCount2].startswith("G0"):
                                                            if lines[lineCount2 + 1].startswith("G0"):
                                                                del lines[lineCount2]
                                                            else:
                                                                lineCount2 += 1
                                                        # Add purge commands
                                                        #todo remove when firmware updated
                                                        if Application.getInstance().getMachineManager().activeMachineId == "Sigma":
                                                            lines[temp_index] = lines[temp_index] + " ;prevent filament grinding on T" + \
                                                                                str(countingForTool) + "\nT" + \
                                                                                str(abs(countingForTool - 1)) + "\nT" + \
                                                                                str(countingForTool) + "\nG91\nG1 F12000 Z2\nG90\nG1 F2400 E" + \
                                                                                str(round(eValue + purgeLength, 5)) + "\nG1 F" + \
                                                                                str(GCodeUtils.getPurgeSpeed(lines, temp_index)) + " E" + \
                                                                                str(round(eValue + 2 * purgeLength, 5)) + "\nG4 P2000\nG1 F2400 E" + \
                                                                                str(round(eValue + purgeLength, 5)) + "\nG92 E" + \
                                                                                str(eValue) + "\nG0 F12000\n" + lines[temp_index + 1] + "\nG91\nG1 F12000 Z-2\nG90 ;end of the filament grinding prevention protocol"
                                                        else:
                                                            count_back = 1
                                                            while not GCodeUtils.charsInLine("GXY", lines[temp_index - count_back]):
                                                                count_back += 1
                                                            xPosition = GCodeUtils.getValue(lines[temp_index - count_back], "X")
                                                            yPosition = GCodeUtils.getValue(lines[temp_index - count_back], "Y")
                                                            lines[temp_index] = lines[temp_index] + " ;prevent filament grinding on T" + \
                                                                                str(countingForTool) + "\nG71\nG91\nG1 F12000 Z5\nG90\nG1 F2400 E" + \
                                                                                str(round(eValue + purgeLength, 5)) + "\nG1 F" + \
                                                                                str(GCodeUtils.getPurgeSpeed(lines, temp_index)) + " E" + \
                                                                                str(round(eValue + 2 * purgeLength,5)) + "\nG4 P2000\nG1 F2400 E" + \
                                                                                str(round(eValue + purgeLength, 5)) + "\nG92 E" + \
                                                                                str(eValue) + "\nG1 F12000 X"+str(xPosition)+" Y"+str(yPosition)+"\nG91\nG1 F12000 Z-5\nG90 ;end of the filament grinding prevention protocol"
                                                        del lines[temp_index + 1]
                                                        temp_index -= 1
                                                        retractionsPerExtruder[countingForTool] = []
                                                    else:
                                                        del retractionsPerExtruder[countingForTool][0]
                                            break
                                        elif line.startswith("T") or line.startswith("G92"):
                                            break
                                        lineCount -= 1
                            except:
                                break
                        temp_index += 1
                layer = "\n".join(lines)
                self._gcode_list[index] = layer
            Logger.log("d", "avoid_grinding_filament applied")

    def setMessage(self, message):
        self._message = message

    def _onFinished(self, job):
        if self == job and self._message is not None:
            self._message.hide()
            self._message = None

    def _onProgress(self, job, amount):
        if self == job and self._message:
            self._message.setProgress(amount)