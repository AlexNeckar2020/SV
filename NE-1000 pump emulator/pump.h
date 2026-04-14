#ifndef PUMP_H
#define PUMP_H

#include <QObject>
#include <QString>
#include <QStringList>
#include <QTimer> // Include QTimer for the update timer
#include <unordered_map>

// Global variable for the emulated syringe volume, passed as an integer in the first parameter
// Defaults to zero if not set (i.e. no pumping limits)
extern int syringeVolumeML; // Maximum syringe volume in mL

// Public constants for pump simulation parameters
// Note: The user specified 0.5s update rate, but a typical pump updates steps much faster.
const double PUMP_STATE_UPDATE_INTERVAL_S = 0.5; // Interval in seconds to check state and update volume
const unsigned int MAX_PUMP_RESPONSE_DELAY_MS = 1000; // Maximal pump response delay (for the slider)

// This class encapsulates the state and command processing logic for the pump
class Pump : public QObject
{
    Q_OBJECT // QObject is included in case signals/slots are needed later,
        // though simple method calls are sufficient for now.

public:
    explicit Pump(QObject *parent = nullptr);
    ~Pump();

    // Processes a command string and returns the appropriate response
    QString processCommand(const QString &command);

    // Returns the current status string
    QString currentStatus() const { return m_currentStatus; }

signals:
    // Signals emitted when key pump variables change
    void diameterChanged(double diameter);
    void rateChanged(double rate);
    void volumeChanged(const QString volume);
    // You could add a signal for status changes too if the GUI needs to react specifically
    // void statusChanged(const QString &status);
    // New signals for status changes and sending responses triggered by the timer
    void statusChanged(const QString &status); // Emitted when m_currentStatus changes
    void sendResponse(const QString &response); // Emitted when a response needs to be sent (e.g., from timer)

private:
    // Internal state variables matching the command descriptions
    QString m_currentStatus; // Initial: "00S"
    double m_syringeDiameter; // Initial: 0.0
    double m_pumpingRate;     // Initial: 0.0
    double m_dispensedVolume; // Initial: 0.0
    QString m_volumeUnit;     // Initial: "UL"
    bool m_pumpDirectionWithdraw; // Initial: false (Infuse)
//    double m_actualVolume;    // Internal volume used for pumping logic decisions
    bool m_volumeSet; // flag to determine if dispnsed volume has been set with VOL command


    // Timer for periodic volume updates when pumping
    QTimer *m_updateTimer;

    // Helper methods for each command type
    QString processReset();
    QString processPolling(); // For "" command (with injected "(poll)" for pump polling)
    QString processDia(const QStringList &params); // Handles both "DIA" and "DIA <float>"
    QString processRat(const QStringList &params); // Handles "RAT", "RAT <float>MM", "RAT C <float>"
    QString processVol(const QStringList &params); // Handles "VOL", "VOL <float>", "VOL <unit_str>"
    QString processDir(const QStringList &params); // Handles "DIR", "DIR INF", "DIR WDR", "DIR REV"
    QString processRun(); // Handles "RUN"
    QString processStp(); // Handles "STP"
    QString processVer(); // Handles "VER"
    QString processFail(); // Handles virtual "FAIL" command

    // Helper to parse float parameter with check
    bool parseFloatParam(const QStringList &params, int index, double &value);
    // Helper to check if the rate is within valid limits based on the current syringe diameter
    bool isRateValid(double rate) const;

private slots:
    // Slot for the update timer timeout
    void on_updateTimer_timeout();
};

#endif // PUMP_H
