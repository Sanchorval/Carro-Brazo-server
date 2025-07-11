import machine
import network
import socket
import time
from ov7670_wrapper import *

# --- CONFIGURACIÓN ---

SERVER_IP = "192.168.245.247" 
CAMERA_PORT = 8002
WIFI_SSID = "AndroidAP"  #misma red que el PC
WIFI_PASS = "miper9605"

# Pines para la cámara OV7670
data_pin_base=0; pclk_pin_no=8; mclk_pin_no=9; href_pin_no=10
vsync_pin_no=11; reset_pin_no=19; shutdown_pin_no=18; sda_pin_no=20; scl_pin_no=21

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Conectando a WiFi...")
        wlan.connect(WIFI_SSID, WIFI_PASS)
        while not wlan.isconnected():
            time.sleep(1)
    print("Conectado:", wlan.ifconfig())

def init_camera():
    i2c = machine.I2C(0, freq=100000, scl=machine.Pin(scl_pin_no), sda=machine.Pin(sda_pin_no))
    cam = OV7670Wrapper(i2c_bus=i2c, mclk_pin_no=mclk_pin_no, pclk_pin_no=pclk_pin_no, data_pin_base=data_pin_base, vsync_pin_no=vsync_pin_no, href_pin_no=href_pin_no, reset_pin_no=reset_pin_no, shutdown_pin_no=shutdown_pin_no)
    cam.wrapper_configure_yuv()
    cam.wrapper_configure_base()
    cam.wrapper_configure_size(OV7670_WRAPPER_SIZE_DIV2)  # 320x240
    cam.wrapper_configure_test_pattern(OV7670_WRAPPER_TEST_PATTERN_NONE)
    return cam

# === FLUJO PRINCIPAL ===
connect_wifi()
camera = init_camera()
time.sleep(1)

width, height = 320, 240
buf_size = width * height * 2  # YUV422 (2 bytes por pixel)
buf = bytearray(buf_size)

while True:
    try:
        print("Conectando al servidor del PC...")
        addr = socket.getaddrinfo(SERVER_IP, CAMERA_PORT)[0][-1]
        s = socket.socket()
        s.connect(addr)
        print("Conectado. Iniciando envío de imágenes.")

        while True:
            camera.capture(buf)
            # Enviar tamaño de la imagen (4 bytes)
            s.sendall(len(buf).to_bytes(4, 'big'))
            # Enviar la imagen
            s.sendall(buf)
            time.sleep(0.1) # Controla los FPS (0.1 = ~10 FPS)

    except OSError as e:
        print(f"Error de conexión o envío: {e}")
        if 's' in locals():
            s.close()
        time.sleep(5) # Esperar antes de reintentar