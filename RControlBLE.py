#/****************************************************************************
# *  PiMowBot-RC_BLE                                                         *
# *  ===============                                                         *
# *  Mit Hilfe dieses Mircopython-Skripts für den Raspberry Pi Pico W und    *
# *  eines Pico-LCD_1.14 Zoll LCD Display Modul von Waveshare wird eine      *
# *  kleine RemoteControl für den PiMowBot realisiert, die anstelle des      *
# *  Webbrowsers die Steuerung des PiMowBots ermöglicht.                     *
# *                                                                          *
# *  Die Übertragung der Steuerbefehle erfolgt per BLE an den PiMowBot.      *
# *  (Repository: https://github.com/micropython/micropython/tree/master/    *
# *               examples/bluetooth)                                        *
# *                                                                          *
# *  Homepage: http://pimowbot.TGD-Consulting.de                             *
# *                                                                          *
# *  Version 0.1.0                                                           *
# *  Datum 31.08.2023                                                        *
# *                                                                          *
# *  (C) 2023 TGD-Consulting , Author: Dirk Weyand                           *
# ****************************************************************************/

import sys
import bluetooth
import struct
import jpegdec
import gc
import uasyncio as asyncio
from micropython import const
from machine import ADC, Pin, reset
from time import sleep, ticks_ms, ticks_diff
from math import atan2, degrees, sqrt, cos, sin, pi

_M = const(0)       # Mode, replace 0 with 1 if analogue joystick is used
_D = const(True)    # Change to False if display isn't connected to the PicoW
_WD = const(1)      # Waveshare-Display, replace 1 with 0 if other display is used
_BTA = const(1)     # Darstellung der Steuerbutton
_DB = const(True)   # Change to False to disable debug info
_FB = const (0)     # Set to 1 to enable FastBoot

# dormant mode 
_DP1 = const(15)    # btn_a
_DP2 = const(17)    # btn_b

_OX = const(99)     # Offset X Steuerknüppel
_OY = const(80)     # Offset Y Steuerknüppel

# Joystick and buttons
joy_l = Pin(16, Pin.IN, Pin.PULL_UP) # left
joy_r = Pin(20, Pin.IN, Pin.PULL_UP) # right
joy_u = Pin(2, Pin.IN, Pin.PULL_UP)  # up
joy_d = Pin(18, Pin.IN, Pin.PULL_UP) # down
joy_c = Pin(3, Pin.IN, Pin.PULL_UP)  # center
btn_a = Pin(_DP1, Pin.IN, Pin.PULL_UP)
btn_b = Pin(_DP2, Pin.IN, Pin.PULL_UP)

D = "unknown"    # current direction
last_btn = 0     # last button value
btn_val = 0      # current button

led = Pin("LED", machine.Pin.OUT)

def uid():
    """ Return the unique id of the device as a string """
    return "{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}".format(
        *machine.unique_id())

# Advertising payloads are repeated packets of the following form:
#   1 byte data length (N + 1)
#   1 byte type (see constants below)
#   N bytes type-specific data

_ADV_TYPE_FLAGS = const(0x01)
_ADV_TYPE_NAME = const(0x09)
_ADV_TYPE_UUID16_COMPLETE = const(0x3)
_ADV_TYPE_UUID32_COMPLETE = const(0x5)
_ADV_TYPE_UUID128_COMPLETE = const(0x7)
_ADV_TYPE_UUID16_MORE = const(0x2)
_ADV_TYPE_UUID32_MORE = const(0x4)
_ADV_TYPE_UUID128_MORE = const(0x6)
_ADV_TYPE_APPEARANCE = const(0x19)

# Generate a payload to be passed to gap_advertise(adv_data=...).
def advertising_payload(limited_disc=False, br_edr=False, name=None, services=None, appearance=0):
    payload = bytearray()

    def _append(adv_type, value):
        nonlocal payload
        payload += struct.pack("BB", len(value) + 1, adv_type) + value

    _append(
        _ADV_TYPE_FLAGS,
        struct.pack("B", (0x01 if limited_disc else 0x02) + (0x18 if br_edr else 0x04)),
    )

    if name:
        _append(_ADV_TYPE_NAME, name)

    if services:
        for uuid in services:
            b = bytes(uuid)
            if len(b) == 2:
                _append(_ADV_TYPE_UUID16_COMPLETE, b)
            elif len(b) == 4:
                _append(_ADV_TYPE_UUID32_COMPLETE, b)
            elif len(b) == 16:
                _append(_ADV_TYPE_UUID128_COMPLETE, b)

    # See org.bluetooth.characteristic.gap.appearance.xml
    if appearance:
        _append(_ADV_TYPE_APPEARANCE, struct.pack("<h", appearance))

    return payload

_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_INDICATE_DONE = const(20)

_FLAG_READ = const(0x0002)
_FLAG_NOTIFY = const(0x0010)
_FLAG_INDICATE = const(0x0020)

#BLE-Device Services and Characteristics

_RC_GENERIC_UUID = bluetooth.UUID(0x1849)  # Generic Media Control

_NAV_CHAR = (bluetooth.UUID(0x2A68), _FLAG_READ | _FLAG_NOTIFY | _FLAG_INDICATE, )      # Navigation Characteristics

_RC_NAV_SERVICE = (_RC_GENERIC_UUID, (_NAV_CHAR,),)

_BLE_APPEARANCE_HID_GAMEPAD = const(964)

MANUFACTURER_ID = const(0x02A29)
MODEL_NUMBER_ID = const(0x2A24)
SERIAL_NUMBER_ID = const(0x2A25)
HARDWARE_REVISION_ID = const(0x2A26)
BLE_VERSION_ID = const(0x2A28)

_DEV_INFO_UUID = bluetooth.UUID(0x180A)   # Device Information
_DEV_MAN_CHAR = (bluetooth.UUID(MANUFACTURER_ID), _FLAG_READ, )
_DEV_MOD_CHAR = (bluetooth.UUID(MODEL_NUMBER_ID), _FLAG_READ, )
_DEV_SER_CHAR = (bluetooth.UUID(SERIAL_NUMBER_ID), _FLAG_READ, )
_DEV_HARD_CHAR = (bluetooth.UUID(HARDWARE_REVISION_ID), _FLAG_READ, )
_DEV_VER_CHAR = (bluetooth.UUID(BLE_VERSION_ID), _FLAG_READ, )
_DEV_INFO_SERVICE = (_DEV_INFO_UUID, (_DEV_MAN_CHAR, _DEV_MOD_CHAR, _DEV_SER_CHAR, _DEV_HARD_CHAR, _DEV_VER_CHAR,),)

_ADV_INTERVAL_MS = const(250000)

connected = False

class BLERemoteControl:
    def __init__(self, ble, name="PiMowBotRC"):
        self._ble = ble
        self._ble.active(True)
        self._ble.irq(self._irq)
        ((self._handle,), (i1, i2, i3, i4, i5,),) = self._ble.gatts_register_services((_RC_NAV_SERVICE, _DEV_INFO_SERVICE,))
        self._connections = set()
        self._ble.gatts_write(i1, "PiMowBot.tgd-consulting.DE")
        self._ble.gatts_write(i2, "1.0")
        self._ble.gatts_write(i3, uid())
        self._ble.gatts_write(i4, sys.version)
        self._ble.gatts_write(i5, "1.0")
        self._payload = advertising_payload(name=name, services=[_RC_GENERIC_UUID], appearance=_BLE_APPEARANCE_HID_GAMEPAD)
        self._advertise()

    def _irq(self, event, data):
        global connected
        # Track connections so we can send notifications.
        if event == _IRQ_CENTRAL_CONNECT:
            conn_handle, _, addr = data
            print("New connection from, ", addr)
            connected = True
            if _WD:
                display_BTlogo()
            self._connections.add(conn_handle)
        elif event == _IRQ_CENTRAL_DISCONNECT:
            conn_handle, _, addr = data
            print("Disconnected ", addr)
            self._connections.remove(conn_handle)
            connected = False
            if _WD:
                display_image("Logo.jpg")
            # Start advertising again to allow a new connection.
            self._advertise()
        elif event == _IRQ_GATTS_INDICATE_DONE:
            conn_handle, value_handle, status = data

    def is_connected(self):
        return len(self._connections) > 0

    def set_navigation(self, data, notify=False, indicate=False):
        # Data is string with navigation info.
        # Write the local value, ready for a central to read.
        self._ble.gatts_write(self._handle, bytes(str(data), 'utf-8'))
        if notify or indicate:
            for conn_handle in self._connections:
                if notify:
                    # Notify connected centrals.
                    self._ble.gatts_notify(conn_handle, self._handle)
                if indicate:
                    # Indicate connected centrals.
                    self._ble.gatts_indicate(conn_handle, self._handle)

    def _advertise(self, interval_us=_ADV_INTERVAL_MS):
        print("Starting advertising")
        self._ble.gap_advertise(interval_us, adv_data=self._payload)

#/***********************
# *** Display Helpers ***
# ***********************/

def reset_display():
    rst = Pin(12,Pin.OUT)
    rst.on()
    rst.off()
    rst.on()

def display_blank():
    BLACK = display.create_pen(0, 0, 0)
    display.set_pen(BLACK)
    display.clear()
    display.set_backlight(0.0)
    display.update()

def display_col(R=90, G=220, B=240):
    COL = display.create_pen(R, G, B)
    display.set_pen(COL)
    display.clear()
    display.update()
    
def display_image(file='image.jpg', x=0, y=0):
    gc.collect()
    # Create a new JPEG decoder for our PicoGraphics
    j = jpegdec.JPEG(display)
     
    # Open the JPEG file
    j.open_file(file)
    # Decode the JPEG
    j.decode(x, y, jpegdec.JPEG_SCALE_FULL)
     
    # Display the result
    display.update()

def display_BTlogo():
    DGREY = display.create_pen(80, 80, 80)
    display.set_pen(DGREY)
    x = 124
    y = 22
    display.triangle(x - 8, y, x, y - 5, x, y + 5) #left
    x = 124
    y = 30
    display.triangle(x - 8, y, x, y - 5, x, y + 5) #left
    x = 125
    y = 22
    display.triangle(x + 8, y, x, y - 5, x, y + 5) #right
    x = 125
    y = 30
    display.triangle(x + 8, y, x, y - 5, x, y + 5) #right
    BACK = display.create_pen(90, 220, 240)
    display.set_pen(BACK)
    x = 125
    y = 22
    display.triangle(x + 4, y, x, y - 2, x, y + 2) #right small blank
    x = 125
    y = 30
    display.triangle(x + 4, y, x, y - 2, x, y + 2) #right small blank
    x = 124
    y = 22
    display.triangle(x - 8, y, x, y - 5, x, y + 2) #left blank
    x = 124
    y = 30
    display.triangle(x - 8, y, x, y - 2, x, y + 5) #left blank
    display.update()
    
def display_text(text, dir = 0):
    GREY = display.create_pen(132, 132, 132)
    RED = display.create_pen(250, 132, 132)
    BACK = display.create_pen(90, 220, 240)
    display.set_pen(BACK)
    if dir:
        display.rectangle(133, 5, 102, 17)
        display.set_pen(GREY)
        display.set_font('bitmap8')
        display.text(text, 133, 5, 102, 2) # show text
    else:
        display.rectangle(2, 105, 236, 20) # remove lawn on display
        display.set_pen(GREY)
        display.set_font('bitmap8')
        display.text(text, 2, 105, 236, 2) # show text
    display.update()

def display_alert(toggle=True):
    GREY = display.create_pen(132, 132, 132)
    RED = display.create_pen(250, 132, 132)
    BACK = display.create_pen(90, 220, 240)
    display.set_pen(BACK)
    display.rectangle(2, 105, 236, 20) # remove lawn on display
    if toggle:
        display.set_pen(GREY)
    else:
        display.set_pen(RED)
    display.set_font('bitmap8')
    display.text(" >> " + al + " << ", 2, 105, 236, 2)
    display.update()

def display_up(set=True):
    if _BTA:
        if set:
            RED = display.create_pen(250, 132, 132)
            display.set_pen(RED)
        else:
            DGREY = display.create_pen(80, 80, 80)
            display.set_pen(DGREY)
        display.triangle(_OX, _OY - 18, _OX - 10, _OY - 10, _OX + 10, _OY - 10) #up
        display.update()
    
def display_down(set=True):
    if _BTA:
        if set:
            RED = display.create_pen(250, 132, 132)
            display.set_pen(RED)
        else:
            DGREY = display.create_pen(80, 80, 80)
            display.set_pen(DGREY)
        display.triangle(_OX, _OY + 18, _OX + 10, _OY + 10, _OX - 10, _OY + 10) #down
        display.update()
 
def display_left(set=True):
    if _BTA:
        if set:
            RED = display.create_pen(250, 132, 132)
            display.set_pen(RED)
        else:
            DGREY = display.create_pen(80, 80, 80)
            display.set_pen(DGREY)
        display.triangle(_OX - 18, _OY, _OX - 10, _OY - 10, _OX - 10, _OY + 10) #left
        display.update()        

def display_right(set=True):
    if _BTA:
        if set:
            RED = display.create_pen(250, 132, 132)
            display.set_pen(RED)
        else:
            DGREY = display.create_pen(80, 80, 80)
            display.set_pen(DGREY)
        display.triangle(_OX + 18, _OY, _OX + 10, _OY - 10, _OX + 10, _OY + 10) #right
        display.update()

def display_center(set=True):
    if _BTA:
        if set:
            RED = display.create_pen(250, 132, 132)
            display.set_pen(RED)
        else:
            GREY = display.create_pen(132, 132, 132)
            display.set_pen(GREY)
        display.circle(_OX, _OY, 5)      # Center btn
        display.update()

def display_dir(odir="Init"):
    if (odir == "u"):
        display_up(0)
    if (odir == "d"):
        display_down(0)
    if (odir == "l"):
        display_left(0)
    if (odir == "r"):
        display_right(0)
    if (odir == "cc") or (odir == "cw"):
        display_center(0)
    if (odir == "dLeft"):
        display_up(0)
        display_left(0)
        display_down(0)
    if (odir == "dRight"):
        display_down(0)
        display_right(0)
        display_up(0)  
    if (odir == "Init"):
        display_up()
        sleep(0.3)
        display_right()
        sleep(0.3)
        display_down()
        sleep(0.3)
        display_left()
        sleep(0.3)
        display_center()
        sleep(0.3)
        display_up(0)
        sleep(0.3)
        display_right(0)
        sleep(0.3)
        display_down(0)
        sleep(0.3)
        display_left(0)
        sleep(0.3)
        display_center(0)
        sleep(0.3)
        
# Init Display
if _WD:
    from pimoroni_bus import SPIBus
    from picographics import PicoGraphics, DISPLAY_PICO_DISPLAY, PEN_RGB565
    reset_display()
    spibus = SPIBus(cs=9, dc=8, sck=10, mosi=11, bl=13)
    display = PicoGraphics(display=DISPLAY_PICO_DISPLAY, bus=spibus, pen_type= PEN_RGB565, rotate=0)
    display.set_backlight(0.7)
    if _FB:
        display_col()
    else:
        # Show Logo
        display_image("Logo.jpg")
#    display_BTlogo()
#    display_dir()
else:
    pass # TBD

_AKTION = ["tl", "m", "tr", "sd"] # Aktionen "Turn-L", "Mower", "Turn-R", "Shutdown"
_AB = ["Turn-L", "Mower", "Turn-R", "Shutdown"]
ai = 1                                   # aktueller Aktions-Index
blanka = False

def change_aktion(step=1):
    global ai, blanka
    if step < 0:
        ai -= 1
        if ai < 0:
            ai = -1 + len(_AKTION)
    else:
        ai += 1
        if ai >= len(_AKTION):
            ai = 0
    if _D:
        display_text("A:" + '{: >9}'.format(_AB[ai]), 1)
        blanka = False
    else:
        print(f"Aktion: {_AB[ai]}")

#/**************************
# *** Joystick Parameter ***
# **************************/

ADCX = ADC(26)   # GPIO26, Pin#31
ADCY = ADC(27)   # GPIO27, Pin#32
ADCZ = ADC(28)   # GPIO28,Pin#34

_BTN = const(22) # GPIO22, Pin#29
_NX = const(False)
_NY = const(True) # negiert Y Werte
_NZ = const(False)

btn = Pin(_BTN, Pin.IN, Pin.PULL_UP)

force = 0
angel = 0
Z = 0

def read_analog(ADC):
    val = ADC.read_u16()  # 0 - 65535
    return val
      
def joy(channel): # left right
    val = read_analog(channel)
    val -= 32768
    val /= 28456
    return val
    
def get_joy():
    global angel, force, Z, al
    x = joy(ADCX)    # left right
    if _NX:          # Werte x negieren
        x = x * -1
    #print("Joy-X: ",x)
    y = joy(ADCY)    # up down
    if _NY:          # Werte y negieren
        y = y * -1
    #print("Joy-Y: ",y)
    angel = degrees(atan2(y,x)) # Ist-Werte oben 0 (E) bis 180 (W)/ unten -0 (E) bis -180 (W)
    # Soll-Werte up: 0 right 90 left -90 down 180
    # daher Korrektur:
    if angel < 0: # untere Hälfte Winkel von 90 (E) bis 180 (S) und -90 (W) bis -180 (S)
        if angel >= -90:
            angel = 90 + (angel * -1)
        else:
            angel = (angel * -1) - 270            
    else: # obere Hälfte -90 (E) bis 90 (W)
        angel -= 90      # Korrektur, 90 Grad nach rechts drehen
        angel *= -1      # und negieren
    angel = int(round(angel, 0))    
    #print("Winkel: ",angel)
    force = round(sqrt((x*x)+(y*y)),1)
    #print("Force: ",force)
    z = joy(ADCZ)    # rotate cw - ccw
    if _NZ:          # Werte z negieren
        z = z * -1
    #print("Joy-Z: ",z)
    Z = z
    if _DB:
        al = "X: " + "{:.2f}".format(x) + ", Y: " + "{:.2f}".format(y) + ", Z: " + "{:.2f}".format(z)
        display_alert()
        
#/*************
# *** Tasks ***
# *************/

async def control_task(mode = 0):
    """ Task to handle button control """
    
    global btn_val, blanka
    oforce = 0
    oangel = 0
    n = 0
    while True:
        if mode:       # Joystick
            get_joy()  # abfragen
            if force > 0.3:
                if ((oforce != min (1, force)) or (abs(oangel - angel) >= 5 )):
                    btn_val = str(force)+" "+str(angel)
                    oforce = min (1, force)
                    oangel = angel
            else:
                btn_val = "0"
            if 0 == btn.value():                       # do aktion
                btn_val = _AKTION[ai]
            elif (abs (Z) >= 0.1) and (abs (Z) < 0.6): # toggle aktion
                n += 1
                if n > 2:
                    n = 0
                    if Z < 0:
                        change_aktion(-1)
                    else:
                        change_aktion()
            elif abs (Z) >= 0.6:
                if Z < 0:
                    btn_val = "cc "+str(round(Z, 1))
                else:
                    btn_val = "cw "+str(round(Z, 1))    
        else:
            if 0 == joy_u.value():
                btn_val = "u"
            elif 0 == joy_d.value():
                btn_val = "d"
            elif 0 == joy_c.value():
                if (joy_l.value() == 0) or (last_btn == "cc"):
                    btn_val = "cc"
                elif (joy_r.value() == 0) or (last_btn == "cw"):
                    btn_val = "cw"
                else:
                    btn_val = "cw"
            elif 0 == joy_l.value():
                btn_val = "l"
            elif 0 == joy_r.value():
                btn_val = "r"
            elif (btn_a.value() == 0) and (btn_b.value() == 0):
                btn_val = "sd"
            elif 0 == btn_a.value():
                btn_val = _AKTION[ai]   # toggle/do aktion
            elif 0 == btn_b.value():
                change_aktion()
            else:
                btn_val = 0
            if btn_val in ["u", "d", "l", "r", "cc" "cw"]:
                blanka = True
        await asyncio.sleep_ms(100)
        
async def remote_task():
    """ Task to handle remote control """
    
    global last_btn
    ble = bluetooth.BLE()
    p = BLERemoteControl(ble)
    jetzt = ticks_ms()
    n = 0

    jetzt = ticks_ms()
    n = 0
    while True:
        if p.is_connected():
            # Short burst of queued notifications.
            if last_btn == btn_val:
                if (last_btn == 0) and (n < 2): # Stop wurde zuletzt uebermittelt
                    jetzt -= 1000
                    n += 1
                if 2000 < ticks_diff (ticks_ms(), jetzt):
                    # Resend alle 2 Sekunden
                    print(f"{last_btn} Button still pressed, connection is: {p}")
                    p.set_navigation(btn_val, notify=True, indicate=False)
                    jetzt = ticks_ms()
            else:
                print(f"{btn_val} Button pressed, connection is: {p}")
                p.set_navigation(btn_val, notify=True, indicate=False)
                last_btn = btn_val
                jetzt = ticks_ms()
                n = 0
        await asyncio.sleep_ms(50)

async def display_task():
    """ Task to update display """
    global D
    while True:
        if D != btn_val:
            display_dir(D)
            #display_text(" S:     " + D + "    ", 1)
            D = str(btn_val)
            #display_text(" S:     " + D + "    ", 1)
            if D == "u":
                display_up()
            if D == "d":
                display_down()
            if D == "l":
                display_left()
            if D == "r":
                display_right()
            if D == "cc":
                display_center()
            if D == "cw":
                display_center()
            if D == "0" and blanka:
                display_text("             ", 1)
        await asyncio.sleep_ms(150)

async def blink_task():
    """ Task to blink LED """
    toggle = True
    while True:
        led.value(toggle)
        toggle = not toggle
        blink = 1000
        if connected:
            blink = 1000
        else:
            blink = 250
        await asyncio.sleep_ms(blink)

async def main():
    tasks = []
    tasks = [asyncio.create_task(remote_task()),
        asyncio.create_task(control_task(_M)),
        asyncio.create_task(blink_task()),
    ]
    if _D:
        tasks.append( asyncio.create_task(display_task()) )
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        print(f"main(): CancelledError {ticks_ms()}")
        reset()        # Workaround for CancelledError = Reboot Pico

asyncio.run(main())
