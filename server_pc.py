import cv2
import numpy as np
import socket
import threading
import time
from flask import Flask, Response, render_template, request, jsonify

# --- Configuración ---
HOST_IP = '0.0.0.0'  # Escucha en todas las interfaces de red disponibles
WEB_PORT = 8000      # Puerto para la página web
CONTROL_PORT = 8001  # Puerto para recibir comandos del carro
CAMERA_PORT = 8002   # Puerto para recibir imágenes de la cámara

# --- Estado Global ---
control_pico_socket = None
latest_jpeg_frame = None
frame_lock = threading.Lock()

# --- Inicialización de Flask ---
app = Flask(__name__, template_folder='.')

# --- Hilo para manejar la conexión con la Pico de Control ---
def handle_control_pico():
    global control_pico_socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST_IP, CONTROL_PORT))
        s.listen()
        print(f"🤖 Esperando conexión del Pico de control en el puerto {CONTROL_PORT}...")
        while True:
            conn, addr = s.accept()
            with conn:
                print(f"✅ Pico de control conectado desde {addr}")
                control_pico_socket = conn
                try:
                    while True:
                        # Mantener la conexión viva, pero no esperamos datos de vuelta
                        # Una pequeña espera para evitar un ciclo de CPU al 100%
                        # Si recv(1) devuelve b'', el cliente se ha desconectado.
                        if not conn.recv(1):
                            break
                except (ConnectionResetError, BrokenPipeError):
                    print("🔌 Pico de control desconectado.")
                finally:
                    control_pico_socket = None
                    print("🔌 Pico de control desconectado.")


# --- Hilo para manejar la conexión con la Pico de la Cámara ---
def handle_camera_pico():
    global latest_jpeg_frame
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST_IP, CAMERA_PORT))
        s.listen()
        print(f"📸 Esperando conexión del Pico de la cámara en el puerto {CAMERA_PORT}...")
        while True:
            conn, addr = s.accept()
            with conn:
                print(f"✅ Pico de cámara conectado desde {addr}")
                try:
                    while True:
                        # 1. Recibir el tamaño de la imagen (4 bytes)
                        img_size_bytes = conn.recv(4)
                        if not img_size_bytes:
                            break
                        img_size = int.from_bytes(img_size_bytes, 'big')

                        # 2. Recibir los datos de la imagen
                        img_data = b''
                        while len(img_data) < img_size:
                            packet = conn.recv(img_size - len(img_data))
                            if not packet:
                                break
                            img_data += packet

                        # 3. Convertir YUV422 a JPG
                        # La OV7670 con esta librería usualmente envía YUYV (que es un tipo de YUV422)
                        yuv_image = np.frombuffer(img_data, dtype=np.uint8)
                        
                        # QVGA (320x240)
                        width, height = 320, 240
                        
                        # Asegurarse de que el buffer tenga el tamaño correcto
                        if yuv_image.size != width * height * 2:
                            print(f"⚠️ Tamaño de imagen incorrecto recibido: {yuv_image.size} bytes")
                            continue

                        yuv_image = yuv_image.reshape((height, width, 2))
                        
                        # Convertir de YUYV (YUV422) a BGR
                        bgr_image = cv2.cvtColor(yuv_image, cv2.COLOR_YUV2BGR_YUY2)
                        
                        # Codificar a JPG
                        ret, jpeg_buffer = cv2.imencode('.jpg', bgr_image)
                        
                        if ret:
                            with frame_lock:
                                latest_jpeg_frame = jpeg_buffer.tobytes()

                except (ConnectionResetError, BrokenPipeError, ValueError) as e:
                    print(f"🔌 Pico de cámara desconectado o error: {e}")
                finally:
                    print("🔌 Pico de cámara desconectado.")


# --- Rutas del Servidor Web (Flask) ---

@app.route('/')
def index():
    # Sirve el archivo HTML. Asegúrate de que se llame 'pagcarro2_modificado.html'
    # y esté en la misma carpeta que este script.
    return render_template('pagcarro2_modificado.html')

@app.route('/control', methods=['POST'])
def control():
    command = request.json.get('command')
    if control_pico_socket and command:
        try:
            print(f"➡️  Enviando comando: '{command}' al Pico de control.")
            control_pico_socket.sendall(command.encode('utf-8'))
            return jsonify({"status": "ok", "command": command})
        except (ConnectionResetError, BrokenPipeError):
            print("❌ Error: No se pudo enviar el comando. El Pico de control se desconectó.")
            return jsonify({"status": "error", "message": "Pico de control no conectado"})
    else:
        print("⚠️ Comando no enviado. No hay conexión con el Pico de control.")
        return jsonify({"status": "error", "message": "Pico de control no conectado"})

def frame_generator():
    while True:
        with frame_lock:
            if latest_jpeg_frame:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + latest_jpeg_frame + b'\r\n')
        # Pequeña pausa para no saturar la red si no hay frames nuevos
        time.sleep(0.03)

@app.route('/video_feed')
def video_feed():
    return Response(frame_generator(), mimetype='multipart/x-mixed-replace; boundary=frame')

# --- Flujo Principal ---
if __name__ == '__main__':
    # Iniciar hilos para los sockets de las Picos
    control_thread = threading.Thread(target=handle_control_pico, daemon=True)
    camera_thread = threading.Thread(target=handle_camera_pico, daemon=True)
    control_thread.start()
    camera_thread.start()

    # Iniciar el servidor web Flask
    print(f"🌐 Servidor web corriendo en http://<TU_IP>:{WEB_PORT}")
    app.run(host=HOST_IP, port=WEB_PORT, debug=False)