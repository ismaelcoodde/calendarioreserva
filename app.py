import hashlib
import hmac
import json
import mimetypes
import os
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "reservations.db"


def load_dotenv(env_path):
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and key not in os.environ:
            os.environ[key] = value


load_dotenv(ENV_PATH)

PORT = int(os.getenv("PORT", "3000"))
BASE_URL = os.getenv("BASE_URL", f"http://localhost:{PORT}")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

BOATS = [
    {
        "id": "mediterraneo",
        "name": "Mediterraneo 28",
        "price": 100,
        "duration": "Dia completo",
    },
    {
        "id": "brisa",
        "name": "Brisa Azul 34",
        "price": 100,
        "duration": "Jornada sunset",
    },
    {
        "id": "coral",
        "name": "Coral Bay 40",
        "price": 100,
        "duration": "Full day premium",
    },
]
BOAT_MAP = {boat["id"]: boat for boat in BOATS}
DATE_KEY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

DB_LOCK = threading.Lock()
DB = sqlite3.connect(DB_PATH, check_same_thread=False)
DB.row_factory = sqlite3.Row


def init_db():
    with DB_LOCK:
        DB.execute(
            """
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                boat_id TEXT NOT NULL,
                date TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                customer_email TEXT NOT NULL,
                stripe_session_id TEXT,
                payment_status TEXT NOT NULL DEFAULT 'paid',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                confirmed_at TEXT,
                UNIQUE(boat_id, date)
            )
            """
        )

        existing_columns = {
            row["name"] for row in DB.execute("PRAGMA table_info(reservations)").fetchall()
        }

        if "stripe_session_id" not in existing_columns:
            DB.execute("ALTER TABLE reservations ADD COLUMN stripe_session_id TEXT")
        if "payment_status" not in existing_columns:
            DB.execute(
                "ALTER TABLE reservations ADD COLUMN payment_status TEXT NOT NULL DEFAULT 'paid'"
            )
        if "confirmed_at" not in existing_columns:
            DB.execute("ALTER TABLE reservations ADD COLUMN confirmed_at TEXT")

        DB.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_reservations_stripe_session_id
            ON reservations(stripe_session_id)
            WHERE stripe_session_id IS NOT NULL
            """
        )
        DB.commit()


def json_response(handler, status_code, payload):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def text_response(handler, status_code, body, content_type):
    payload = body if isinstance(body, bytes) else body.encode("utf-8")
    handler.send_response(status_code)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def read_raw_body(handler):
    content_length = int(handler.headers.get("Content-Length", "0") or "0")
    if content_length > 1_000_000:
        raise ValueError("Payload demasiado grande")
    return handler.rfile.read(content_length)


def read_json_body(handler):
    raw_body = read_raw_body(handler)
    if not raw_body:
        return {}
    try:
        return json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("JSON invalido") from error


def parse_date_key(date_value):
    return datetime.strptime(date_value, "%Y-%m-%d").date()


def validate_reservation_payload(boat_id, date_value, name, email):
    if boat_id not in BOAT_MAP:
        raise ValueError("Barco no valido")
    if not DATE_KEY_PATTERN.match(date_value):
        raise ValueError("Fecha no valida")
    if not name or not email:
        raise ValueError("Faltan datos del cliente")
    if parse_date_key(date_value) < datetime.now().date():
        raise ValueError("Solo se permiten fechas de hoy en adelante")


def build_reservation_map():
    with DB_LOCK:
        rows = DB.execute(
            """
            SELECT boat_id, date, customer_name, customer_email, created_at
            FROM reservations
            WHERE payment_status = 'paid'
            ORDER BY date ASC
            """
        ).fetchall()

    reservation_map = {}
    for row in rows:
        reservation_map.setdefault(row["boat_id"], {})[row["date"]] = {
            "name": row["customer_name"],
            "email": row["customer_email"],
            "createdAt": row["created_at"],
        }
    return reservation_map


def get_paid_reservation_for_slot(boat_id, date_value):
    with DB_LOCK:
        return DB.execute(
            """
            SELECT boat_id, date, customer_name, customer_email, stripe_session_id, payment_status
            FROM reservations
            WHERE boat_id = ? AND date = ? AND payment_status = 'paid'
            """,
            (boat_id, date_value),
        ).fetchone()


def get_reservation_by_session(session_id):
    with DB_LOCK:
        return DB.execute(
            """
            SELECT boat_id, date, customer_name, customer_email, stripe_session_id, payment_status
            FROM reservations
            WHERE stripe_session_id = ?
            """,
            (session_id,),
        ).fetchone()


def insert_reservation(boat_id, date_value, name, email, session_id, payment_status):
    now = datetime.utcnow().isoformat() + "Z"
    with DB_LOCK:
        DB.execute(
            """
            INSERT INTO reservations (
                boat_id,
                date,
                customer_name,
                customer_email,
                stripe_session_id,
                payment_status,
                created_at,
                confirmed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (boat_id, date_value, name, email, session_id, payment_status, now, now),
        )
        DB.commit()


def stripe_request(method, endpoint, params=None):
    if not STRIPE_SECRET_KEY:
        raise RuntimeError("Stripe no esta configurado")

    encoded_params = None
    headers = {
        "Authorization": f"Bearer {STRIPE_SECRET_KEY}",
    }
    if params is not None:
        encoded_params = urllib.parse.urlencode(params).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    request = urllib.request.Request(
        f"https://api.stripe.com{endpoint}",
        data=encoded_params,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        payload = error.read().decode("utf-8")
        try:
            details = json.loads(payload)
            message = details.get("error", {}).get("message", "Error al comunicar con Stripe")
        except json.JSONDecodeError:
            message = "Error al comunicar con Stripe"
        raise RuntimeError(message) from error


def create_checkout_session(boat_id, date_value, name, email):
    validate_reservation_payload(boat_id, date_value, name, email)
    boat = BOAT_MAP[boat_id]

    if get_paid_reservation_for_slot(boat_id, date_value):
        raise ValueError("Ese dia ya esta reservado para este barco")

    params = {
        "mode": "payment",
        "success_url": f"{BASE_URL}/?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{BASE_URL}/?checkout=cancel",
        "customer_email": email,
        "metadata[boat_id]": boat_id,
        "metadata[reservation_date]": date_value,
        "metadata[customer_name]": name,
        "metadata[customer_email]": email,
        "line_items[0][price_data][currency]": "eur",
        "line_items[0][price_data][unit_amount]": str(boat["price"] * 100),
        "line_items[0][price_data][product_data][name]": f"Reserva {boat['name']}",
        "line_items[0][price_data][product_data][description]": f"{date_value} · {boat['duration']}",
        "line_items[0][quantity]": "1",
    }
    return stripe_request("POST", "/v1/checkout/sessions", params)


def retrieve_checkout_session(session_id):
    return stripe_request("GET", f"/v1/checkout/sessions/{urllib.parse.quote(session_id)}")


def extract_reservation_from_session(session):
    metadata = session.get("metadata", {})
    boat_id = str(metadata.get("boat_id", "")).strip()
    date_value = str(metadata.get("reservation_date", "")).strip()
    name = str(metadata.get("customer_name", "")).strip()
    email = str(
        metadata.get("customer_email")
        or session.get("customer_details", {}).get("email")
        or session.get("customer_email", "")
    ).strip()

    validate_reservation_payload(boat_id, date_value, name, email)
    return boat_id, date_value, name, email


def finalize_checkout_session(session):
    session_id = session.get("id")
    if not session_id:
        raise ValueError("Sesion de Stripe invalida")

    if session.get("payment_status") != "paid":
        return {"reservationStatus": "pending"}

    existing_by_session = get_reservation_by_session(session_id)
    if existing_by_session:
        return {
            "reservationStatus": "confirmed",
            "boatId": existing_by_session["boat_id"],
            "date": existing_by_session["date"],
        }

    boat_id, date_value, name, email = extract_reservation_from_session(session)
    if get_paid_reservation_for_slot(boat_id, date_value):
        return {
            "reservationStatus": "slot-taken",
            "boatId": boat_id,
            "date": date_value,
        }

    insert_reservation(boat_id, date_value, name, email, session_id, "paid")
    return {
        "reservationStatus": "confirmed",
        "boatId": boat_id,
        "date": date_value,
    }


def parse_stripe_signature(signature_header):
    entries = {}
    for item in signature_header.split(","):
        if "=" in item:
            key, value = item.strip().split("=", 1)
            entries.setdefault(key, []).append(value)
    timestamp = entries.get("t", [None])[0]
    signatures = entries.get("v1", [])
    return timestamp, signatures


def verify_stripe_webhook_signature(raw_body, signature_header):
    if not STRIPE_WEBHOOK_SECRET:
        raise ValueError("Webhook de Stripe no configurado")

    timestamp, signatures = parse_stripe_signature(signature_header or "")
    if not timestamp or not signatures:
        raise ValueError("Cabecera Stripe-Signature no valida")

    age_seconds = abs(int(time.time()) - int(timestamp))
    if age_seconds > 300:
        raise ValueError("Firma de Stripe fuera de tolerancia")

    signed_payload = f"{timestamp}.{raw_body.decode('utf-8')}".encode("utf-8")
    expected = hmac.new(
        STRIPE_WEBHOOK_SECRET.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    if not any(hmac.compare_digest(signature, expected) for signature in signatures):
        raise ValueError("Firma de Stripe no valida")

    return json.loads(raw_body.decode("utf-8"))


class AppHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path_value = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        if path_value == "/api/config":
            json_response(
                self,
                200,
                {
                    "stripeEnabled": bool(STRIPE_SECRET_KEY),
                    "webhookEnabled": bool(STRIPE_WEBHOOK_SECRET),
                },
            )
            return

        if path_value == "/api/reservations":
            json_response(self, 200, build_reservation_map())
            return

        if path_value == "/api/checkout-session-status":
            if not STRIPE_SECRET_KEY:
                json_response(self, 503, {"error": "Stripe no esta configurado en el servidor"})
                return

            session_id = (query.get("session_id") or [""])[0].strip()
            if not session_id:
                json_response(self, 400, {"error": "Falta el identificador de la sesion"})
                return

            try:
                session = retrieve_checkout_session(session_id)
                result = finalize_checkout_session(session)
                boat_name = BOAT_MAP.get(result.get("boatId", ""), {}).get("name", "")
                json_response(
                    self,
                    200,
                    {
                        "reservationStatus": result["reservationStatus"],
                        "boatName": boat_name,
                        "date": result.get("date", ""),
                        "reservations": build_reservation_map(),
                        "paymentStatus": session.get("payment_status", ""),
                    },
                )
            except Exception as error:
                json_response(self, 400, {"error": str(error) or "No se pudo comprobar el pago"})
            return

        self.serve_static(path_value)

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path_value = parsed_url.path

        if path_value == "/api/create-checkout-session":
            if not STRIPE_SECRET_KEY:
                json_response(self, 503, {"error": "Stripe no esta configurado en el servidor"})
                return

            try:
                body = read_json_body(self)
                session = create_checkout_session(
                    str(body.get("boatId", "")).strip(),
                    str(body.get("date", "")).strip(),
                    str(body.get("name", "")).strip(),
                    str(body.get("email", "")).strip(),
                )
                json_response(
                    self,
                    201,
                    {
                        "url": session.get("url", ""),
                        "sessionId": session.get("id", ""),
                    },
                )
            except ValueError as error:
                message = str(error)
                status_code = 409 if "ya esta reservado" in message else 400
                json_response(self, status_code, {"error": message})
            except Exception as error:
                json_response(self, 400, {"error": str(error) or "No se pudo iniciar el pago"})
            return

        if path_value == "/api/stripe/webhook":
            try:
                raw_body = read_raw_body(self)
                event = verify_stripe_webhook_signature(
                    raw_body,
                    self.headers.get("Stripe-Signature", ""),
                )
                if event.get("type") == "checkout.session.completed":
                    finalize_checkout_session(event.get("data", {}).get("object", {}))
                json_response(self, 200, {"received": True})
            except Exception as error:
                json_response(self, 400, {"error": str(error) or "Webhook invalido"})
            return

        json_response(self, 404, {"error": "Ruta no encontrada"})

    def serve_static(self, path_value):
        relative_path = "index.html" if path_value in ("", "/") else path_value.lstrip("/")
        file_path = (BASE_DIR / relative_path).resolve()

        if BASE_DIR not in file_path.parents and file_path != BASE_DIR / "index.html":
            json_response(self, 403, {"error": "Ruta no permitida"})
            return

        if not file_path.exists() or not file_path.is_file():
            json_response(self, 404, {"error": "Archivo no encontrado"})
            return

        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        text_response(self, 200, file_path.read_bytes(), f"{content_type}; charset=utf-8")

    def log_message(self, format_string, *args):
        return


def run():
    init_db()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), AppHandler)
    print(f"Servidor Python disponible en {BASE_URL}")
    server.serve_forever()


if __name__ == "__main__":
    run()
