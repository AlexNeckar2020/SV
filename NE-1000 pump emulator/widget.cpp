#include "widget.h"
#include "ui_widget.h"

#include <QSerialPort>
#include <QSerialPortInfo>
#include <QTimer> // Keep QTimer for the response delay simulation
#include <QDebug> // Keep for logging
#include <QMessageBox> // Keep for port errors
#include <QString>
#include <QByteArray>
#include <QtMath> // For qFuzzyIsNull

#include <unordered_map>
#include <stdexcept> // for potential errors, though simpler handling is used

// Include the new Pump class header
#include "pump.h"
// Include the custom quasi-exponential slider
#include "quasiexponentialslider.h"



MainWidget::MainWidget(QWidget *parent)
    : QWidget(parent)
    , ui(new Ui::Widget)
    , serialPort(new QSerialPort(this))
    , responseTimer(new QTimer(this))
    // Initialize the Pump object here. 'this' makes MainWidget the parent,
    // so the Pump object will be automatically deleted when MainWidget is deleted.
    , m_pump(new Pump(this))
{
    ui->setupUi(this);

    // Configure the custom slider's range (internal linear range)
    // This range determines the granularity of the slider movement.
    // The mapping functions handle the conversion to the quasi-exponential scale 0 ... MAX_PUMP_RESPONSE_DELAY_MS (in ms).
    ui->pump1Delay->setRange(0, MAX_PUMP_RESPONSE_DELAY_MS);

    // Set tick properties for the standard QSlider tick drawing
    //ui->pump1Delay->setTickPosition(QSlider::TicksBelow); // Or TicksBothSides, TicksAbove
    //ui->pump1Delay->setTickInterval(100); // Set the interval for linear ticks based on internal range

    // Populate the combo box with available serial ports
    populateSerialPorts();

    // Set the title of the QGroupBox if pumpValue is greater than 0
    if (syringeVolumeML > 0) {
        QString newTitle = QString("Pump (%1 mL syringe)").arg(syringeVolumeML); // Show syringe volume in QGroupBox title if passed as a parameter
        ui->pump1Settings->setTitle(newTitle);
    }

    // Connect signals and slots
    // Connecting QComboBox::currentTextChanged to both handlePortChanged and on_pump1Port_currentTextChanged
    // is redundant if on_pump1Port_currentTextChanged just calls handlePortChanged.
    // Keeping both for now as per original code structure, but could simplify.
    connect(ui->pump1Port, &QComboBox::currentTextChanged, this, &MainWidget::handlePortChanged); // connect signal for port changes
    // Keep this connection to receive data from the serial port
    connect(serialPort, &QSerialPort::readyRead, this, &MainWidget::handleReadyRead);
    // Keep this connection to trigger response generation after the delay
    connect(responseTimer, &QTimer::timeout, this, &MainWidget::handleTimeout);

    // Connect UI elements to slots
    // Connect to the custom signal that emits the quasi-exponential value
    connect(ui->pump1Delay, &QuasiExponentialSlider::quasiExponentialValueChanged,
            this, &MainWidget::handlePump1DelayChanged);
    connect(ui->pump1Command, &QLineEdit::returnPressed, this, &MainWidget::on_pump1Command_returnPressed);
    // This slot also handles port changes, potentially redundant with the handlePortChanged connection above
    connect(ui->pump1Port, &QComboBox::currentTextChanged, this, &MainWidget::on_pump1Port_currentTextChanged);
    ui->pump1Port->setCurrentIndex(-1); // Ensure no initial selection in the combo box.
    // Connect the toggled signal of the checkbox to our new slot
    connect(ui->pump1ManualResponse, &QCheckBox::toggled, this, &MainWidget::on_pump1ManualResponse_toggled);
    // Trigger the slot once with the initial state of the checkbox
    on_pump1ManualResponse_toggled(ui->pump1ManualResponse->isChecked());
    // Connect Pump signals to MainWidget slots
    connect(m_pump, &Pump::diameterChanged, this, &MainWidget::updateDiameterLabel);
    connect(m_pump, &Pump::rateChanged, this, &MainWidget::updateRateLabel);
    connect(m_pump, &Pump::volumeChanged, this, &MainWidget::updateVolumeLabel);
    // Connect new signals from Pump for status updates and sending responses from the timer
    connect(m_pump, &Pump::statusChanged, this, &MainWidget::updateStatusLabel); // Update status label when Pump status changes
    connect(m_pump, &Pump::sendResponse, this, &MainWidget::handlePumpResponse); // Send responses emitted by Pump

    // Set initial status label appearance based on the Pump's default status ("00S")
    updateStatusLabel(m_pump->currentStatus());
    // Set alignment for the status label (can also be done in UI file)
    ui->pump1Status->setAlignment(Qt::AlignCenter);
}

MainWidget::~MainWidget()
{
    // Delete the Pump object first.
    delete m_pump;
    // Delete Qt objects that have 'this' as parent are usually deleted automatically
    // when the parent is deleted, but explicit deletion is also safe and matches original code structure.
    delete ui;
    delete serialPort;
    delete responseTimer;
}

void MainWidget::populateSerialPorts()
{
    ui->pump1Port->clear();
    QList<QSerialPortInfo> ports = QSerialPortInfo::availablePorts();
    for (const QSerialPortInfo &portInfo : ports) {
        ui->pump1Port->addItem(portInfo.portName());
    }
    if (ports.isEmpty()) {
        ui->pump1Port->addItem(""); // Add an empty item if no ports are found
    }
}

void MainWidget::handlePortChanged(const QString &portName)
{
    // Close the currently open port if any
    if (serialPort->isOpen()) {
        serialPort->close();
        qDebug() << "Disconnected from previous port";
    }

    // If the new port name is empty (e.g., nothing selected), just return
    if (portName.isEmpty()) {
        qDebug() << "No port selected.";
        return;
    }

    // Configure and open the selected serial port
    serialPort->setPortName(portName);
    serialPort->setBaudRate(QSerialPort::Baud19200);
    serialPort->setDataBits(QSerialPort::Data8);
    serialPort->setParity(QSerialPort::NoParity);
    serialPort->setStopBits(QSerialPort::OneStop);
    serialPort->setFlowControl(QSerialPort::NoFlowControl);

    if (serialPort->open(QIODevice::ReadWrite)) {
        qDebug() << "Connected to" << portName;
        // Optionally update a UI status indicator here
    } else {
        // Show an error message if opening fails
        QMessageBox::critical(this, "Error", "Failed to open serial port: " + serialPort->errorString());
        qDebug() << "Failed to open serial port" << portName << ":" << serialPort->errorString();
        // Optionally reset the combo box or UI status on failure
    }
}

void MainWidget::handleReadyRead()
{
    QByteArray data = serialPort->readAll();
    // Look for a carriage return '\r' to identify a complete command
    if (data.contains('\r')) {
        // Find the position of the carriage return
        int newlineIndex = data.indexOf('\r');

        // Extract the command (up to the carriage return)
        QByteArray commandBytes = data.left(newlineIndex);

        // Convert the command to a QString, handling potential encoding issues and trimming whitespace
        // Convert toUpper() to make command matching case-insensitive as per common protocol practice
        QString command = QString(commandBytes).toUpper().trimmed();

        // If empty line received as a command, the pump was polled - inject "(poll)" as virtual command
        if (command.isEmpty())
            command = "(poll)";

        qDebug() << "handleReadyRead: Received complete command bytes:" << data.toHex() << ", Parsed Command:" << command;

        // On;y display incoming commands if "Manual send" is not checked - otherwise the input will be overwritten e.g. on every poll
        if (!(ui->pump1ManualResponse->isChecked()))
            ui->pump1Command->setText(command); // Display the received command in the command line edit

        // Store the received command for processing after the delay.
        // Start the timer for the simulated processing delay.
        // The actual command processing and response sending happens when the timer times out in handleTimeout.
        responseTimer->start(ui->pump1Delay->value());
        m_receivedCommand = command; // Store the command string
    } else {
        // If no carriage return is found, it's a partial command.
        // Depending on the protocol, you might need to buffer partial data.
        // For this simple simulation, we only process when '\r' is found.
        qDebug() << "handleReadyRead: Received partial data (no newline):" << data.toHex();
    }
}

void MainWidget::handleTimeout()
{
    // This function is called when the responseTimer expires, simulating the pump's processing delay.

    // Check if there is a command stored to be processed
    // This timer handles the initial response to a command received via serial or manual input.
    if (!m_receivedCommand.isEmpty()) {
        qDebug() << "handleTimeout: Processing stored command:" << m_receivedCommand;

        // Pass the stored command to the Pump object for logic execution and response generation.
        // The Pump object updates its internal state (status, variables) based on the command.
        QString response = m_pump->processCommand(m_receivedCommand);

        qDebug() << "handleTimeout: Pump processed command, Generated Initial Response:" << response;
        // Send the response returned by Pump::processCommand back over serial
        handlePumpResponse(response); // Use the new helper slot to send the response

        // Update the UI based on the response and the Pump's *new* state.
        ui->pump1Response->setText(response); // Display the response string

        // Get the current status from the Pump object and update the status label's text and color.
        updateStatusLabel(m_pump->currentStatus());

        // Clear the stored command now that it has been processed and responded to.
        m_receivedCommand.clear();
    } else {
        // This case should ideally not happen if the timer is only started when a command is received.
        qDebug() << "handleTimeout: Timer timed out but no command was stored.";
    }
}

// Slot to handle responses emitted by the Pump object (e.g., state change responses from timer)
void MainWidget::handlePumpResponse(const QString &response)
{
    qDebug() << "handlePumpResponse: Received response from Pump:" << response;

    // Send the response back over the serial port
    QByteArray responseBytes;
    responseBytes.append(0x02); // Start of Text (STX)
    responseBytes.append(response.toLatin1()); // Append the response string
    responseBytes.append(0x03); // End of Text (ETX)

    if (serialPort->isOpen()) {
        qint64 bytesWritten = serialPort->write(responseBytes);
        if (bytesWritten == -1) {
            qDebug() << "handlePumpResponse: Error writing to serial port:" << serialPort->errorString();
        } else {
            qDebug() << "handlePumpResponse: Response sent:" << responseBytes.toHex() << "(" << bytesWritten << " bytes)";
        }
        serialPort->flush(); // Ensure data is sent immediately
    } else {
        qDebug() << "handlePumpResponse: Serial port not open, cannot send response.";
    }
}

// Slot connected to the pump1Delay slider's valueChanged signal.
void MainWidget::handlePump1DelayChanged(int value)
{
    // Update the label next to the slider to show the current delay value.
    qDebug() << "handlePump1DelayChanged: Pump delay changed to: " << value << " ms";
    ui->pump1DelayValue->setText(QString::number(value) + " ms");
    // The timer's interval is set in handleReadyRead just before starting it.
}

// Slot connected to the pump1Command line edit's returnPressed signal.
void MainWidget::on_pump1Command_returnPressed()
{
    // This slot is triggered when the user presses Enter in the pump1Command line edit.
    // We only process the input if the line edit is currently editable (manual response mode).
    if (!ui->pump1Command->isReadOnly()) {
        QString command = ui->pump1Command->text().trimmed(); // Get the text and remove leading/trailing whitespace
        qDebug() << "on_pump1Command_returnPressed: Manually entered command: " << command;
        // Check if the entered command is not empty after trimming
        if (!command.isEmpty()) {
            // Copy the command to m_receivedCommand, converting to uppercase
            // This simulates receiving the command via serial.
            m_receivedCommand = command.toUpper();
            // Start the response timer to simulate the pump's processing delay.
            // handleTimeout will then pick up m_receivedCommand and process it.
        responseTimer->start(ui->pump1Delay->value());
        } else {
            qDebug() << "on_pump1Command_returnPressed: Ignoring empty command entered manually.";
        }
    } else {
    // If the line edit is read-only (manual response is off), do nothing or just print debug.
    qDebug() << "on_pump1Command_returnPressed: Return pressed in command line edit with text: " << ui->pump1Command->text();
    }
}

// Slot connected to the pump1Port combo box's currentTextChanged signal.
// This slot is called when the selected port changes.
// It effectively acts as a wrapper around handlePortChanged.
void MainWidget::on_pump1Port_currentTextChanged(const QString &portName)
{
    qDebug() << "on_pump1Port_currentTextChanged: Port changed to: " << portName;
    // Call the function that handles the serial port connection logic.
    handlePortChanged(portName);
}

void MainWidget::on_pump1ManualResponse_toggled(bool checked)
{
    if (checked) {
        // If checkbox is checked, make pump1Command editable and set text color to green
        ui->pump1Command->setReadOnly(false);
        ui->pump1Command->setStyleSheet("color: rgb(0, 127, 0);"); // Green color
        qDebug() << "pump1ManualResponse checked: pump1Command editable and green";
    } else {
        // If checkbox is unchecked, make pump1Command read-only and set text color back to blue
        ui->pump1Command->setReadOnly(true);
        ui->pump1Command->setStyleSheet("color: rgb(0, 0, 127);"); // Blue color (your default)
        qDebug() << "pump1ManualResponse unchecked: pump1Command read-only and blue";
    }
}

// Slot to update the pumpDiamValue label when diameter changes in Pump
void MainWidget::updateDiameterLabel(double value)
{
    // Format the double value to 2 decimal places and set as the label's text
    ui->pumpDiamValue->setText(QString::asprintf("%.2f", value));
    qDebug() << "pumpDiamValue updated to:" << value;
}

// Slot to update the pumpRateValue label when rate changes in Pump
void MainWidget::updateRateLabel(double value)
{
    // Format the double value to 2 decimal places and set as the label's text
    ui->pumpRateValue->setText(QString::asprintf("%.2f", value));
    qDebug() << "pumpRateValue updated to:" << value;
}

// Slot to update the pumpVolValue label when volume changes in Pump
void MainWidget::updateVolumeLabel(const QString &valueString)
{
    // Format the double value to 2 decimal places and set as the label's text
    ui->pumpVolValue->setText(valueString);
    qDebug() << "pumpVolValue updated to:" << valueString;
}

// --- New Helper Method ---
// This method updates the text and background color of the pump1Status QLabel
// based on the provided status string from the Pump object.
void MainWidget::updateStatusLabel(const QString &statusText)
{
    // Set the text of the status label
    ui->pump1Status->setText(statusText);

    // Determine the background color based on the status string using a stylesheet.
    QString backgroundColorStyle = "";
    // Map pump status codes to background colors as defined previously.
    if (statusText == "00I") { // Infuse
        backgroundColorStyle = "background-color: #20F000;";
    } else if (statusText == "00W") { // Withdraw
        backgroundColorStyle = "background-color: #FF60B0;";
    } else if (statusText == "00S") { // Stop
        backgroundColorStyle = "background-color: #60B0FF;";
    } else if (statusText == "00P") { // Pause
        backgroundColorStyle = "background-color: #F0F000;";
    } else if (statusText == "00A") { // Error (=Alarm)
        backgroundColorStyle = "background-color: #FF0000;";
    } else {
        // Set a default color or clear the style for any other status codes.
        backgroundColorStyle = ""; // Clears the background style
        // Or: backgroundColorStyle = "background-color: lightgrey;"; // Example default
    }
    // Apply the generated stylesheet to set the background color.
    ui->pump1Status->setStyleSheet(backgroundColorStyle);
    // Alignment (Qt::AlignCenter) is set once in the constructor, no need to set it here repeatedly.
}
