#ifndef QUASIEXPONENTIALSLIDER_H
#define QUASIEXPONENTIALSLIDER_H

#include <QSlider>
#include <QPainter>
#include <QStyleOptionSlider>
#include <QStyle>
#include <QRect>
#include <QMouseEvent>
#include <QDebug>
#include <cmath>

class QuasiExponentialSlider : public QSlider
{
    Q_OBJECT
public:
    explicit QuasiExponentialSlider(QWidget *parent = nullptr);

    // Methods to convert between internal linear value and quasi-exponential value
    int internalValueToQuasiExponential(int internalValue) const;
    int quasiExponentialToInternalValue(int quasiExpValue) const;

signals:
    // Custom signal emitted with the quasi-exponential value
    void quasiExponentialValueChanged(double value);

private slots:
    // Slot to receive the standard valueChanged signal and emit the custom one
    void onInternalValueChanged(int internalValue);

private:
    // Define the mapping parameters
    int m_quasiExponentialMidpointValue = 100;
    int m_quasiExponentialMaxValue = 1000;
    double m_midpointSliderProportion = 1.0 / 2.0; // 100 mark at 1/3 of the slider

    // Calculate internal slider value corresponding to the midpoint value
    int internalMidpointValue() const;
};


#endif // QUASIEXPONENTIALSLIDER_H
