#include "pump.h"
#include <QDebug> // Using QDebug for internal Pump logs
#include <QTimer> // Include QTimer implementation
#include <stdexcept> // For potential errors, though simpler error handling is used in protocol

Pump::Pump(QObject *parent)
    : QObject(parent)
    , m_currentStatus("00S") // Initial status as per * RESET command
    , m_syringeDiameter(0.0)
    , m_pumpingRate(0.0)
    , m_dispensedVolume(0.0)
    , m_volumeUnit("UL")
    , m_pumpDirectionWithdraw(false) // false for Infuse initially
//    , m_actualVolume(0.0) // Initialize actual volume
    , m_volumeSet(false)
    , m_updateTimer(new QTimer(this)) // Initialize the update timer

{
    qDebug() << "Pump object created. Initial Status:" << m_currentStatus;
    // Connect the update timer's timeout signal to the slot that handles periodic updates
    connect(m_updateTimer, &QTimer::timeout, this, &Pump::on_updateTimer_timeout);
}

Pump::~Pump()
{
    qDebug() << "Pump object destroyed.";
    // The timer will be deleted automatically because it has 'this' as parent
    m_updateTimer->stop(); // Stop the timer if it's running before deletion
}

QString Pump::processCommand(const QString &command)
{
    QString trimmedCommand = command.trimmed();
    qDebug() << "Pump received command:" << trimmedCommand;

    // Handle empty command (polling) - will not work this way unless logic in MainWidget::handleTimeout() is changed
    //if (trimmedCommand.isEmpty()) {
    //    return processEmpty();
    //}

    QStringList parts = trimmedCommand.split(" ", Qt::SkipEmptyParts);
    if (parts.isEmpty()) {
        // Should not happen if trimmedCommand is not empty, but for safety
        return m_currentStatus + "?"; // Or a specific error for malformed command
    }

    QString baseCommand = parts.first().toUpper(); // Get the base command (e.g., "DIA", "RAT")
    QStringList params = parts.mid(1); // Get the rest as parameters

    if (trimmedCommand == "* RESET") { // Special case for exact match including asterisk
        return processReset();
    } else if (baseCommand == "DIA") {
        return processDia(params);
    } else if (baseCommand == "RAT") {
        return processRat(params);
    } else if (baseCommand == "VOL") {
        return processVol(params);
    } else if (baseCommand == "DIR") {
        return processDir(params);
    } else if (baseCommand == "RUN" && params.isEmpty()) { // RUN has no parameters
        return processRun();
    } else if (baseCommand == "STP" && params.isEmpty()) { // STP has no parameters
        return processStp();
    } else if (baseCommand == "VER" && params.isEmpty()) { // VER has no parameters
        return processVer();
    } else if (baseCommand == "FAIL" && params.isEmpty()) { // FAIL: virtual command (does not exist on NE-1000)
        return processFail();
    } else if (baseCommand == "(POLL)" && params.isEmpty()) { // (POLL): virtual command (does not exist on NE-1000, was injected artificially when empty command was received)
        return processPolling();
    } else {
        // Command not recognized
        qDebug() << "Unknown command:" << trimmedCommand;
        return m_currentStatus + "?";
    }
}

QString Pump::processReset()
{
    // Stop the update timer if it's running
    if (m_updateTimer->isActive()) {
        m_updateTimer->stop();
    }
    m_currentStatus = "00S";
    m_syringeDiameter = 0.0;
    m_pumpingRate = 0.0;
    m_dispensedVolume = 0.0;
    m_volumeUnit = "UL";
    m_pumpDirectionWithdraw = false; // Infuse
    m_volumeSet = false;
//    m_actualVolume = 0.0; // Zero actual volume on reset
    // Emit initial values so connected slots in the GUI can update immediately on startup
    emit diameterChanged(m_syringeDiameter);
    emit rateChanged(m_pumpingRate);
    QString volume_label = QString("%1 %2").arg(m_dispensedVolume, 0, 'f', 2).arg(m_volumeUnit == "ML" ? "mL" : "uL");
    emit volumeChanged(volume_label);
    // emit statusChanged(m_currentStatus); // Could emit status initially too if needed by GUI
    qDebug() << "Command * RESET processed. Status:" << m_currentStatus;
    // Emit status changed signal
    emit statusChanged(m_currentStatus);
    return m_currentStatus; // Returns "00S"
}

QString Pump::processPolling()
{
    qDebug() << "Polling processed. Status:" << m_currentStatus;
    return m_currentStatus;
}

QString Pump::processDia(const QStringList &params)
{
    if (params.isEmpty()) {
        // DIA (Query)
        QString response = QString("%1%2MM").arg(m_currentStatus).arg(m_syringeDiameter, 0, 'f', 2); // Format float with 2 decimal places
        qDebug() << "Command DIA (Query) processed. Response:" << response;
        return response;
    } else if (params.size() == 1) {
        // DIA <float> (Set)
        if (m_currentStatus != "00I" && m_currentStatus != "00W") { 
            double diameter;
            if (parseFloatParam(params, 0, diameter)) {
                m_syringeDiameter = diameter;
                emit diameterChanged(m_syringeDiameter);
				if (m_currentStatus == "00P") { // pump stops if diameter set in paused state
                    m_currentStatus = "00S";
					emit statusChanged(m_currentStatus);
				}
				else if (m_currentStatus == "00A") { // pump paused if diameter set in error state
                    m_currentStatus = "00P";
					emit statusChanged(m_currentStatus);
				}
                qDebug() << "Command DIA <float> processed. Set diameter to:" << m_syringeDiameter << ". Status:" << m_currentStatus;
                return m_currentStatus; // Returns "00S"
            } else {
                // Parameter is not a valid float
                qDebug() << "Command DIA <float> received invalid float parameter:" << params.first();
                return m_currentStatus + "?"; // Protocol specifies ?NA for invalid parameters in this case
            }
        } else {
            // Status is 00I or 00W
            qDebug() << "Command DIA <float> received in status" << m_currentStatus << ". Expected 00S/00P/00A.";
            return m_currentStatus + "?NA";
        }
    } else {
        // Invalid number of parameters for DIA
        qDebug() << "Command DIA received invalid number of parameters:" << params.size();
        return m_currentStatus + "?"; // Protocol doesn't specify, returning "?"
    }
}

// Helper method: Checks if the provided rate is within the valid limit based on the current syringe diameter.
// Formula: rate <= pi * (diameter)^2 / 80
bool Pump::isRateValid(double rate) const
{
    if (rate < 0) return false; // check to ignore negative rates
    double maxRate = M_PI * pow(m_syringeDiameter, 2) / 80.0;
    return rate <= maxRate; // Use <= for the check
}


QString Pump::processRat(const QStringList &params)
{
    // Command 3: RAT

    if (params.isEmpty()) {
        // RAT (Query) - Responds with "00x<float>MM"
        QString response = QString("%1%2MM").arg(m_currentStatus).arg(m_pumpingRate, 0, 'f', 3); // Format float with 3 decimal places
        qDebug() << "Command RAT (Query) processed in status" << m_currentStatus << ". Response:" << response;
        return response;
    } else if (params.size() == 1) {
        // Could be RAT <float>MM where the unit is part of the parameter string
        QString param = params.first();
        // Check if the single parameter ends with "MM" (case-insensitive)
        if (param.toUpper().endsWith("MM")) { // only working with mL/min rate
            // Extract the substring before "MM" as the potential float value
            QString floatString = param.left(param.length() - 2);
            double rate;
            bool ok;
            rate = floatString.toDouble(&ok); // Try to parse the extracted part as double

            if (ok) {
                // It's RAT <float>MM and the float part is valid
                if (m_currentStatus != "00I" && m_currentStatus != "00W") {
                    // Can only set rate if pump is not running
                    //Rate validation check first
                    if (!isRateValid(rate)) {
                        qDebug() << "Command RAT <float>MM received rate out of range:" << rate << " for diameter:" << m_syringeDiameter;
                        return m_currentStatus + "?OOR"; // Return Status + ?OOR if rate is out of range
                    }
                    m_pumpingRate = rate; // Accept the rate
                    emit rateChanged(m_pumpingRate);
                    if (rate == 0.0) { // pump stops if rate is set to zero value
                        m_currentStatus = "00S";
                        emit statusChanged(m_currentStatus);
                    }
                    else if (m_currentStatus == "00P") { // pump stops if rate set in paused state
                        m_currentStatus = "00S";
						emit statusChanged(m_currentStatus);
					}
                    else if (m_currentStatus == "00A") { // pump paused if rate set in error state
                        m_currentStatus = "00P";
						emit statusChanged(m_currentStatus);
					}
                    qDebug() << "Command RAT <float>MM processed (unit attached). Set rate to:" << m_pumpingRate << ". Status:" << m_currentStatus;
                    return m_currentStatus; // Returns "00S" as per protocol for successful set in 00S
                } else {
                    // Status is not 00S, cannot set rate
                    qDebug() << "Command RAT <float>MM (unit attached) received in status" << m_currentStatus << ". Expected Expected 00S/00P/00A.";
                    return m_currentStatus + "?NA"; // Cannot set in current status
                }
            } else {
                // Parameter ends with MM but the part before is not a valid float
                qDebug() << "Command RAT <float>MM (unit attached) received invalid float part:" << floatString;
                return m_currentStatus + "?"; // Protocol specifies ? for invalid parameters
            }
        } else {
            // Single parameter format but doesn't end with MM - invalid format for RAT set commands
            qDebug() << "Command RAT received invalid single parameter format (doesn't end with MM):" << param;
            return m_currentStatus + "?"; 
        }
    } else if (params.size() == 2) {
        // Must be RAT C <float> based on defined formats
        if (params.at(0).toUpper() == "C") {
            double rate;
            // Use parseFloatParam helper to parse the float parameter at index 1
            if (parseFloatParam(params, 1, rate)) {
                // Set pumpingRate regardless of status for RAT C <float>

                // Rate validation check first
                if (!isRateValid(rate)) {
                    qDebug() << "Command RAT C <float> received rate out of range:" << rate << " for diameter:" << m_syringeDiameter;
                    return m_currentStatus + "?OOR"; // Return Status + ?OOR if rate is out of range
                }

                m_pumpingRate = rate; // Accept the rate
                emit rateChanged(m_pumpingRate);
                if (rate == 0.0) { // pump stops if rate is set to zero value
                    m_currentStatus = "00S";
                    emit statusChanged(m_currentStatus);
                }
                else if (m_currentStatus == "00A") { // pump paused if rate set in error state
                    m_currentStatus = "00P";
					emit statusChanged(m_currentStatus);
				}
                qDebug() << "Command RAT C <float> processed. Set rate to:" << m_pumpingRate << ". Status:" << m_currentStatus;
                // Response is current status regardless of status before set or parameter validity for RAT C
                return m_currentStatus;
            } else {
                // Invalid float parameter for RAT C <float>
                qDebug() << "Command RAT C <float> received invalid float parameter:" << params.at(1);
                // Return ? for an invalid float parameter
                return m_currentStatus + "?";
            }
        } else {
            // Two parameters, but the first is not "C" - invalid format for RAT set commands
            qDebug() << "Command RAT received invalid two parameter format (first not C):" << params;
            return m_currentStatus + "?";
        }
    } else {
        // Invalid number of parameters (size > 2) for RAT command
        qDebug() << "Command RAT received invalid number of parameters:" << params.size();
        return m_currentStatus + "?"; // Protocol doesn't specify exact error, using "?" (may be "?OOR" for space-separated numbers)
    }
}

QString Pump::processVol(const QStringList &params)
{
    if (params.isEmpty()) {
        // VOL (Query)
        QString response = QString("%1%2%3").arg(m_currentStatus).arg(m_dispensedVolume, 0, 'f', 2).arg(m_volumeUnit); // Format float with 2 decimal places
        qDebug() << "Command VOL (Query) processed. Response:" << response;
        return response;
    } else if (params.size() == 1) {
        // VOL <float> (Set Volume) or VOL <unit_str> (Set Unit)
        if (m_currentStatus != "00I" && m_currentStatus != "00W") {
            bool isFloat;
            double volume = params.first().toDouble(&isFloat); // Try parsing as float

            if (isFloat) {
                // It's a float parameter, Set Volume
                m_dispensedVolume = volume;
                m_volumeSet = (m_dispensedVolume > 0);
                QString volume_label = QString("%1 %2").arg(m_dispensedVolume, 0, 'f', 2).arg(m_volumeUnit == "ML" ? "mL" : "uL");
                emit volumeChanged(volume_label);
				if (m_currentStatus == "00P") { // pump stops if volume set in paused state
                    m_currentStatus = "00S";
					emit statusChanged(m_currentStatus);
				}
                if (m_currentStatus == "00A") { // pump paused if volume set in error state
                    m_currentStatus = "00P";
					emit statusChanged(m_currentStatus);
				}
                qDebug() << "Command VOL <float> processed. Set volume to:" << m_dispensedVolume << ". Status:" << m_currentStatus;
                return m_currentStatus; // Returns "00S"
            } else {
                // Not a float, assume it's a unit string parameter, Set Unit
                QString unit = params.first().toUpper();
                if (unit == "UL" || unit == "ML") {
                    m_volumeUnit = unit;
                    QString volume_label = QString("%1 %2").arg(m_dispensedVolume, 0, 'f', 2).arg(m_volumeUnit == "ML" ? "mL" : "uL");
                    emit volumeChanged(volume_label);
					if (m_currentStatus == "00P") { // pump stops if volume set in paused state
                        m_currentStatus = "00S";
						emit statusChanged(m_currentStatus);
					}
                    if (m_currentStatus == "00A") { // pump paused if volume set in error state
                        m_currentStatus = "00P";
						emit statusChanged(m_currentStatus);
					}
                    qDebug() << "Command VOL <unit_str> processed. Set unit to:" << m_volumeUnit << ". Status:" << m_currentStatus;
                    return m_currentStatus; // Returns "00S"
                } else {
                    // Invalid unit string
                    qDebug() << "Command VOL <unit_str> received invalid unit:" << params.first();
                    return m_currentStatus + "?";
                }
            }
        } else {
            // Status is not 00S for setting
            qDebug() << "Command VOL received set command in status" << m_currentStatus << ". Expected 00S/00P/00A.";
            return m_currentStatus + "?NA";
        }
    } else {
        // Invalid number of parameters for VOL
        qDebug() << "Command VOL received invalid number of parameters:" << params.size();
        return m_currentStatus + "?"; // Protocol doesn't specify, returning "?"
    }
}

QString Pump::processDir(const QStringList &params)
{
    if (params.size() == 1) {
        QString subCommand = params.first().toUpper();
        if (subCommand == "INF") {
            // DIR INF (Set Infuse)
            if (m_currentStatus == "00S") {
                m_pumpDirectionWithdraw = false;
                qDebug() << "Command DIR INF processed. Direction: Infuse. Status:" << m_currentStatus;
				if (m_currentStatus == "00P") { // pump stops if volume set in paused state
                    m_currentStatus = "00S";
						emit statusChanged(m_currentStatus);
				}
                if (m_currentStatus == "00A") { // pump paused if volume set in error state
                    m_currentStatus = "00P";
					emit statusChanged(m_currentStatus);
				}
                return m_currentStatus + "INF";
            } else {
                qDebug() << "Command DIR INF received in status" << m_currentStatus << ". Expected 00S/00P/00A.";
                return m_currentStatus + "?NA";
            }
        } else if (subCommand == "WDR") {
            // DIR WDR (Set Withdraw)
            if (m_currentStatus == "00S") {
                m_pumpDirectionWithdraw = true;
				if (m_currentStatus == "00P") { // pump stops if volume set in paused state
                    m_currentStatus = "00S";
					emit statusChanged(m_currentStatus);
				}
                if (m_currentStatus == "00A") { // pump paused if volume set in error state
                    m_currentStatus = "00P";
					emit statusChanged(m_currentStatus);
				}
                qDebug() << "Command DIR WDR processed. Direction: Withdraw. Status:" << m_currentStatus;
                return m_currentStatus + "WDR";
            } else {
                qDebug() << "Command DIR WDR received in status" << m_currentStatus << ". Expected 00S/00P/00A.";
                return m_currentStatus + "?NA";
            }
        } else if (subCommand == "REV") {
            // DIR REV (Reverse)
            if (m_currentStatus == "00S") {
                m_pumpDirectionWithdraw = !m_pumpDirectionWithdraw;
				m_pumpDirectionWithdraw = true;
				if (m_currentStatus == "00P") { // pump stops if volume set in paused state
                    m_currentStatus = "00S";
					emit statusChanged(m_currentStatus);
				}
                if (m_currentStatus == "00A") { // pump paused if volume set in error state
                    m_currentStatus = "00P";
					emit statusChanged(m_currentStatus);
				}
                qDebug() << "Command DIR REV processed. Direction toggled. Status:" << m_currentStatus;
                return m_currentStatus + (m_pumpDirectionWithdraw ? "WDR" : "INF");
            } else {
                qDebug() << "Command DIR REV received in status" << m_currentStatus << ". Expected 00S/00P/00A.";
                return m_currentStatus + "?NA";
            }
        } else {
            // DIR <unknown_param> - treat as unknown parameter
            qDebug() << "Command DIR received unknown parameter:" << params.first();
            return m_currentStatus + "?";
        }
    } else if (params.isEmpty()) {
        // DIR (Query)
        qDebug() << "Command DIR (Query) processed. Status:" << m_currentStatus << ". Direction:" << (m_pumpDirectionWithdraw ? "WDR" : "INF");
        return m_currentStatus + (m_pumpDirectionWithdraw ? "WDR" : "INF");
    }
    else {
        // Invalid parameters for DIR
        qDebug() << "Command DIR received invalid parameters:" << params;
        return m_currentStatus + "?";
    }
}

QString Pump::processRun()
{
    // Command 5: RUN

    // Initial check: for simplicity, will not run if unit is "UL" and return Program step error response
    if (m_volumeUnit == "UL") {
        qDebug() << "Command RUN processed. Unit is UL. Cannot run in UL.";
        // Protocol: send response "00A?E" and return immediately. Status changes to Error (00A).
        m_currentStatus = "00A";
        return m_currentStatus + "?E";
    }
    // Check if pumping rate is effectively zero
    if (qFuzzyIsNull(m_pumpingRate)) { // Use qFuzzyIsNull for float comparison with 0.0
        qDebug() << "Command RUN processed. Pumping rate is 0.0. Staying in 00S.";
        return "00S"; // Protocol specifies return "00S" if rate is 0
    } else {
        // Pumping rate > 0
        // When entering running state, initialize actual volume from dispensed volume
//        m_actualVolume = m_dispensedVolume;
//        qDebug() << "Pump::processRun: Initializing m_actualVolume to m_dispensedVolume:" << m_actualVolume;
        if (m_pumpDirectionWithdraw) {
            // Direction is Withdraw (WDR)
            m_currentStatus = "00W";
            qDebug() << "Command RUN processed. Rate > 0, Direction Withdraw. Setting status to 00W.";
            // Emit status changed signal now that pumping status is set
            emit statusChanged(m_currentStatus);
            // Start the update timer for periodic volume changes
            m_updateTimer->start(PUMP_STATE_UPDATE_INTERVAL_S * 1000); // Timer interval is in milliseconds
            qDebug() << "Update timer started with interval:" << m_updateTimer->interval() << " ms";
            return m_currentStatus; // Returns "00W"
        } else {
            // Direction is Infuse (INF)
            m_currentStatus = "00I";
            qDebug() << "Command RUN processed. Rate > 0, Direction Infuse. Setting status to 00I.";
            // Emit status changed signal now that pumping status is set
            emit statusChanged(m_currentStatus);
            // Start the update timer for periodic volume changes
            m_updateTimer->start(PUMP_STATE_UPDATE_INTERVAL_S * 1000); // Timer interval is in milliseconds
            qDebug() << "Update timer started with interval:" << m_updateTimer->interval() << " ms";
            return m_currentStatus; // Returns "00I"
        }
    }
}

QString Pump::processStp()
{
    if (m_currentStatus == "00S") {
        qDebug() << "Command STP processed in status 00S. Returning 00S?NA.";
        return "00S?NA";
    } else if (m_currentStatus == "00P" || m_currentStatus == "00A") {
        // Transition from Paused to Stopped
        // Stop the update timer
        if (m_updateTimer->isActive()) {
            m_updateTimer->stop();
        }
        m_currentStatus = "00S";
        qDebug() << "Command STP processed in status " << m_currentStatus << ". Setting status to 00S.";
        // Emit status changed signal
        emit statusChanged(m_currentStatus);
        return "00S";
    } else if (m_currentStatus == "00I" || m_currentStatus == "00W") {
        m_currentStatus = "00P";
        qDebug() << "Command STP processed in status" << (m_currentStatus == "00I" ? "00I" : "00W") << ". Setting status to 00P.";
        // Emit status changed signal
        emit statusChanged(m_currentStatus);
        return "00P";
    } else {
        // Should not happen with defined states, but defensive programming
        qDebug() << "Command STP processed in unexpected status" << m_currentStatus << ". Returning status?.";
        return m_currentStatus + "?";
    }
}

QString Pump::processVer()
{
    // Always responds with current status + "NE1000VEmulator"
    QString response = m_currentStatus + "NE1000VEmulator";
    qDebug() << "Command VER processed. Response:" << response;
    return response;
}

// Virtual command 8: FAIL
// Stops pumping if running, sets status to 00A, and responds with "00A?E"
QString Pump::processFail()
{
    qDebug() << "Command FAIL processed. Current status:" << m_currentStatus;

    // If the pump is running (status "00I" or "00W"), stop the volume update timer
    if (m_currentStatus == "00I" || m_currentStatus == "00W") {
        if (m_updateTimer->isActive()) {
            m_updateTimer->stop();
            qDebug() << "FAIL command stopped the update timer.";
        }
        // Note: Volume and actual volume are preserved when stopping this way,
        // unless the status transition logic requires zeroing (it doesn't for 00A).
    }
    // For other statuses (like 00P, 00S, 00A, 00E), the timer is already stopped or it doesn't apply.
    // Just proceed to set the status to 00A.


    // Always set the status to 00A regardless of previous status
    m_currentStatus = "00A";
    // Emit status changed signal to update the GUI
    emit statusChanged(m_currentStatus);

    // Always respond with "00A?E"
    QString response = m_currentStatus + "?E";
    qDebug() << "FAIL command response:" << response;
    return response;
}


// Helper function to parse float parameter
bool Pump::parseFloatParam(const QStringList &params, int index, double &value)
{
    if (index < 0 || index >= params.size()) {
        return false;
    }
    bool ok;
    value = params.at(index).toDouble(&ok);
    return ok;
}

// Slot for the update timer timeout
// Handles periodic volume updates and state checks during pumping (00I or 00W states).
void Pump::on_updateTimer_timeout()
{
    // This slot should only be active when the pump is in 00I or 00W states.
    // If it fires in another state, something is wrong, so stop the timer.
    if (m_currentStatus != "00I" && m_currentStatus != "00W") {
        qDebug() << "Update timer timeout in unexpected status:" << m_currentStatus << ". Stopping timer.";
        m_updateTimer->stop();
        // Optionally emit an error status or response if the timer fires in a wrong state
        // m_currentStatus = "00E"; emit statusChanged(m_currentStatus); emit sendResponse("00E?");
        return; // Exit the slot
    }

    // Calculate the volume change since the last tick (in mL)
    // Rate is in mL/min, timer interval is in seconds (PUMP_STATE_UPDATE_INTERVAL_S)
    double volumeChange = (m_pumpingRate / 60.0) * PUMP_STATE_UPDATE_INTERVAL_S;

    // Determine behavior based *only* on the current value of m_actualVolume, as per user's clarification.
    // If m_actualVolume > 0, we are in a 'decreasing' mode (simulating withdraw from a non-empty syringe).
    // If m_actualVolume == 0, we are in an 'increasing' mode (simulating infuse into an empty syringe).

    if (m_volumeSet && (m_dispensedVolume > 0.0)) {
        // Logic for decreasing volume (simulating withdraw)
        m_dispensedVolume -= volumeChange; // Decrease displayed volume
//        m_actualVolume -= volumeChange;     // Decrease actual volume

        qDebug() << "on_updateTimer_timeout: m_actualVolume > 0. Decreasing volume. m_dispensedVolume:" << m_dispensedVolume;
        // Check for actual volume reaching zero or below
        if (m_dispensedVolume <= 0.0) {
            m_dispensedVolume = 0.0; // Cap the dispensed volume at zero

            // Stop pumping, transition to "00S" state (indicating empty)
            m_updateTimer->stop();
            m_volumeSet = false;
            m_currentStatus = "00S"; // Set status to Stopped
            qDebug() << "on_updateTimer_timeout: Volume dispensed (reached zero). Status changed to 00S.";
            emit statusChanged(m_currentStatus); // Notify GUI of status change
            emit sendResponse("00S"); // Send the specific response "00S"
        }

    } else if (!m_volumeSet) { // Use qFuzzyIsNull for robust comparison with 0.0
        // Logic for increasing volume (simulating infuse)
        m_dispensedVolume += volumeChange; // Increase displayed volume

        qDebug() << "on_updateTimer_timeout: m_actualVolume == 0. Increasing volume. m_dispensedVolume:" << m_dispensedVolume;

        // Check for actual volume exceeding limit if pump syringe volume is set (syringeVolumeML)
        if ((syringeVolumeML > 0) && (m_dispensedVolume > syringeVolumeML)) {

            // Stop pumping, transition to "00A" state (indicating full or over-infused)
            m_updateTimer->stop();
            m_currentStatus = "00A"; // Set status to Error (e.g., over-infused)
            qDebug() << "on_updateTimer_timeout: Volume limit reached. Status changed to 00A.";
            emit statusChanged(m_currentStatus); // Notify GUI of status change
            emit sendResponse("00A?S"); // Send the specific response "00A?S"
        }
    } else {
        // This case should ideally not happen if volume is always capped at 0.0 and syringeVolumeML.
        // It might indicate an issue with float precision or unexpected state outside [0, syringeVolumeML].
        // Handle as an error state.
        qDebug() << "on_updateTimer_timeout: Unexpected m_dispensedVolume state:" << m_dispensedVolume << ". Stopping timer.";
        m_updateTimer->stop(); // Stop the timer
        m_currentStatus = "00A"; // Set status to a general Error related to volume limits
        emit statusChanged(m_currentStatus); // Notify GUI of status change
        emit sendResponse("00A?E"); // Send a general error response related to volume limits
    }


    // Emit the volume changed signal with the updated formatted string based on m_dispensedVolume (for display)
    QString volumeLabelString = QString("%1 %2") // Use positional placeholders %1 and %2
                                    .arg(m_dispensedVolume, 0, 'f', 2) // %1 is m_dispensedVolume (float, precision 2) for display
                                    .arg(m_volumeUnit == "ML" ? "mL" : "uL"); // %2 is mapped unit string
    emit volumeChanged(volumeLabelString); // Emit the formatted string
}
