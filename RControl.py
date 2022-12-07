#/****************************************************************************
# *  PiMowBot-RC                                                             *
# *  ===========                                                             *
# *  Mit Hilfe dieses Mircopython-Skripts für den Raspberry Pi Pico W und    *
# *  eines Pico-LCD_1.14 Zoll LCD Display Modul von Waveshare wird eine      *
# *  kleine RemoteControl für den PiMowBot realisiert, die anstelle des      *
# *  Webbrowsers die Steuerung des PiMowBots ermöglicht.                     *
# *                                                                          *
# *  Die Übertragung der Steuerbefehle erfolgt per HTTP Request an das       *
# *  Webserver Modul des PiMowBots.                                          *
# *                                                                          *
# *  Homepage: http://pimowbot.TGD-Consulting.de                             *
# *                                                                          *
# *  Version 0.1.2                                                           *
# *  Datum 07.12.2022                                                        *
# *                                                                          *
# *  (C) 2022 TGD-Consulting , Author: Dirk Weyand                           *
# ****************************************************************************/

from micropython import const
from pimoroni_bus import SPIBus
from picographics import PicoGraphics, DISPLAY_PICO_DISPLAY, PEN_RGB565
import jpegdec
import network
import uasyncio
import urequests
import gc
from os import stat, rename
from socket import getaddrinfo
from time import sleep, ticks_ms, ticks_diff #time
from machine import Pin, Timer, reset
#import lowpower   # https://github.com/tomjorquera/pico-micropython-lowpower-workaround

#/*************************
# *** Globale Parameter ***
# *************************/

# WiFi Credentials
_SSID = const('Your_SSID_Name')         # change to your WiFi SSID
_PASSWORD = const('Your_WiFi_Password') # change to your passphrase

# PiMowBot hostname
_HOST = const('pimowbot.local')  # the name of the PiMowBot 
_TOKEN = const('12345')          # right Token required look@nohup.out

# dormant mode 
_DP1 = const(15)    # btna
_DP2 = const(17)    # btnb

_OX = const(99)     # Offset X Steuerknüppel
_OY = const(80)     # Offset Y Steuerknüppel

# Joystick and buttons
joy_l = Pin(16, Pin.IN, Pin.PULL_UP)
joy_r = Pin(20, Pin.IN, Pin.PULL_UP)
joy_u = Pin(2, Pin.IN, Pin.PULL_UP)
joy_d = Pin(18, Pin.IN, Pin.PULL_UP)
joy_c = Pin(3, Pin.IN, Pin.PULL_UP)
btnA = Pin(_DP1, Pin.IN, Pin.PULL_UP)
btnB = Pin(_DP2, Pin.IN, Pin.PULL_UP)

led = Pin('LED', Pin.OUT)
timer = Timer()

def blink(timer):
    led.toggle()

D = "unknown"    # current direction
S = 200          # Status Code
a = "none"       # alert note
lt = 0           # normal thumbs
bta = 1          # Darstellung der Steuerbutton

def log(msg):
    if _LOG:
        lfile=open("myLog.txt","a")
        lfile.write('{'+ str(msg) +'},'+'\n')
        lfile.close()
    else:
        print(msg)
        
def do_rmp():
    try:
        stat("main.py")
        log("Info: benenne main.py in main_.py um")
        rename("main.py","main_.py")
        reset()
        return True
    except OSError:
        log("INFO: keine main.py vorhanden")
        return False

def restore(abtn=3):
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

def motor_stop():
    global D
    if (D != "Stop"):
        display_dir(D)
        D = "Stop"
        print (D)
        get_request("http://" + pip + ":8080/cgi-bin/control.html?Token=" + _TOKEN + "&name=motor&state=OFF")

def move_forward():
    global D
    if (D != "Forward"):
        display_dir(D)
        D = "Forward"
        print (D)
        display_up()
        get_request("http://" + pip + ":8080/cgi-bin/control.html?Token=" + _TOKEN + "&name=forward&state=ON")
 
def move_backward():
    global D
    if (D != "Backward"):
        display_dir(D)
        D = "Backward"
        print (D)
        display_down()
        get_request("http://" + pip + ":8080/cgi-bin/control.html?Token=" + _TOKEN + "&name=back&state=ON")
    
def move_left():
    global D
    if (D != "Left"):
        display_dir(D)
        D = "Left"
        print (D)
        display_left()
        get_request("http://" + pip + ":8080/cgi-bin/control.html?Token=" + _TOKEN + "&name=left&state=ON")
    
def move_right():
    global D
    if (D != "Right"):
        display_dir(D)
        D = "Right"
        print (D)
        display_right()
        get_request("http://" + pip + ":8080/cgi-bin/control.html?Token=" + _TOKEN + "&name=right&state=ON")

def turn(n):
    global D
    print (f'Turn {n}')
    if (D != "Turn"):
        display_dir(D)
        D = "Turn"
        display_center()
        if (n <= 1) or (n == 4) or (n == 5) or (n == 10):
            print ("Turn CW")
            get_request("http://" + pip + ":8080/cgi-bin/control.html?Token=" + _TOKEN + "&name=turn_right&state=ON")
        else:
            print ("Turn CCW")
            get_request("http://" + pip + ":8080/cgi-bin/control.html?Token=" + _TOKEN + "&name=turn_left&state=ON")

def drift_left (dir):
    global D
    if (D != "dLeft"):
        display_dir(D)
        D = "dLeft"
        if (dir == 1):
            display_dleft()
            print ("Drift Left Forward")
        else:
            display_dleftb()
            print ("Drift Left Backwards")

def drift_right (dir):
    global D
    if (D != "dRight"):
        display_dir(D)
        D = "dRight"
        if (dir == 1):
            display_dright()
            print ("Drift Right Forward") 
        else:
            display_drightb()
            print ("Drift Right Backwards")

def do_shutdown():
    print ("Shutdown in Progress")   #PiMowBot herunterfahren
    motor_stop()
    display.set_backlight(0)
    #lowpower.dormant_until_pins([_DP1, _DP2])
    print ("RC WakeUp in Progress")  #PiMowBot RC wiederbeleben
    display.set_backlight(0.7)
    #reset()

def toggle_mower():                  #Mähmotor an/aus
    print ("Mowing On/Off") 
    get_request("http://" + pip + ":8080/cgi-bin/control.html?Token=" + _TOKEN + "&mower=%E2%9C%87")

def do_special():                    #Fahrtenschreiber an/aus geht nur per Websocket
    print ("Blackbox On/Off") 

def do_notaus():                     #NotAus Wird bei btn und Steuerkreuz aktiviert 
    print ("NotAus")
    get_request("http://" + pip + ":8080/cgi-bin/control.html?Token=" + _TOKEN + "&motor=%E2%8A%97")

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

def display_cinema():
    #remove RC from Background
    BACK = display.create_pen(90, 220, 240)
    display.set_clip(140,20,90,80)
    display.set_pen(BACK)
    display.clear()
    display.update()
    display.remove_clip()
    #add cinema frame
    GREY = display.create_pen(132, 132, 132)
    display.set_clip(143,33,80,45)
    display.set_pen(GREY)
    display.clear()
    display.update()
    display.remove_clip()

def display_up(set=True):
    if (bta == 1):
        if set:
            RED = display.create_pen(250, 132, 132)
            display.set_pen(RED)
        else:
            DGREY = display.create_pen(80, 80, 80)
            display.set_pen(DGREY)
        display.triangle(_OX, _OY - 18, _OX - 10, _OY - 10, _OX + 10, _OY - 10) #up
        display.update()
    
def display_down(set=True):
    if (bta == 1):
        if set:
            RED = display.create_pen(250, 132, 132)
            display.set_pen(RED)
        else:
            DGREY = display.create_pen(80, 80, 80)
            display.set_pen(DGREY)
        display.triangle(_OX, _OY + 18, _OX + 10, _OY + 10, _OX - 10, _OY + 10) #down
        display.update()
 
def display_left(set=True):
    if (bta == 1):
        if set:
            RED = display.create_pen(250, 132, 132)
            display.set_pen(RED)
        else:
            DGREY = display.create_pen(80, 80, 80)
            display.set_pen(DGREY)
        display.triangle(_OX - 18, _OY, _OX - 10, _OY - 10, _OX - 10, _OY + 10) #left
        display.update()        

def display_right(set=True):
    if (bta == 1):
        if set:
            RED = display.create_pen(250, 132, 132)
            display.set_pen(RED)
        else:
            DGREY = display.create_pen(80, 80, 80)
            display.set_pen(DGREY)
        display.triangle(_OX + 18, _OY, _OX + 10, _OY - 10, _OX + 10, _OY + 10) #right
        display.update()

def display_center(set=True):
    if (bta == 1):
        if set:
            RED = display.create_pen(250, 132, 132)
            display.set_pen(RED)
        else:
            GREY = display.create_pen(132, 132, 132)
            display.set_pen(GREY)
        display.circle(_OX, _OY, 5)      # Center btn
        display.update()

def display_dleft(set=True):
     if set:
        display_up()
        display_left()
     else:
        display_up(0)
        display_left(0)

def display_dleftb(set=True):
    if set:
        display_down()
        display_left()
    else:
        display_down(0)
        display_left(0)

def display_dright(set=True):
    if set:
        display_up()
        display_right()
    else:
        display_up(0)
        display_right(0)

def display_drightb(set=True):
    if set:
        display_down()
        display_right()
    else:
        display_down(0)
        display_right(0)
        
def display_dir(odir="Init"):
    if (odir == "Forward"):
        display_up(0)
    if (odir == "Backward"):
        display_down(0)
    if (odir == "Left"):
        display_left(0)
    if (odir == "Right"):
        display_right(0)
    if (odir == "Turn"):
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

def display_text(text):
    GREY = display.create_pen(132, 132, 132)
    RED = display.create_pen(250, 132, 132)
    BACK = display.create_pen(90, 220, 240)
    display.set_pen(BACK)
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
    display.text(" >> " + a + " << ", 2, 105, 236, 2)
    display.update()
    
def display_image(file='image.jpg', x=0, y=0):    
    # Create a new JPEG decoder for our PicoGraphics
    j = jpegdec.JPEG(display)
     
    # Open the JPEG file
    j.open_file(file)
    # Decode the JPEG
    j.decode(x, y, jpegdec.JPEG_SCALE_FULL)
     
    # Display the result
    display.update()

async def refresh_display():
    global a
    ts = 0
    n = 0
    i = 0
    while True:
       ts += 1
       # Load current PiCAM image and display
       if (n == 1) and (ts == 2):
           if (a != "none"):
               display_alert()
       if ts >= 4:
           ts = 0
           image = get_request("http://" + pip + ":8080/cgi-bin/xcom.html?Token=" + _TOKEN + "&Thumb=image.jpg", "Get")
           if S != 200:
               a = "PiMowBot returned " + str(S) + "!"
           if (image == False) or (S != 200):
               if (a != "none"):
                   display_alert(False)
               n = 1
               i += 1
               if i >= 21:
                   display_blank()
                   reset() # Pico neu starten
           else:
               File = open ("image.jpg","wb")
               File.write(image)
               File.close()
               if (lt == 1):
                   display_image("image.jpg",0,0)
               else:
                   display_image("image.jpg",143,33)
               n = 0
               i = 0

       await uasyncio.sleep(0.5)

async def do_buttons():
    btnA_rel = True
    bntB_rel = True
    state = 0
    ostate = state
    while True:
        nojoy = 1
        if (joy_c.value() == 0):   # Center gedrückt -> auf der Stelle drehen
             turn(ostate)
             nojoy = 0
        else:
            state = -1
            if (joy_u.value() == 0):
                 nojoy = 0
                 if (state < 0):
                     state = 0
                 state = state + 1
            if (joy_l.value() == 0):
                 nojoy = 0
                 if (state < 0):
                     state = 0
                 state = state + 2
            if (joy_r.value() == 0):
                 nojoy = 0
                 if (state < 0):
                     state = 0
                 state = state + 4
            if (joy_d.value() == 0):
                 nojoy = 0
                 if (state < 0):
                     state = 0
                 state = state + 6
            if (state == 1):
                move_forward()
            if (state == 2):
                move_left()
            if (state == 4):
                move_right()
            if (state == 6):
                move_backward()
            if (state == 3):
                drift_left(1)
            if (state == 5):
                drift_right(1)
            if (state == 8):
                drift_left(-1)
            if (state == 10):
                drift_right(-1)
            if (state < 0):
                state = 0
            else:
                ostate = state

        if (nojoy == 1):    # keine Joystick-Steuerung
            if (state >= 0):
                motor_stop()
            state = -1
        
        if (btnA.value() == 0) and (btnB.value() == 0):
            do_shutdown()
        if (btnA.value() == 0):
            if (nojoy == 0):
                do_notaus()
            else:
                if (btnA_rel == True):
                    btnA_rel = False
                    toggle_mower()                
        else:
            btnA_rel = True
            
        if (btnB.value() == 0):
            if (nojoy == 0):
                do_notaus()
            else:
                if (btnB_rel == True):
                    btnB_rel = False
                    do_special()
        else:
            btnB_rel = True
        
        await uasyncio.sleep(0.25)

async def coop_tasks():
    uasyncio.create_task(do_buttons())
    uasyncio.create_task(refresh_display())
    while True:
          await uasyncio.sleep(10)

def connect():
    global a
    ip = False
    #Connect to WLAN
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(_SSID, _PASSWORD)
    # Wait for connect or fail
    max_wait = 12
    while max_wait > 0:
        if wlan.status() < 0 or wlan.status() >= 3:
            break
        max_wait -= 1
        print('Waiting for connection...')
        sleep(1)
    # Handle connection error
    if wlan.status() != 3:
        a = "WiFi connect failed!!"
        display_alert()
    else:  # wlan.isconnected() == True
        ip = wlan.ifconfig()[0]
        print(f'Connected on {ip}')
    return ip
       
try:
    # Blink onboard LED slowly during restore 
    timer.init(freq=2, mode=Timer.PERIODIC, callback=blink)
    # Check Restore
    restore()
    # Init Display
    reset_display()
    spibus = SPIBus(cs=9, dc=8, sck=10, mosi=11, bl=13)
    display = PicoGraphics(display=DISPLAY_PICO_DISPLAY, bus=spibus, pen_type= PEN_RGB565, rotate=0)
    display.set_backlight(0.7)
    # Show Logo
    display_image("Logo.jpg")
    pc = False
    if hasattr(network, "WLAN"):
        # Blink onboard LED during connect
        timer.init(freq=4, mode=Timer.PERIODIC, callback=blink)
        # the board has WLAN capabilities
        ip = connect()
        if ip:             # WiFi ist da
            display_text("    my IP: " + ip)
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
                if ip:
                     a = "PiMowBot not found"
                     display_alert()
            ws_avail = get_request("http://" + pip + ":8008/echo")
            print(f'Websocket available {ws_avail}')
        else:
            pip = "localhost"
    else:
        print('Wrong Raspberry Pi Pico')
        print('Raspberry Pi Pico W required')
        a = "  Pico W required  "
        display_alert()
    if (pc == True) and (lt == 0) and (a == "none"):
        display_cinema()     # PiCAM Kinovorstellung ist eröffnet
    display_dir()            # kurze Vorstellung der Steuerung
    if (lt == 1):
        bta = 0              # Steuerbutton nicht darstellen
    gc.enable()
    display_text(" ||||||||||||||||||||||||||||||||||||||||||||||||||||||| ")
    uasyncio.run(coop_tasks())
except KeyboardInterrupt:
    print('Finished!!!')
#EOF
