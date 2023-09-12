# PiMowBot-RC
![picoRC 4 PiMowBot!](/Logo.jpg "picoRC 4 PiMowBot") 
This is the code of **RControl 4 PiMowBot** ( http://pimowbot.tgd-consulting.de ).
___
Hier findet ihr den Quellcode der pico**RC** Fernbedienung für den **PiMowBot** ( http://pimowbot.tgd-consulting.de ).

### Die RC (Remote Control) benötigt mindestens diese Komponenten:
- Raspberry Pi Pico W
- Pico LCD 1.14inch Display Modul von Waveshare
- Custom MicroPython uf2 Firmware von Pimroni ( https://github.com/pimoroni/pimoroni-pico/releases/download/v1.20.4/pimoroni-picow-v1.20.4-micropython.uf2 ) 

### Die RCjoy benötigt mindestens diese Komponenten:
- Raspberry Pi Pico W
- rundes SPI LCD 1.28" Display Modul 240x240 mit GC9A01 Treiber
- analogen Joystick (Schaltplan, siehe: Joystick-Wiring_diagram.pdf)
- Custom MicroPython uf2 Firmware von Russ Hughes ( https://github.com/russhughes/gc9a01_mpy/blob/main/firmware/RP2W/firmware.uf2 ) or this ( https://github.com/TGD-Consulting/PiMowBot-RC/blob/main/GC9A01-MicroPython%20v1.20.0-452_firmware.uf2 ) with bluetooth support

### Inbetriebnahme der RC in drei Schritten:
- Flashen des Pico W mit der passenden Custom MicroPython uf2 Firmware.
- Mit Hilfe der Thonny IDE (https://thonny.org/) werden diese Dateien (***Logo.jpg*** und ***RControl.py*** bzw. ***Logo240.jpg*** und ***RCjoy.py***) des Repositories auf den Flashspeicher des Pico W übertragen.
- Vor Ausführung des *RControl.py*/*RCjoy.py* Skriptes sollten die Werte für **_SSID**, **_PASSWORD**, **_HOST** und **_TOKEN** zu Beginn des jeweiligen MicroPython Skriptes entsprechend angepasst werden.
### _!Wichtig!_
- Euer **PiMowBot** benötigt ein Release (Stand: **24. November 2022** oder **neuer**), damit die Bildübertragung zur RC funktioniert.
- Zur Steuerung via Bluetooth, also bei Verwendung von *RControlBLE.py*, benötigt der **PiMowBot** ein aktuelles Release ( **Stand: September 2023** oder **neuer**).
