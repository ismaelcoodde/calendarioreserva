const boats = [
  {
    id: "mediterraneo",
    name: "Mediterraneo 28",
    type: "Lancha premium",
    capacity: "Hasta 8 personas",
    price: 100,
    duration: "Dia completo",
    description:
      "Perfecta para una escapada costera con solarium, toldo y zona de relax.",
    features: ["Patron incluido", "Equipo de snorkel", "Nevera a bordo"],
    accent: "rgba(15, 139, 141, 0.18)",
    tint: "rgba(15, 139, 141, 0.12)",
  },
  {
    id: "brisa",
    name: "Brisa Azul 34",
    type: "Velero elegante",
    capacity: "Hasta 10 personas",
    price: 100,
    duration: "Jornada sunset",
    description:
      "Una opcion comoda para navegar con calma, celebraciones o puestas de sol.",
    features: ["Capitan profesional", "Bebidas de bienvenida", "Equipo de musica"],
    accent: "rgba(242, 143, 59, 0.2)",
    tint: "rgba(242, 143, 59, 0.14)",
  },
  {
    id: "coral",
    name: "Coral Bay 40",
    type: "Catamaran",
    capacity: "Hasta 12 personas",
    price: 100,
    duration: "Full day premium",
    description:
      "Amplio, estable y pensado para grupos que quieren comodidad durante todo el dia.",
    features: ["Dos zonas chill out", "Paddle surf", "Catering opcional"],
    accent: "rgba(20, 83, 116, 0.22)",
    tint: "rgba(20, 83, 116, 0.14)",
  },
];

const weekdayNames = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"];
const monthFormatter = new Intl.DateTimeFormat("es-ES", {
  month: "long",
  year: "numeric",
});
const fullDateFormatter = new Intl.DateTimeFormat("es-ES", {
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
});

const elements = {
  boatList: document.getElementById("boat-list"),
  bookingSection: document.getElementById("reservas"),
  selectedBoatSummary: document.getElementById("selected-boat-summary"),
  selectedBoatFeatures: document.getElementById("selected-boat-features"),
  calendarTitle: document.getElementById("calendar-title"),
  weekdays: document.getElementById("weekdays"),
  calendarDays: document.getElementById("calendar-days"),
  selectedDateText: document.getElementById("selected-date-text"),
  reservationForm: document.getElementById("reservation-form"),
  customerName: document.getElementById("customer-name"),
  customerEmail: document.getElementById("customer-email"),
  checkoutButton: document.getElementById("checkout-button"),
  paymentNote: document.getElementById("payment-note"),
  statusMessage: document.getElementById("status-message"),
  prevMonth: document.getElementById("prev-month"),
  nextMonth: document.getElementById("next-month"),
};

const today = startOfDay(new Date());
const AVAILABILITY_REFRESH_MS = 15000;
const state = {
  selectedBoatId: boats[0].id,
  currentMonth: new Date(today.getFullYear(), today.getMonth(), 1),
  selectedDate: null,
  reservations: {},
  stripeEnabled: false,
};
let reservationRefreshTimer = null;

function startOfDay(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function formatDateKey(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseDateKey(dateKey) {
  const [year, month, day] = dateKey.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function getSelectedBoat() {
  return boats.find((boat) => boat.id === state.selectedBoatId);
}

function getBoatReservations(boatId) {
  return state.reservations[boatId] || {};
}

function setStatus(message, type = "") {
  elements.statusMessage.textContent = message;
  elements.statusMessage.className = "status-message";
  if (type) {
    elements.statusMessage.classList.add(type);
  }
}

function setPaymentNote(message, type = "") {
  elements.paymentNote.textContent = message;
  elements.paymentNote.className = "payment-note";
  if (type) {
    elements.paymentNote.classList.add(type);
  }
}

function scrollToReservations() {
  elements.bookingSection?.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
}

function resetSelection() {
  state.selectedDate = null;
  elements.selectedDateText.textContent =
    "Todavia no has seleccionado una fecha";
}

function renderBoatCards() {
  elements.boatList.innerHTML = "";

  boats.forEach((boat) => {
    const card = document.createElement("article");
    card.className = "boat-card";
    if (boat.id === state.selectedBoatId) {
      card.classList.add("active");
    }

    card.style.setProperty("--card-glow", boat.accent);
    card.style.setProperty("--card-tint", boat.tint);
    card.setAttribute("role", "button");
    card.tabIndex = 0;
    card.innerHTML = `
      <span class="boat-badge">${boat.type}</span>
      <h3>${boat.name}</h3>
      <p>${boat.description}</p>
      <div class="boat-meta">
        <span>${boat.capacity}</span>
        <strong>${boat.price} EUR</strong>
      </div>
    `;

    const selectBoat = () => {
      if (boat.id === state.selectedBoatId) {
        return;
      }

      state.selectedBoatId = boat.id;
      resetSelection();
      setStatus("");
      renderBoatCards();
      renderSelectedBoat();
      renderCalendar();
    };

    card.addEventListener("click", selectBoat);
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectBoat();
      }
    });

    elements.boatList.appendChild(card);
  });
}

function renderSelectedBoat() {
  const boat = getSelectedBoat();
  elements.selectedBoatSummary.innerHTML = `
    <p class="eyebrow">Barco seleccionado</p>
    <h3 class="summary-name">${boat.name}</h3>
    <p class="summary-price">Desde ${boat.price} EUR</p>
    <p class="summary-description">${boat.description}</p>
    <p class="summary-description">${boat.capacity} · ${boat.duration}</p>
  `;

  elements.selectedBoatFeatures.innerHTML = "";
  boat.features.forEach((feature) => {
    const item = document.createElement("li");
    item.textContent = feature;
    elements.selectedBoatFeatures.appendChild(item);
  });
}

function renderWeekdays() {
  elements.weekdays.innerHTML = "";
  weekdayNames.forEach((name) => {
    const day = document.createElement("div");
    day.className = "weekday";
    day.textContent = name;
    elements.weekdays.appendChild(day);
  });
}

function renderCalendar() {
  const boatReservations = getBoatReservations(state.selectedBoatId);
  const year = state.currentMonth.getFullYear();
  const month = state.currentMonth.getMonth();
  const firstDay = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0);
  const leadingBlanks = (firstDay.getDay() + 6) % 7;

  elements.calendarTitle.textContent = capitalize(monthFormatter.format(firstDay));
  elements.calendarDays.innerHTML = "";

  for (let index = 0; index < leadingBlanks; index += 1) {
    const placeholder = document.createElement("div");
    placeholder.className = "calendar-placeholder";
    elements.calendarDays.appendChild(placeholder);
  }

  for (let dayNumber = 1; dayNumber <= lastDay.getDate(); dayNumber += 1) {
    const date = new Date(year, month, dayNumber);
    const dateKey = formatDateKey(date);
    const button = document.createElement("button");
    const isPast = startOfDay(date) < today;
    const isBooked = Boolean(boatReservations[dateKey]);
    const isSelected = state.selectedDate === dateKey;

    button.type = "button";
    button.className = "calendar-day";
    button.textContent = String(dayNumber);

    if (isSelected) {
      button.classList.add("selected");
    } else if (isBooked) {
      button.classList.add("booked");
      button.disabled = true;
      button.title = `Reservado por ${boatReservations[dateKey].name}`;
    } else if (isPast) {
      button.classList.add("past");
      button.disabled = true;
    } else {
      button.classList.add("available");
      button.addEventListener("click", () => {
        state.selectedDate = dateKey;
        elements.selectedDateText.textContent = capitalize(
          fullDateFormatter.format(date)
        );
        setStatus("");
        renderCalendar();
      });
    }

    elements.calendarDays.appendChild(button);
  }
}

function capitalize(text) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

async function fetchReservations() {
  const response = await fetch(`/api/reservations?ts=${Date.now()}`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error("No se pudo cargar la disponibilidad");
  }

  state.reservations = await response.json();
}

async function refreshAvailability(options = {}) {
  const { silent = false, clearInvalidSelection = true } = options;
  const previousSelectedDate = state.selectedDate;
  const previousBoatId = state.selectedBoatId;

  try {
    await fetchReservations();
    const boatReservations = getBoatReservations(previousBoatId);
    const selectedDateWasBooked =
      previousSelectedDate && Boolean(boatReservations[previousSelectedDate]);

    if (selectedDateWasBooked && clearInvalidSelection) {
      resetSelection();
      if (!silent) {
        setStatus("Ese dia acaba de quedar reservado y ya aparece marcado en rojo.", "error");
      }
    } else if (!silent && !elements.statusMessage.textContent.includes("Pago confirmado")) {
      setStatus("");
    }

    renderCalendar();
  } catch (error) {
    if (!silent) {
      setStatus(error.message || "No se pudo actualizar la disponibilidad.", "error");
    }
  }
}

async function fetchAppConfig() {
  const response = await fetch("/api/config");

  if (!response.ok) {
    throw new Error("No se pudo cargar la configuracion de pago");
  }

  const config = await response.json();
  state.stripeEnabled = Boolean(config.stripeEnabled);

  if (state.stripeEnabled) {
    setPaymentNote(
      "Tu fecha se marca como reservada en rojo en cuanto Stripe confirma el pago."
    );
  } else {
    setPaymentNote(
      "Los pagos con Stripe todavia no estan configurados. Define STRIPE_SECRET_KEY y BASE_URL en el servidor.",
      "warning"
    );
  }
}

function changeMonth(offset) {
  const nextMonth = new Date(
    state.currentMonth.getFullYear(),
    state.currentMonth.getMonth() + offset,
    1
  );
  state.currentMonth = nextMonth;

  if (state.selectedDate) {
    const selectedDate = parseDateKey(state.selectedDate);
    const selectedMonth = new Date(
      selectedDate.getFullYear(),
      selectedDate.getMonth(),
      1
    );

    if (selectedMonth.getTime() !== state.currentMonth.getTime()) {
      resetSelection();
    }
  }

  renderCalendar();
}

async function handleCheckoutReturn() {
  const params = new URLSearchParams(window.location.search);
  const checkoutState = params.get("checkout");
  const sessionId = params.get("session_id");

  if (checkoutState === "cancel") {
    setStatus("Pago cancelado. Tu fecha sigue libre mientras nadie la reserve.", "error");
    scrollToReservations();
    window.history.replaceState({}, "", `${window.location.pathname}#reservas`);
    return;
  }

  if (checkoutState !== "success" || !sessionId) {
    return;
  }

  setStatus("Verificando el pago con Stripe...", "");

  try {
    const response = await fetch(
      `/api/checkout-session-status?session_id=${encodeURIComponent(sessionId)}`
    );
    const payload = await response.json();

    if (!response.ok) {
      throw new Error(payload.error || "No se pudo comprobar el pago");
    }

    state.reservations = payload.reservations || {};
    resetSelection();
    renderCalendar();

    if (payload.reservationStatus === "confirmed") {
      const dateText = capitalize(fullDateFormatter.format(parseDateKey(payload.date)));
      setStatus(
        `Pago confirmado de 100 EUR. ${payload.boatName} queda reservado para el ${dateText}.`,
        "success"
      );
      scrollToReservations();
    } else if (payload.reservationStatus === "slot-taken") {
      setStatus(
        "El pago figura como completado, pero esa fecha ya estaba ocupada al confirmarse. Revisa el cobro en Stripe antes de reutilizarla.",
        "error"
      );
      scrollToReservations();
    } else {
      setStatus(
        "El pago se ha registrado, pero la reserva aun no se ha confirmado. Recarga en unos segundos.",
        "error"
      );
      scrollToReservations();
    }
  } catch (error) {
    setStatus(error.message || "No se pudo verificar el pago.", "error");
    scrollToReservations();
  } finally {
    window.history.replaceState({}, "", `${window.location.pathname}#reservas`);
  }
}

async function handleReservationSubmit(event) {
  event.preventDefault();

  if (!state.selectedDate) {
    setStatus("Selecciona un dia libre antes de confirmar la reserva.", "error");
    return;
  }

  const boat = getSelectedBoat();
  const name = elements.customerName.value.trim();
  const email = elements.customerEmail.value.trim();

  if (!name || !email) {
    setStatus("Completa tu nombre y email para reservar.", "error");
    return;
  }

  if (!state.stripeEnabled) {
    setStatus("Stripe no esta configurado todavia en el servidor.", "error");
    return;
  }

  const boatReservations = getBoatReservations(boat.id);
  if (boatReservations[state.selectedDate]) {
    setStatus("Ese dia acaba de ser reservado. Elige otra fecha.", "error");
    renderCalendar();
    return;
  }

  try {
    elements.checkoutButton.disabled = true;
    elements.checkoutButton.textContent = "Redirigiendo a Stripe...";
    setStatus("Preparando el pago seguro...", "");

    const response = await fetch("/api/create-checkout-session", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        boatId: boat.id,
        date: state.selectedDate,
        name,
        email,
      }),
    });

    const payload = await response.json();

    if (!response.ok) {
      throw new Error(payload.error || "No se pudo guardar la reserva");
    }

    window.location.href = payload.url;
  } catch (error) {
    setStatus(error.message || "Ha ocurrido un error al iniciar el pago.", "error");
    refreshAvailability({ silent: true, clearInvalidSelection: false })
      .catch(() => {});
  } finally {
    elements.checkoutButton.disabled = false;
    elements.checkoutButton.textContent = "Reservar y pagar con Stripe";
  }
}

function startAvailabilityRefresh() {
  if (reservationRefreshTimer) {
    clearInterval(reservationRefreshTimer);
  }

  reservationRefreshTimer = window.setInterval(() => {
    refreshAvailability({ silent: true });
  }, AVAILABILITY_REFRESH_MS);

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      refreshAvailability({ silent: true });
    }
  });

  window.addEventListener("focus", () => {
    refreshAvailability({ silent: true });
  });
}

async function init() {
  renderWeekdays();
  renderBoatCards();
  renderSelectedBoat();
  setStatus("Cargando disponibilidad...");

  try {
    await Promise.all([fetchAppConfig(), fetchReservations()]);
    setStatus("");
  } catch (error) {
    setStatus(error.message || "No se pudo iniciar la aplicacion.", "error");
  }

  renderCalendar();
  await handleCheckoutReturn();
  startAvailabilityRefresh();

  elements.prevMonth.addEventListener("click", () => changeMonth(-1));
  elements.nextMonth.addEventListener("click", () => changeMonth(1));
  elements.reservationForm.addEventListener("submit", handleReservationSubmit);
}

init();
