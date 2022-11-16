# PiMowBot-RC
![picoRC 4 PiMowBot!](/Logo.jpg "picoRC 4 PiMowBot") 
This is the code of **RControl 4 PiMowBot** ( http://pimowbot.tgd-consulting.de ).
___
Hier findet ihr den Quellcode der pico**RC** Fernbedienung für den **PiMowBot** ( http://pimowbot.tgd-consulting.de ).

### Die RC (Remote Control) benötigt mindestens diese Komponenten:
- Raspberry Pi Pico W
- Pico LCD 1.14inch Display Modul von Waveshare
- Custom MicroPython uf2 Firmware von Pimroni ( https://github.com/pimoroni/pimoroni-pico/releases/download/v1.19.9/pimoroni-picow-v1.19.9-micropython.uf2 ) 

### Inbetriebnahme der RC in drei Schritten:
- Flashen des Pico W mit der Custom MicroPython uf2 Firmware von Pimroni.
- Mit Hilfe der Thonny IDE (https://thonny.org/) werden diese Dateien (***Logo.jpg*** und ***RControl.py***) des Repositories auf den Flashspeicher des Pico W übertragen.
- Vor Ausführung des *RControl.py* Skriptes sollten die Werte für **_SSID**, **_PASSWORD**, **_HOST** und **_TOKEN** zu Beginn des *RControl.py* MicroPython Skriptes entsprechend angepasst werden.
### !*Wichtig*!
Euer **PiMowBot** benötigt ein aktuelles Release (Stand: **16. November 2022**), damit die Bildübertragung zur RC funktioniert.  
