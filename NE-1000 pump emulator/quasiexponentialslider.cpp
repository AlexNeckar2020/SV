#include "quasiexponentialslider.h"

QuasiExponentialSlider::QuasiExponentialSlider(QWidget *parent) : QSlider(parent)
{
    // Set a suitable internal range. 1000 gives good granularity.
    setRange(0, 1000);
    setOrientation(Qt::Horizontal); // Default orientation, can be changed

    // Connect the internal valueChanged signal to our handler
    connect(this, &QSlider::valueChanged, this, &QuasiExponentialSlider::onInternalValueChanged);
}

int QuasiExponentialSlider::internalMidpointValue() const
{
    return static_cast<int>(maximum() * m_midpointSliderProportion);
}

int QuasiExponentialSlider::internalValueToQuasiExponential(int internalValue) const
{
    double quasiExpValue_double = 0.0;
    int sliderMaxInternal = maximum();
    int midpointInternal = internalMidpointValue();

    if (internalValue <= midpointInternal) {
        // Linear mapping for the first part (0 to m_quasiExponentialMidpointValue)
        // Maps internal values from 0 to midpointInternal (0 to 500)
        // to quasi-exponential values from 0 to m_quasiExponentialMidpointValue (0 to 100)
        if (midpointInternal > 0) {
            quasiExpValue_double = (double)internalValue / midpointInternal * m_quasiExponentialMidpointValue;
        } else {
            quasiExpValue_double = 0.0; // Avoid division by zero
        }
    } else {
        // Linear mapping for the second part (m_quasiExponentialMidpointValue to m_quasiExponentialMaxValue)
        // Maps internal values from midpointInternal (500) to sliderMaxInternal (1000)
        // to quasi-exponential values from m_quasiExponentialMidpointValue (100) to m_quasiExponentialMaxValue (1000)
        double remainingSliderRange = sliderMaxInternal - midpointInternal; // 1000 - 500 = 500
        double remainingValueRange = m_quasiExponentialMaxValue - m_quasiExponentialMidpointValue; // 1000 - 100 = 900
        if (remainingSliderRange > 0) {
            quasiExpValue_double = m_quasiExponentialMidpointValue +
                                   (double)(internalValue - midpointInternal) / remainingSliderRange * remainingValueRange;
        } else {
            quasiExpValue_double = m_quasiExponentialMaxValue; // Avoid division by zero
        }
    }

    // Round the double value to the nearest integer
    int quasiExpValue_int = static_cast<int>(std::round(quasiExpValue_double));

    // Clamp the value to the defined range [0, 1000]
    return qBound(0, quasiExpValue_int, m_quasiExponentialMaxValue);
}

int QuasiExponentialSlider::quasiExponentialToInternalValue(int quasiExpValue) const
{
    int internalValue = 0;
    int sliderMaxInternal = maximum();
    int midpointInternal = internalMidpointValue();

    // Clamp the input value to the defined range [0, 1000]
    int clampedQuasiExpValue = qBound(0, quasiExpValue, m_quasiExponentialMaxValue);

    if (clampedQuasiExpValue <= m_quasiExponentialMidpointValue) {
        // Inverse mapping for the first part (0 to 100)
        // Maps quasi-exponential values from 0 to 100 to internal values from 0 to midpointInternal (500)
        if (m_quasiExponentialMidpointValue > 0) {
            internalValue = static_cast<int>(std::round((double)clampedQuasiExpValue / m_quasiExponentialMidpointValue * midpointInternal));
        } else {
            internalValue = 0; // Avoid division by zero
        }
    } else {
        // Inverse mapping for the second part (100 to 1000)
        // Maps quasi-exponential values from 100 to 1000 to internal values from midpointInternal (500) to sliderMaxInternal (1000)
        double remainingSliderRange = sliderMaxInternal - midpointInternal; // 500
        double remainingValueRange = m_quasiExponentialMaxValue - m_quasiExponentialMidpointValue; // 900
        if (remainingValueRange > 0) {
            internalValue = static_cast<int>(std::round(midpointInternal +
                                                        (double)(clampedQuasiExpValue - m_quasiExponentialMidpointValue) / remainingValueRange * remainingSliderRange));
        } else {
            internalValue = sliderMaxInternal; // Avoid division by zero
        }
    }

    // Clamp the internal value to the slider's range [0, 1000]
    return qBound(0, internalValue, sliderMaxInternal);
}

void QuasiExponentialSlider::onInternalValueChanged(int internalValue)
{
    // Convert the internal value and emit the custom signal
    emit quasiExponentialValueChanged(internalValueToQuasiExponential(internalValue));
}
