#/****************************************************************************
# *  PiMowBot-RCjoy                                                          *
# *  ==============                                                          *
# *  Mit Hilfe dieses Mircopython-Skripts für den Raspberry Pi Pico W        *
# *  und eines LCD Display Modul mit SPI-Interface wird eine kleine Fern-    *
# *  bedienung (RemoteControl) für den PiMowBot realisiert, die anstelle     *
# *  des Webbrowsers die Steuerung des PiMowBots ermöglicht.                 *
# *                                                                          *
# *  Achten Sie darauf, dass Sie GND und +3,3V richtig an die Potis an-      *
# *  schließen. Die Werte müssen sich wie im kartesischen Koordinatensystem  *
# *  verhalten. Oben und rechts ansteigend, unten und links fallend.         *
# *                                                                          *
# *  Die Übertragung der Steuerbefehle erfolgt per Websocket an den          *
# *  WebSocket-Server Modul des PiMowBots.                                   *
# *                                                                          *
# *  Es werden folgende Libraries benötigt:                                  *
# *  AsyncWebsocketClient von Vovaman:                                       *
# *     https://github.com/Vovaman/micropython_async_websocket_client        *
# *                                                                          *
# *  Homepage: http://pimowbot.TGD-Consulting.de                             *
# *                                                                          *
# *  Version 0.1.0                                                           *
# *  Datum 23.11.2022                                                        *
# *                                                                          *
# *  (C) 2022 TGD-Consulting , Author: Dirk Weyand                           *
# ****************************************************************************/

from micropython import const
from machine import ADC, Pin, Timer, reset
import network as net
import uasyncio as a
import gc
from ws import AsyncWebsocketClient            # https://github.com/Vovaman/micropython_async_websocket_client
from socket import getaddrinfo
from time import sleep, ticks_ms, ticks_diff
from math import atan2, degrees, sqrt

# WiFi Credentials
_SSID = const('Your_SSID_Name')         # change to your WiFi SSID
_PASSWORD = const('Your_WiFi_Password') # change to your passphrase

# PiMowBot hostname
_HOST = const('pimowbot.local')  # the name of the PiMowBot
_TOKEN = const('12345')          # right Token required look@nohup.out

_SOCKET_DELAY_MS = const(5) # ocket delay ms increase on weak wifi-signal

ADCX = ADC(26)   # GPIO26,Pin#1
ADCY = ADC(27)   # GPIO26,Pin#2
#ADCZ = ADC(28)   # GPIO26,Pin#4

_BTN = const(22)
_NX = const(False)
_NY = const(True) # negiert Y Werte
#_NZ = const(False)

# create instance of websocket client
ws = AsyncWebsocketClient(_SOCKET_DELAY_MS)

led = Pin('LED', Pin.OUT)
timer = Timer()

def blink(timer):
    led.toggle()

S = 200           # Status Code
al = "none"       # alert note
lt = 0            # normal thumbs
w = False         # WebSocket Client
g = False         # all information gathered?
    
def display_text(text):
    print("display not implemented yet: "+text)  

def display_alert(toggle=True):
    print("display not implemented yet: "+al)

def get_request(URL, type="HEAD", format="BIN"):
    rc = False
    try:
        jetzt = ticks_ms()
        if (type == "HEAD"):
            response = urequests.head(URL)
            if (200 == response.status_code):
                rc = True
        else:
            gc.collect()     #Run a garbage collection.
            #print(gc.mem_free())
            #print(gc.mem_alloc())
            response = urequests.get(URL)
            if (format == "BIN"):
                rc = response.content
            else:
                rc = response.text
        S = response.status_code
        print("Delay-" + type + ": " + str(ticks_diff(ticks_ms(), jetzt)) + "ms, Status: " + str(S))
    except:
            rc = False
    return rc

def get_ip(host, port=8080):
    addr_info = getaddrinfo (host, port)
    return addr_info[0][-1][0]

def gathered(IP):
    global g, al
    if not g:
        display_text("    my IP: " + IP)
        timer.deinit() #blinken beenden
        led.off()      #LED ausschalten
        pip = get_ip(_HOST)
        print(f'PiMowBot IP is {pip}')
        sleep(3)  # zum Lesen der IP-Addr der RC auf dem Display
        rc = get_request("http://" + pip + ":8080/favicon.ico")
        if (True == rc):
            print('PiMowBot is ready 4 RC.')
            # now check PiCAM
            pc = get_request("http://" + pip + ":8080/image.jpg")
            print('PiMowBot-PiCAM is ready.')
            # now check large thumb support
            lt = get_request("http://" + pip + ":8080/cgi-bin/xcom.html?Token=" + _TOKEN + "&Thumb=mode", "Get", "TXT")
            if (0 <= lt.find('1')):
                lt = 1
            else:
                lt = 0
                print(f'Large thumb mode "{lt}"')
        else:
            print('PiMowBot is not ready !!!')
            al = "PiMowBot not found"
            display_alert()
        g = True
        return pip
    
async def wlan_connect(SSID: str, pwd: str, attempts: int = 5, delay_in_msec: int = 200) -> net.WLAN:
    global al
    #Connect to WLAN
    wlan = net.WLAN(net.STA_IF)
    wlan.active(1)
    count = 1
    # Wait for connect or fail
    while not wlan.isconnected() and count <= attempts:
        if wlan.status() != net.STAT_CONNECTING:
            wlan.connect(SSID, pwd)
        print('Waiting for connection...')
        await a.sleep_ms(delay_in_msec)
        count += 1

    if wlan.isconnected():
        print("Connected on {}".format(wlan.ifconfig()[0]))
    else:
        al = "WiFi connect failed!!"
        display_alert()

    return wlan

force = 0
angel = 0

def read_analog(ADC):
    val = ADC.read_u16()  # 0 - 65535
    return val
      
def joy(channel): # left right
    val = read_analog(channel)
    val -= 32768
    val /= 28456
    return val
    
def get_joy():
    global angel, force
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
    angel = round(angel, 1)    
    #print("Winkel: ",angel)
    force = round(sqrt((x*x)+(y*y)),2)
    #print("Force: ",force)
    #z = joy(ADCZ)    # rotate cw - ccw
    #    if _NZ:      # Werte z negieren
    #    z = z * -1
    #print("Joy-Z: ",z)

async def do_joy():
    global angel, force, ws
    oforce = 0
    oangel = 0
    omsg = ""
    lmsg = "[0 0]"
    btn_state = False
    btn = Pin(_BTN, Pin.IN, Pin.PULL_UP)
    while True:
        # Button auswerten
        if (btn.value() == 0):
            btn_state = True
        # Joystick auswerten
        get_joy()
        if force > 0.3:
            if ((oforce != min (1, force)) or (abs(oangel - angel) >= 5 )):
                lmsg = "["+str(force)+" "+str(angel)+ "]"
                oforce = min (1, force)
                oangel = angel
        else:
            lmsg = "[0 0]"
            oforce = 0
            oangel = angel
        # neue Steuerungsinformatiomen per senden
        if await ws.open():
            if btn_state:
                lmsg="mower"
                btn_state=False
            if omsg != lmsg:
                print ("Sende Daten per WS: ", lmsg)
                await ws.send(lmsg)
                omsg = lmsg
            gc.collect()
        await a.sleep_ms(300)

async def do_img():
    global ws
    while True:
        if await ws.open():
            print ("Fordere neues Bild per WS an")  # alle 2 Sekunden
            await ws.send("0")
            gc.collect()
        await a.sleep(2)   
    
async def read_ws():
    global ws, w, al
    if hasattr(net, "WLAN"):
        pip = "localhost"
        # Blink onboard LED during connect
        timer.init(freq=4, mode=Timer.PERIODIC, callback=blink)
        # the board has WLAN capabilities
        wifi = await wlan_connect(_SSID, _PASSWORD)
        e =  0
        while e < 50:
            gc.collect()
            if not wifi.isconnected():
                wifi = await wlan_connect(_SSID, _PASSWORD)
                if not wifi.isconnected():
                    continue
            rc = gathered(wifi.ifconfig()[0])
            if wifi.isconnected() and rc:
                pip = rc
                #print(f'PIP {pip}')
            try:
                # connect to PiMowBot socket server with Token
                if not await ws.handshake("ws://" + pip + ":8008/cgi-bin/control.html?token=" + _TOKEN + "&thumb=mode"):
                    w = ws._open
                    print(f'Websocket available {w}')
                    raise Exception('Handshake error.')
                else:
                    print ("WS-Handshake erfolgreich")
                while await ws.open():
                    e = 0
                    w = True
                    gc.collect()
                    data = await ws.recv()
                    if data is not None:
                        print (f'Datenlaenge: {len(data)}')
                        if isinstance(data, bytes):
                            print ('Bytes empfangen')
                            File = open ("image.jpg","wb")
                            File.write(data)
                            File.close()
                        else:
                            print ('String empfangen')
                        # Data Handling demnächst
                    await a.sleep_ms(50)
            except Exception as ex:
                w = False
                e += 1
                print("Exception: {}".format(ex))
                al = " {} ".format(ex)
                display_alert()
                await a.sleep(1)
    else:
        print('Wrong Raspberry Pi Pico')
        print('Raspberry Pi Pico W required')
        al = "  Pico W required  "
        display_alert()
    
async def main():    
    tasks = [read_ws(), do_joy(), do_img()]
    await a.gather(*tasks)

a.run(main())
#EOF
