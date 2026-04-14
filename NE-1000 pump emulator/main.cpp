#include "widget.h"
#include "pump.h"

#include <QApplication>

// Global variable for the emulated syringe volume, passed as an integer in the first parameter
// Defaults to zero if not set (i.e. no pumping limits)
int syringeVolumeML = 0;

int main(int argc, char *argv[])
{
    QApplication a(argc, argv);

    // Check for a command-line argument
    if (argc > 1) {
        QString arg = QString(argv[1]);
        bool ok;
        int value = arg.toInt(&ok);

        // Check if conversion was successful and the value is a positive integer
        if (ok && value > 0) {
            syringeVolumeML = value;
        }
    }

    MainWidget w;
    w.show();
    return a.exec();
}
