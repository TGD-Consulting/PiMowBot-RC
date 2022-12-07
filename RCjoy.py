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
# *  Version 0.1.4                                                           *
# *  Datum 07.12.2022                                                        *
# *                                                                          *
# *  (C) 2022 TGD-Consulting , Author: Dirk Weyand                           *
# ****************************************************************************/

from micropython import const
from machine import ADC, Pin, SPI, Timer, RTC, reset
import network as net
import uasyncio as a
import urequests as r
import gc
import gc9a01
from os import stat, rename
from ws import AsyncWebsocketClient            # https://github.com/Vovaman/micropython_async_websocket_client
from socket import getaddrinfo
from time import sleep, ticks_ms, ticks_diff, localtime
from math import atan2, degrees, sqrt

#/*************************
# *** Globale Parameter ***
# *************************/

# WiFi Credentials
_SSID = const('Your_SSID_Name')         # change to your WiFi SSID
_PASSWORD = const('Your_WiFi_Password') # change to your passphrase

# PiMowBot hostname
_HOST = const('pimowbot.local')  # the name of the PiMowBot
_TOKEN = const('12345')          # right Token required look@nohup.out

_LOG = const(False)              # Set to True to enable logging to flash
_SOCKET_DELAY_MS = const(5)      # Socket delay ms, increase on weak wifi-signal
_RDELAY = const(10 * _SOCKET_DELAY_MS)

ADCX = ADC(26)   # GPIO26, Pin#31
ADCY = ADC(27)   # GPIO27, Pin#32
#ADCZ = ADC(28)   # GPIO28,Pin#34

_BTN = const(22) # GPIO22, Pin#29
_NX = const(False)
_NY = const(True) # negiert Y Werte
#_NZ = const(False)

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
q = []            # empty queue, contains payload send via ws, init stop
na = False        # bei True ist acknowledge erforderlich
ec = 0            # error counter

def log(msg):
    if _LOG:
        lfile=open("myLog.txt","a")
        ts = localtime()  #(2022, 12, 7, 17, 58, 54, 2, 341)
        lfile.write(str(ts[2])+'.'+str(ts[1])+'.'+str(ts[0])+' '+str(ts[3])+':'+str(ts[4])+':'++str(ts[5])+' '+ str(msg) +'\n')
        lfile.close()
    else:
        print(msg)
        
def do_rmp():
    try:
        stat("main.py")
        log("INFO: benenne main.py in main_.py um")
        rename("main.py","main_.py")
        reset()
        return True
    except OSError:
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

def reset_display():
    # enable display and clear screen
    display.init()
    
def display_text(text):
    print("display not implemented yet: "+text)  

def display_alert(toggle=True):
    print("display not implemented yet: "+al)

def display_image(file="image.jpg", x=0, y=0):
    log("Display image: " + file)
    #display.jpg(file, x, y, gc9a01.FAST)
    display.jpg(file, x, y, gc9a01.SLOW)
    gc.collect()     #Run a garbage collection.

def set_rtc(timestamp):
    import ujson
    i=ujson.loads('{"Jan":"01","Feb":"02","Mar":"03","Apr":"04","May":"05","Jun":"06","Jul":"07","Aug":"08","Sep":"09","Oct":"10","Nov":"11","Dec":"12"}')
    w=ujson.loads('{"Mon,":"0","Tue,":"1","Wed,":"2","Thu,":"3","Fri,":"4","Sat,":"5","Sun,":"6"}')
    ts=timestamp # "Wed, 07 Feb 2022 10:06:56 GMT"
    el=ts.split(" ")
    wd=w[el[0]]
    d=el[1]
    m=i[el[2]]
    y=el[3]
    zeit=el[4]
    h=zeit.split(":")[0]
    M=zeit.split(":")[1]
    s=zeit.split(":")[2]
    #print(int(y),int(m),int(d),int(h),int(M),int(s))
    RTC().datetime((int(y), int(m), int(d), int(wd), int(h), int(M), int(s), 0))
    log("INFO: Zeit erfolgreich gesetzt ("+timestamp+')')
    return True

def get_request(URL, type="HEAD", format="BIN"):
    rc = False
    try:
        jetzt = ticks_ms()
        if (type == "HEAD"):
            response = r.head(URL)
            if (200 == response.status_code):
                rc = True
        else:
            if (type == "TIME"):
                response = r.head(URL)
                if 200 == response.status_code and set_rtc(response.headers['Date']):
                    rc = True
            else:
                gc.collect()     #Run a garbage collection.
                response = r.get(URL)
                if (format == "BIN"):
                    rc = response.content
                else:
                    rc = response.text
        S = response.status_code
        log("Delay-" + type + ": " + str(ticks_diff(ticks_ms(), jetzt)) + "ms, Status: " + str(S))
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
        rc = get_request("http://" + pip + ":8080/favicon.ico", "TIME")
        if (True == rc):
            print('PiMowBot is ready 4 RC.')
            # now check PiCAM
            pc = get_request("http://" + pip + ":8080/image.jpg")
            print('PiMowBot-PiCAM is ready.')
            # now check large thumb support
            lt = get_request("http://" + pip + ":8080/cgi-bin/xcom.html?Token=" + _TOKEN + "&Thumb=mode", "Get", "TXT")
            if lt:
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
    global angel, force, ws, q, ec, na
    oforce = 0
    oangel = 0
    omsg = ""
    lmsg = "[0 0]"
    btn_state = False
    btn = Pin(_BTN, Pin.IN, Pin.PULL_UP)
    t = ticks_ms()
    while True:
        if ticks_diff(ticks_ms(), t) > 290:
            t = ticks_ms()
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
            # neue Steuerungsinformatiomen an queue senden
            if btn_state:
                lmsg="mower"
                btn_state=False
            if omsg != lmsg:
                #print ("Sende Daten an WS-queue: " + lmsg + " (" +str(ticks_ms())+ ")")
                if q:
                    q[0] = lmsg
                    #if '0' == q[0]:
                    #    q[0] = lmsg
                    #    q.append('0')
                    #else:
                    #    q[0] = lmsg
                else:
                    q.append(lmsg)
                omsg = lmsg
        if q and await ws.open(): # send first WS message
            if len(q) > 5 or ec > 5:
                await ws.open(False)
                ec = 0
            else:
                cmd = q[0]
                print ("Sende Daten an WS: " + cmd + " (" +str(ticks_ms())+ ")")
                await ws.send(cmd)
                if cmd.find("[") == 0:
                    na = cmd
                    ec += 1
                else:
                    ec = 0
                    q.pop(0)
                gc.collect()
        await a.sleep_ms(150)

async def do_img():
    global q, w
    last = ticks_ms()
    while True:
        if w and ticks_diff(ticks_ms(), last) > 1900:
            if not '0' in q:
                last = ticks_ms()
                #print ("Fordere neues Bild per Queue an ("+str(last)+")")
                q.append("0")
        await a.sleep(0.5)   
            
async def conn_ws():
    global ws, w, al, q, na, ec
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
                    w = ws._open
                    print(f'Websocket available {w}')
                while await ws.open():
                    e = 0
                    gc.collect()
                    data = await ws.recv()
                    if data is not None:
                        if isinstance(data, bytes):
                            log (str(len(data)) + ' Bytes empfangen (' +str(ticks_ms()) +')')
                            File = open ("image.jpg","wb")
                            File.write(data)
                            File.close()
                        else:
                            log ('String mit '+str(len(data))+' Zeichen empfangen ('+str(ticks_ms())+')')
                            if data == '':
                                if q and na:
                                    print ('Quittiert', q.pop(0))
                                    na = False
                                    ec = 0
                            else:
                                if q and na == data: # Steuerungsbefehl wird so lange gesendet bis Quittung empfangen
                                    #q.pop(0)
                                    print ('Quittiert', q.pop(0))
                                    na = False
                                    ec = 0
                    await a.sleep_ms(_RDELAY)
            except Exception as ex:
                gc.collect()
                w = False
                e += 1
                print("Exception: {}".format(ex))
                al = " {} ".format(ex)
                display_alert()
                await a.sleep(1)
    else:
        log('Wrong Raspberry Pi Pico')
        log('Raspberry Pi Pico W required')
        al = "  Pico W required  "
        display_alert()
    
async def main():
    # Blink onboard LED slowly during restore-phase
    timer.init(freq=2, mode=Timer.PERIODIC, callback=blink)
    # Check 4 Restore
    restore()
    # Init Display
    reset_display()
    # Show Logo
    display_image("Logo240.jpg")
    tasks = [conn_ws(), do_joy(), do_img()]
    await a.gather(*tasks)

a.run(main())
#EOF
