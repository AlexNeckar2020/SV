#ifndef WIDGET_H
#define WIDGET_H

#include <QWidget>
#include "ui_widget.h"
#include <QSerialPort>
#include <QTimer>

#include "pump.h" // Include the new Pump class header
#include "quasiexponentialslider.h" // Include the custom quasi-exponential slider

QT_BEGIN_NAMESPACE
namespace Ui { class MainWidget; }
QT_END_NAMESPACE

class MainWidget : public QWidget
{
    Q_OBJECT

public:
    MainWidget(QWidget *parent = nullptr);
    ~MainWidget();

private slots:
    // Renamed the slot to avoid auto-connection
    void handlePump1DelayChanged(int value);
    void on_pump1Command_returnPressed();
    void on_pump1Port_currentTextChanged(const QString &portName);
    void on_pump1ManualResponse_toggled(bool checked);
    // Slots to update UI labels when Pump variables change
    void updateDiameterLabel(double value);
    void updateRateLabel(double value);
    void updateVolumeLabel(const QString &valueString);
    void populateSerialPorts();
    void handlePortChanged(const QString &portName);
    void handleReadyRead();
    void handleTimeout();
    // Slot to handle responses emitted by the Pump object (e.g., from its internal timer)
    void handlePumpResponse(const QString &response);

private:
    Ui::Widget *ui;
    QGroupBox *pump1Settings;
    QLineEdit *pump1Command;
    QLineEdit *pump1Response;
    QuasiExponentialSlider *pump1Delay;
    QLabel *pump1DelayValue;
    QLabel *pump1LabelCommand;
    QLabel *pump1LabelDelay;
    QLabel *pump1LabelPort;
    QLabel *pump1LabelResponse;
    QLabel *pump1Status;
    QCheckBox *pump1ManualResponse;
    QComboBox *pump1Port;
    QSerialPort *serialPort;
    QTimer *responseTimer;   // Timer to simulate pump processing delay
    QString m_receivedCommand;
    Pump *m_pump; // Instance of the Pump class to manage pump state and logic

    // Helper to update the status label's text and color based on status string
    void updateStatusLabel(const QString &statusText);
};
#endif // WIDGET_H
