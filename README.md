# Blue Charter

Web basica de alquiler de barcos con calendario de disponibilidad, reservas y pago con Stripe Checkout.

## Arranque

En PowerShell:

```powershell
python app.py
```

Luego abre `http://localhost:3000`.

La app carga las claves automaticamente desde `.env`.

Si `python` no funciona en tu Windows, prueba con el ejecutable completo de tu instalacion de Python.

## Variables

- `STRIPE_SECRET_KEY`: clave secreta de Stripe para crear y consultar sesiones de pago.
- `STRIPE_PUBLIC_KEY`: no hace falta en el flujo actual, pero queda guardada para futuras integraciones en frontend.
- `BASE_URL`: URL publica desde la que se sirve la web. En local suele ser `http://localhost:3000`.
- `STRIPE_WEBHOOK_SECRET`: opcional pero recomendable. Sirve para confirmar pagos mediante webhook.
- `PORT`: opcional. Por defecto `3000`.

## Webhook local

Si usas Stripe CLI, puedes reenviar eventos al servidor:

```powershell
stripe listen --forward-to localhost:3000/api/stripe/webhook
```

Copia el secreto que te devuelva Stripe CLI en `STRIPE_WEBHOOK_SECRET`.
