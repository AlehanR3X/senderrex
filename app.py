import asyncio
import json
import os
from flask import Flask, render_template, request, redirect, url_for, flash
from telethon import TelegramClient
from telethon.errors import FloodWaitError, RPCError
from datos import api_id, api_hash

# Configuración básica
app = Flask(__name__)
app.secret_key = 'replace-with-your-secret-key'

SESSION_NAME = 'session_telegram'
DESTINATIONS_FILE = 'destino.json'

# Variable global para controlar la cancelación
cancel_event = asyncio.Event()

# Cargar y guardar destinos

def load_destinations():
    if not os.path.exists(DESTINATIONS_FILE):
        with open(DESTINATIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump({'destinations': {}}, f, indent=4)
    with open(DESTINATIONS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('destinations', {})


def save_destinations(destinations):
    with open(DESTINATIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump({'destinations': destinations}, f, indent=4)

@app.route('/', methods=['GET', 'POST'])
def index():
    destinations = load_destinations()
    if request.method == 'POST':
        if 'cancel' in request.form:
            # Activar el evento de cancelación
            cancel_event.set()
            flash('Envío cancelado.', 'info')
            return redirect(url_for('index'))

        # Datos del formulario
        dest_key = request.form.get('destination')
        prefix = request.form.get('prefix', '').strip()
        delay = int(request.form.get('delay', 30))
        messages = request.form.get('messages', '').splitlines()

        if not prefix or not messages:
            flash('Prefijo y mensajes son requeridos.', 'warning')
            return redirect(url_for('index'))

        target_chat = destinations.get(dest_key)
        if not target_chat:
            flash('Destino inválido.', 'danger')
            return redirect(url_for('index'))

        # Reiniciar el evento de cancelación
        cancel_event.clear()

        # Ejecutar envío
        asyncio.run(send_messages(target_chat, prefix, delay, messages))
        flash('Envío completado exitosamente.', 'success')
        return redirect(url_for('index'))

    return render_template('index.html', destinations=load_destinations())

async def send_messages(target_chat, prefix, delay, messages):
    async with TelegramClient(SESSION_NAME, api_id, api_hash) as client:
        await client.start()
        entity = await client.get_input_entity(target_chat)
        for msg in messages:
            if cancel_event.is_set():
                break  # Detener el envío si se activa el evento de cancelación
            text = msg.strip()
            if not text:
                continue
            full = f"{prefix} {text}"
            try:
                await client.send_message(entity, full)
                await asyncio.sleep(delay)
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds)
            except Exception:
                continue

if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
