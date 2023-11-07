#/*****************************************************************************
# *  PiMowBot-RC_BLE                                                          *
# *  ===============                                                          *
# *  Mit Hilfe dieses Mircopython-Skripts für den Raspberry Pi Pico W und     *
# *  eines LCD Display Moduls (Pico-LCD_1.14 Zoll von Waveshare oder rundes   *
# *  SPI LCD 1.28" Display Modul 240x240 mit GC9A01 Treiber) wird eine kleine *
# *  smarte RemoteControl für den PiMowBot realisiert, die anstelle des       *
# *  Webbrowsers die Steuerung des PiMowBots ermöglicht.                      *
# *                                                                           *
# *  Achten Sie beim analogen Joystick darauf, dass Sie GND und +3,3V richtig *
# *  an die Potis anschließen. Die Werte müssen sich wie im kartesischen      *
# *  Koordinatensystem verhalten. Oben und rechts ansteigend, unten und links *
# *  fallend.                                                                 *
# *                                                                           *
# *  Die Übertragung der Steuerbefehle erfolgt per BLE an den PiMowBot.       *
# *  (Repository: https://github.com/micropython/micropython/tree/master/     *
# *               examples/bluetooth)                                         *
# *                                                                           *
# *  Homepage: http://pimowbot.TGD-Consulting.de                              *
# *                                                                           *
# *  Version 0.1.2                                                            *
# *  Datum 13.09.2023                                                         *
# *                                                                           *
# *  (C) 2023 TGD-Consulting , Author: Dirk Weyand                            *
# *****************************************************************************/

import sys
import bluetooth
import struct
import gc
import uasyncio as asyncio
from micropython import const
from machine import Pin, Timer, ADC
from os import stat, rename
from time import sleep, ticks_ms, ticks_diff, localtime
from math import atan2, degrees, sqrt, cos, sin, pi

_M = const(1)       # Mode, change to 0 if analogue joystick is not used
_D = const(True)    # Change to False if display isn't connected to the PicoW
_WD = const(0)      # set to 1, if Waveshare-Display Pico-LCD_1.14 is used instead of GC9A01
_BTA = const(1)     # Darstellung der Steuerbutton, set to 0 to disable
_FB = const (0)     # Set to 1 to enable FastBoot
_DB = const(False)  # Change to True to enable debug info
_LOG = const(False) # Set to True to enable logging to flash, Set to None to disable

# dormant mode 
_DP1 = const(15)    # btn_a
_DP2 = const(17)    # btn_b

_OX = const(99)     # Offset X Steuerknüppel
_OY = const(80)     # Offset Y Steuerknüppel

if _D:
    if _WD:
        import jpegdec
        # Joystick and buttons
        joy_l = Pin(16, Pin.IN, Pin.PULL_UP) # left
        joy_r = Pin(20, Pin.IN, Pin.PULL_UP) # right
        joy_u = Pin(2, Pin.IN, Pin.PULL_UP)  # up
        joy_d = Pin(18, Pin.IN, Pin.PULL_UP) # down
        joy_c = Pin(3, Pin.IN, Pin.PULL_UP)  # center
        btn_a = Pin(_DP1, Pin.IN, Pin.PULL_UP)
        btn_b = Pin(_DP2, Pin.IN, Pin.PULL_UP)
        _LOGO = "Logo.jpg"
    else:
        import gc9a01
        import vga1_8x16 as font
        import vga2_8x8 as font2
        from machine import SPI
        #/*************************
        # *** Display Parameter ***
        # *************************/
        _BLK = const(10)  # GPIO10, Pin#14, BLK
        _RST = const(11)  # GPIO11, Pin#15, RES
        _DC = const(12)   # GPIO12, Pin#16,  DC
        _CS = const(13)   # GPIO13, Pin#17,  CS
                          #    GND, Pin#18, GND
        _SCL = const(14)  # GPIO14, Pin#19  SCL
        _SDA = const(15)  # GPIO15, Pin#20  SDA
        _LOGO = "Logo240.jpg"

D = "unknown"    # current direction
last_btn = 0     # last button value
btn_val = 0      # current button

if _M:
    _BTN = 22 # GPIO22, Pin#29
elif _WD:
    _BTN = 3  # Joy center-btn of Waveshare display
    
led = Pin("LED", Pin.OUT)
timer = Timer()

def blink(timer):
    led.toggle()

def shour(ts=localtime()):
    return '{:0>2}'.format(ts[3])+":"+'{:0>2}'.format(ts[4])+":"+'{:0>2}'.format(ts[5])
    
def sdate(ts=localtime()):
    return '{:0>2}'.format(ts[2])+"."+'{:0>2}'.format(ts[1])+"."+str(ts[0])

def exists(file="main.py"):
    try:
        stat(file)
        return True
    except OSError:
        return False
    
def log(msg):
    if _LOG is not None:
        if _LOG:
            if exists("myLog.txt") and 43008 > stat("myLog.txt")[6]:
                lfile=open("myLog.txt","a")
            else:
                lfile=open("myLog.txt","w")    # overwrite if log > 42k
            lfile.write(sdate()+" "+shour(localtime())+' '+ str(msg) +'\n')
            lfile.close()
        else:
            print(msg)

def do_rmp():
    if exists():
        log("INFO: benenne main.py in main_.py um")
        rename("main.py","main_.py")
        reset()
        return True
    else:
        log("INFO: keine main.py vorhanden")
        return False
    
def restore(abtn=_BTN):
    a = Pin(abtn, Pin.IN, Pin.PULL_UP)
    b = 0
    t = 0
    start=ticks_ms()
    while ticks_ms()-start <=5000:
        if a.value()==0:
            b += 1
        if a.value()==1 and b > 0:
            t += 1
            b = 0
        if t > 1:
            if do_rmp():
                break
            else:
                t = 0
        sleep(0.1)

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
_IRQ_GATTS_WRITE = const(3)
_IRQ_GATTS_INDICATE_DONE = const(20)

_FLAG_READ = const(0x0002)
_FLAG_WRITE_NO_RESPONSE = const(0x0004)
_FLAG_WRITE = const(0x0008)
_FLAG_NOTIFY = const(0x0010)
_FLAG_INDICATE = const(0x0020)

#BLE-Device Services and Characteristics
_RC_TELE_UUID = bluetooth.UUID(0x1801) # Generic Attribute

_TELE_CHAR = (bluetooth.UUID(0x2700), _FLAG_WRITE | _FLAG_WRITE_NO_RESPONSE, )   # unitless

_RC_TELE_SERVICE = (_RC_TELE_UUID, (_TELE_CHAR,),)

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
        ((self._handle,), (self._handle_tele,), (i1, i2, i3, i4, i5,),) = self._ble.gatts_register_services((_RC_NAV_SERVICE, _RC_TELE_SERVICE, _DEV_INFO_SERVICE,))
        self._connections = set()
        self._write_callback = None
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
            log("New connection from " + str(addr))
            connected = True
            timer.deinit() #blinken beenden
            led.off()      #LED ausschalten
            if _D:
                display_BTlogo()
            self._connections.add(conn_handle)
        elif event == _IRQ_CENTRAL_DISCONNECT:
            conn_handle, _, addr = data
            log("Disconnected " + str(addr))
            self._connections.remove(conn_handle)
            connected = False
            # Blink onboard LED during connect
            timer.init(freq=4, mode=Timer.PERIODIC, callback=blink)
            if _D:
                display_image(_LOGO)
            # Start advertising again to allow a new connection.
            self._advertise()
        elif event == _IRQ_GATTS_INDICATE_DONE:
            conn_handle, value_handle, status = data
        elif event == _IRQ_GATTS_WRITE:
            conn_handle, value_handle = data
            value = self._ble.gatts_read(value_handle)
            if value_handle == self._handle_tele and self._write_callback:
                self._write_callback(value)

    def is_connected(self):
        return len(self._connections) > 0
    
    def on_write(self, callback):
        self._write_callback = callback
    
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
        log("Starting advertising")
        self._ble.gap_advertise(interval_us, adv_data=self._payload)

#/***********************
# *** Display Helpers ***
# ***********************/

def reset_display():
    if _WD:
        rst = Pin(12,Pin.OUT)
        rst.on()
        rst.off()
        rst.on()
    else:   # enable display and clear screen
        display.init()
        display.fill(0) # clear (fill with black) 

def display_blank():
    if _WD:
        BLACK = display.create_pen(0, 0, 0)
        display.set_pen(BLACK)
        display.clear()
        display.set_backlight(0.0)
        display.update()
    else:
        display.fill(0)
        display.off()

def display_col(R=90, G=220, B=240):
    if _WD:
        COL = display.create_pen(R, G, B)
        display.set_pen(COL)
        display.clear()
        display.update()
    else:
        display.fill(gc9a01.color565(R, G, B))
    
def display_image(file='image.jpg', x=0, y=0):
    if _WD:
        # Create a new JPEG decoder for our PicoGraphics
        j = jpegdec.JPEG(display)
     
        # Open the JPEG file
        j.open_file(file)
        # Decode the JPEG
        j.decode(x, y, jpegdec.JPEG_SCALE_FULL)
     
        # Display the result
        display.update()
    else:
        display.jpg(file, x, y, gc9a01.SLOW)
    gc.collect()
    

def display_compass(alpha=0, set=True):
    deg = (alpha * -1) + 270 # Korrektur Kompass-Rose 0=N -> Einheitskreis 90=N
    rad = (pi * deg) / 180   # Grad nach Bogenmaß
    x = cos(rad)
    y = sin(rad)
    if set:
        display.fill_rect(117 + int(115 * x), 117 + int(115 * y), 7, 7, RED)
    else:
        display.fill_rect(117 + int(115 * x), 117 + int(115 * y), 7, 7, BACK)

oa = 0
def display_Heading(val="10.8"):
    global oa
    if _WD:
        log("Heading: "+val)
    else:
        display_compass(float(oa), 0)
        display_compass(float(val))
        oa = val
    
def display_Battery(val="10.8"):
    if _WD:
        display.set_pen(BACK)
        display.rectangle(33, 67, 39, 16) # Battery
        display.rectangle(28, 71, 3, 8)   # +Knob
        display.set_pen(DGREY)
        display.pixel(28,71)  # round corners knob
        display.pixel(28,78)
        display.pixel(33,67)  # round corners battery
        display.pixel(33,82)
        display.pixel(71,67)
        display.pixel(71,82)
        display.set_pen(GREY)
        display.set_font('bitmap8')
        display.text(val, 36, 68, scale=2) # show text
        display.update()
    else:
        display.fill_rect(33, 116, 39, 16, BACK) # Battery
        display.fill_rect(28, 120, 3, 8, BACK) # +Knob
        display.pixel(28, 120, DGREY)  # round corners knob
        display.pixel(28, 127, DGREY)
        display.pixel(33, 116, DGREY)  # round corners battery
        display.pixel(33, 131, DGREY)
        display.pixel(71, 116, DGREY)
        display.pixel(71, 131, DGREY)
        display.text(font,val,36,117, GREY, BACK)
    
def display_BTlogo():
    if _WD:
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
    else:
        x = 116
        y = 76
        display.line(x + 8, y, x, y - 5, DGREY) #left
        display.line(x + 8, y, x, y + 5, DGREY)
        display.line(x + 7, y, x, y - 4, DGREY)
        display.line(x + 7, y, x, y + 4, DGREY)
        display.vline(x, y - 5, 11, BACK)       #left blank
        display.vline(x + 1, y - 5, 11, BACK)
        x = 125
        y = 72
        display.line(x + 8, y, x, y - 5, DGREY) #right
        display.line(x + 8, y, x, y + 5, DGREY)
        display.line(x + 7, y, x, y - 4, DGREY)
        display.line(x + 7, y, x, y + 4, DGREY)
        x = 125
        y = 80
        display.line(x + 8, y, x, y - 5, DGREY) #right
        display.line(x + 8, y, x, y + 5, DGREY)
        display.line(x + 7, y, x, y - 4, DGREY)
        display.line(x + 7, y, x, y + 4, DGREY)

def display_text(text, dir = 0):
    if _WD:
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
    else:
        if dir:
            display.fill_rect(133, 55, 102, 17, BACK)
            display.text(font,text,133,55, GREY, BACK)
        else:
            display.fill_rect(2, 155, 236, 20, BACK)
            display.text(font,text,2,155, GREY, BACK)

def display_alert(toggle=True):
    if _WD:
        display.set_pen(BACK)
        display.rectangle(2, 105, 236, 20) # remove lawn on display
        if toggle:
            display.set_pen(GREY)
        else:
            display.set_pen(RED)
        display.set_font('bitmap8')
        display.text(" >> " + al + " << ", 2, 105, 236, 2)
        display.update()
    else:
        display.fill_rect(2, 155, 236, 20, BACK)
        if toggle:
            display.text(font," >> " + al + " << ",2,155, GREY, BACK)
        else:
            display.text(font," >> " + al + " << ",2,155, RED, BACK)

def display_up(set=True):
    if _BTA:
        if _WD:
            if set:
                display.set_pen(RED)
            else:
                display.set_pen(DGREY)
            display.triangle(_OX, _OY - 18, _OX - 10, _OY - 10, _OX + 10, _OY - 10) #up
            display.update()
        else:
            if set:
                display.text(font2,30,96,113, RED, DGREY)
            else:
                display.text(font2,30,96,113, DGREY, DGREY)

    
def display_down(set=True):
    if _BTA:
        if _WD:
            if set:
                display.set_pen(RED)
            else:
                display.set_pen(DGREY)
            display.triangle(_OX, _OY + 18, _OX + 10, _OY + 10, _OX - 10, _OY + 10) #down
            display.update()
        else:
            if set:
                display.text(font2,31,96,142, RED, DGREY)
            else:
                display.text(font2,31,96,142, DGREY, DGREY)

 
def display_left(set=True):
    if _BTA:
        if _WD:
            if set:
                display.set_pen(RED)
            else:
                display.set_pen(DGREY)
            display.triangle(_OX - 18, _OY, _OX - 10, _OY - 10, _OX - 10, _OY + 10) #left
            display.update()
        else:
            if set:
                display.text(font2,17,82,127, RED, DGREY)
            else:
                display.text(font2,17,82,127, DGREY, DGREY)

def display_right(set=True):
    if _BTA:
        if _WD:
            if set:
                display.set_pen(RED)
            else:
                display.set_pen(DGREY)
            display.triangle(_OX + 18, _OY, _OX + 10, _OY - 10, _OX + 10, _OY + 10) #right
            display.update()
        else:
            if set:
                display.text(font2,16,111,127, RED, DGREY)
            else:
                display.text(font2,16,111,127, DGREY, DGREY)

def display_center(set=True):
    if _BTA:
        if _WD:
            if set:
                display.set_pen(RED)
            else:
                display.set_pen(GREY)
            display.circle(_OX, _OY, 5)      # Center btn
            display.update()
        else:
            if set:
                display.text(font2,219,96,127, RED, GREY)
            else:
                display.text(font2,219,96,127, GREY, GREY)

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
if _D:        
    # Init Display
    if _WD:
        from pimoroni_bus import SPIBus
        from picographics import PicoGraphics, DISPLAY_PICO_DISPLAY, PEN_RGB565
        reset_display()
        spibus = SPIBus(cs=9, dc=8, sck=10, mosi=11, bl=13)
        display = PicoGraphics(display=DISPLAY_PICO_DISPLAY, bus=spibus, pen_type= PEN_RGB565, rotate=0)
        BACK = display.create_pen(90, 220, 240)
        DGREY = display.create_pen(80, 80, 80)
        GREY = display.create_pen(132, 132, 132)
        RED = display.create_pen(250, 132, 132)
        display.set_backlight(0.7)
    else:
        spi = SPI(1, baudrate=60000000, sck=Pin(_SCL), mosi=Pin(_SDA))
        display = gc9a01.GC9A01(
            spi,
            240,
            240,
            reset=Pin(_RST, Pin.OUT),
            cs=Pin(_CS, Pin.OUT),
            dc=Pin(_DC, Pin.OUT),
            backlight=Pin(_BLK, Pin.OUT),
            rotation=2) # 180Grad
        reset_display()
        BACK = gc9a01.color565(90, 220, 240)
        DGREY = gc9a01.color565(80, 80, 80)
        GREY = gc9a01.color565(132, 132, 132)
        RED = gc9a01.color565(250, 132, 132)
 
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
        log("Aktion: " + _AB[ai])

if _M:
    #/**************************
    # *** Joystick Parameter ***
    # **************************/
    
    ADCX = ADC(26)   # GPIO26, Pin#31
    ADCY = ADC(27)   # GPIO27, Pin#32
    ADCZ = ADC(28)   # GPIO28,Pin#34
    
    _NX = const(False)
    _NY = const(False) # True negiert Y Werte
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
            if btn_val == "0" and _WD:       # Button a or b bei Waveshare-Display
                if 0 == btn_a.value():
                     btn_val = _AKTION[ai]   # toggle/do aktion
                elif 0 == btn_b.value():
                    n += 1
                    if n > 1:
                        n = 0
                        change_aktion()
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
                n += 1
                if n > 1:
                    n = 0
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

    def do_tele(v):
        t = v.decode("utf-8").split()
        if t[0] == 'b':
            display_Battery(t[1])
        elif t[0] == 'h':
            display_Heading(t[1])
        else:
            pass #TBD

    p.on_write(do_tele)

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

async def main():
    log("INFO: >> RControl-BLE powered up <<")
    
    # Blink onboard LED slowly during restore
    timer.init(freq=2, mode=Timer.PERIODIC, callback=blink)
    # Check 4 Restore
    log("Waiting 5s 4 doubleclick 2 restore")
    restore()
    timer.deinit() #blinken beenden
    led.off()      #LED ausschalten
    
    tasks = []
    if _D:
        tasks.append( asyncio.create_task(display_task()) )
        if _FB:
            display_col()
        else:   # Show Logo
            display_image(_LOGO)
            #display_Battery()
            #display_BTlogo()
            #display_Heading(120)
    
    if _BTA:
        display_dir()            # kurze Vorstellung der Steuerung
        
    # Blink onboard LED during connect
    timer.init(freq=4, mode=Timer.PERIODIC, callback=blink)
    
    tasks.append( asyncio.create_task(control_task(_M)) )
    tasks.append( asyncio.create_task(remote_task()) )
    
    if _DB:
        log("INFO: Tasks ("+str(len(tasks))+")")
    await asyncio.gather(*tasks)

asyncio.run(main())
