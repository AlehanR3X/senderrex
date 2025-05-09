import asyncio
import json
import os
import threading
import uuid

from flask import Flask, render_template, request, redirect, url_for, flash, session
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from datos import api_id, api_hash

# Configuración básica
app = Flask(__name__)
app.secret_key = 'replace-with-your-secret-key'

SESSION_NAME = 'session_telegram'
DESTINATIONS_FILE = 'destino.json'

# Para controlar jobs en background
jobs = {}            # job_id → threading.Thread
cancel_events = {}   # job_id → threading.Event

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
        dest_key = request.form.get('destination')
        prefix   = request.form.get('prefix', '').strip()
        delay    = int(request.form.get('delay', 30))
        messages = request.form.get('messages', '').splitlines()

        if not prefix or not messages:
            flash('Prefijo y mensajes son requeridos.', 'warning')
            return redirect(url_for('index'))

        target_chat = destinations.get(dest_key)
        if not target_chat:
            flash('Destino inválido.', 'danger')
            return redirect(url_for('index'))

        # Creamos un job_id y su Event de cancelación
        job_id = str(uuid.uuid4())
        stop_event = threading.Event()
        cancel_events[job_id] = stop_event

        # Hilo que ejecuta la coroutine send_messages
        thread = threading.Thread(
            target=asyncio.run,
            args=(send_messages(target_chat, prefix, delay, messages, stop_event),)
        )
        thread.start()
        jobs[job_id] = thread

        # Guardamos en sesión para mostrar el botón de cancelar
        session['current_job'] = job_id

        flash('Envío iniciado. Puedes cancelar en cualquier momento.', 'info')
        return redirect(url_for('index'))

    current_job = session.get('current_job')
    return render_template('index.html', destinations=destinations, current_job=current_job)

@app.route('/cancel/<job_id>', methods=['POST'])
def cancel(job_id):
    evt = cancel_events.get(job_id)
    if evt:
        evt.set()
        flash('Cancelando envío…', 'info')
    else:
        flash('No hay envío activo.', 'warning')
    return redirect(url_for('index'))

async def send_messages(target_chat, prefix, delay, messages, stop_event):
    async with TelegramClient(SESSION_NAME, api_id, api_hash) as client:
        await client.start()
        entity = await client.get_input_entity(target_chat)

        for msg in messages:
            if stop_event.is_set():
                break

            text = msg.strip()
            if not text:
                continue

            full = f"{prefix} {text}"
            try:
                await client.send_message(entity, full)
                # dividimos el sleep para comprobar el flag cada segundo
                for _ in range(delay):
                    if stop_event.is_set():
                        break
                    await asyncio.sleep(1)
                if stop_event.is_set():
                    break

            except FloodWaitError as e:
                await asyncio.sleep(e.seconds)
            except Exception:
                continue

    # limpieza al terminar o cancelar
    jid = session.pop('current_job', None)
    if jid:
        cancel_events.pop(jid, None)
        jobs.pop(jid, None)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
