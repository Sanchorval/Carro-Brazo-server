import rp2
import network
import time
import socket
import ujson
from machine import I2C, Pin, PWM
import ssd1306

# --- CONFIGURACIÓN ---

SERVER_IP = "192.168.245.247" 
SERVER_PORT = 8001
WIFI_SSID = 'AndroidAP'
WIFI_PASS = 'miper9605'

# -------- OLED --------
i2c = I2C(1, scl=Pin(3), sda=Pin(2))
oled = ssd1306.SSD1306_I2C(128, 64, i2c)

def mostrar_estado(linea2="", icono=""):
    oled.fill(0)
    oled.text("Cliente Control", 0, 0)
    oled.text(linea2[:16], 0, 20)

    if icono == "🛠": oled.rect(100, 40, 10, 10, 1)

    oled.show()

# ... mensajes, servos, motores, etc ...
mensajes = {"carro": ("Modo manual activado", "🛠"), "brazo": ("Modo automatico activado", "🤖"),"adelante": ("Moviendo adelante", ">>>"),"atras": ("Moviendo atras", "<<<"), "izquierda": ("Girando izquierda", "<--"),"derecha": ("Girando derecha", "-->")}
servo_base = PWM(Pin(18)); servo_hombro = PWM(Pin(17)); servo_codo = PWM(Pin(16)); electro=Pin(19, Pin.OUT)
for servo in [servo_base, servo_hombro, servo_codo]: servo.freq(50)
def angulo_base_a_duty_ns_personalizado(angulo): return int(-10000 * (angulo) + 1291666)
def angulo_hombro_a_duty_ns_personalizado(angulo): return int(-11111*(angulo) +1780000 )
def angulo_codo_a_duty_ns_personalizado(angulo): return int( 12142*(angulo)+607142)
def correcion_codo(anguloHombro,anguloCodo):
    if anguloCodo-anguloHombro > 20: anguloCodo = anguloHombro+20
    return anguloCodo
ENA = PWM(Pin(10)); IN1 = Pin(11, Pin.OUT); IN2 = Pin(12, Pin.OUT)
ENB = PWM(Pin(13)); IN3 = Pin(14, Pin.OUT); IN4 = Pin(15, Pin.OUT)
ENA.freq(1000); ENB.freq(1000)
def motor_stop(): ENA.duty_u16(0); ENB.duty_u16(0); IN1.low(); IN2.low(); IN3.low(); IN4.low()
def motor_atras(): ENA.duty_u16(60000); ENB.duty_u16(60000); IN1.low(); IN2.high(); IN3.low(); IN4.high()
def motor_adelante(): ENA.duty_u16(60000); ENB.duty_u16(60000); IN1.high(); IN2.low(); IN3.high(); IN4.low()
def motor_izquierda(): ENA.duty_u16(60000); ENB.duty_u16(60000); IN3.high(); IN4.low(); IN1.low(); IN2.high()
def motor_derecha(): ENA.duty_u16(60000); ENB.duty_u16(60000); IN1.high(); IN2.low(); IN3.low(); IN4.high()

# -------- CONEXIÓN WIFI --------
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(WIFI_SSID, WIFI_PASS)
mostrar_estado("Conectando WiFi...")
timeout = 10
while timeout > 0 and wlan.status() < 3:
    timeout -= 1; time.sleep(1)
if wlan.status() != 3:
    mostrar_estado("Error WiFi"); raise RuntimeError('Error de conexion Wi-Fi')
ip = wlan.ifconfig()[0]
print("¡Conectado! IP:", ip)
mostrar_estado("IP: " + ip)
time.sleep(2)

# -------- Variables de estado --------
modo_manual_carro = False
modo_manual_brazo = False
angulos_actuales = [90, 70, 0]

# -------- Loop principal del cliente --------
while True:
    try:
        mostrar_estado("Conectando a PC", SERVER_IP)
        addr = socket.getaddrinfo(SERVER_IP, SERVER_PORT)[0][-1]
        s = socket.socket()
        s.connect(addr)
        print("Conectado al servidor del PC")
        mostrar_estado("Conectado a PC!")

        while True: # Bucle de recepción de comandos
            accion = s.recv(1024).decode('utf-8')
            if not accion:
                # Si no se recibe nada, la conexión se cerró
                break
            
            print("📥 Acción recibida:", accion)
            texto, icono = mensajes.get(accion, ("Accion desconocida", ""))
            mostrar_estado(texto, icono)

            if accion == "carro":
                modo_manual_carro = True; modo_manual_brazo = False; motor_stop()
            elif accion == "brazo":
                modo_manual_brazo = True; modo_manual_carro = False; motor_stop()
            elif accion == "auto":
                modo_manual_brazo = False; modo_manual_carro = False; motor_stop()
            
            if accion == "recojer":
                electro.low()
            if accion == "soltar":
                electro.high()

            if modo_manual_carro:
                if accion == 'adelante': motor_adelante()
                elif accion == 'atras': motor_atras()
                elif accion == 'izquierda': motor_izquierda()
                elif accion == 'derecha': motor_derecha()
                elif accion == "stop": motor_stop()
            
            if modo_manual_brazo:
                if accion == 'adelante':
                    if angulos_actuales[0] > 0: angulos_actuales[0] -= 10
                    if angulos_actuales[1] > 0: angulos_actuales[1] -= 10
                elif accion == 'atras':
                    if angulos_actuales[0] < 90: angulos_actuales[0] += 10
                    if angulos_actuales[1] < 90: angulos_actuales[1] += 10
                elif accion == 'izquierda':
                    if angulos_actuales[2] > -90: angulos_actuales[2] -= 10
                elif accion == 'derecha':
                    if angulos_actuales[2] < 90: angulos_actuales[2] += 10
            
            # Actualizar la posición de los servos constantemente
            servo_base.duty_ns(angulo_base_a_duty_ns_personalizado(angulos_actuales[2]))
            servo_hombro.duty_ns(angulo_hombro_a_duty_ns_personalizado(angulos_actuales[0]))
            angulos_actuales[1]=correcion_codo(angulos_actuales[0],angulos_actuales[1])
            servo_codo.duty_ns(angulo_codo_a_duty_ns_personalizado(angulos_actuales[1]))

    except OSError as e:
        print("Error de conexión:", e)
        mostrar_estado("Error conexion PC")
        if 's' in locals():
            s.close()
        time.sleep(5) # Esperar antes de reintentar