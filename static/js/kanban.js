document.addEventListener("DOMContentLoaded", function () {
    const tablero = document.querySelector(".tablero");
    if (!tablero || tablero.dataset.puedeMover !== "1") {
        /* Sin mover_etapa: ni siquiera se inicializa SortableJS — las
         * tarjetas no son arrastrables. El servidor igual rechaza el
         * endpoint si alguien lo llama directo (ver procesos/views.py). */
        return;
    }
    document.querySelectorAll(".tablero__cuerpo").forEach(function (columna) {
        new Sortable(columna, {
            group: "kanban",
            animation: 150,
            ghostClass: "fantasma-arrastre",
            dragClass: "arrastrando",
            onEnd: manejarSoltarTarjeta,
        });
    });
});

function manejarSoltarTarjeta(evt) {
    if (evt.to === evt.from) return;

    const tarjeta = evt.item;
    const procesoId = tarjeta.dataset.tarjetaProceso;
    const estadoDestino = evt.to.dataset.columnaEstado;
    let transiciones = {};
    try {
        transiciones = JSON.parse(tarjeta.dataset.transiciones || "{}");
    } catch (e) { /* deja transiciones vacío */ }

    const revertir = function (mensaje) {
        evt.from.insertBefore(tarjeta, evt.from.children[evt.oldIndex] || null);
        if (mensaje) licitapro.avisoFlash(mensaje, "error");
    };

    /* Primer chequeo: el mapa ya lo calculó el servidor al renderizar la
     * tarjeta. Si el destino no está ahí, ni siquiera pegamos al backend. */
    if (!transiciones[estadoDestino]) {
        revertir("Esa transición no está permitida desde el estado actual.");
        return;
    }

    /* Descartar exige un motivo, igual que en el statusbar del detalle —
     * el drag&drop no puede saltarse esa exigencia solo por ser más rápido. */
    let cuerpo = {};
    if (transiciones[estadoDestino] === "descartar") {
        const motivo = window.prompt("Motivo del descarte:");
        if (!motivo || !motivo.trim()) {
            revertir(motivo === null ? null : "Se requiere un motivo para descartar.");
            return;
        }
        cuerpo = { motivo: motivo.trim() };
    }

    fetch(`/procesos/${procesoId}/mover/${estadoDestino}/`, {
        method: "POST",
        headers: {
            "X-CSRFToken": licitapro.csrfToken(),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        body: new URLSearchParams(cuerpo),
    })
        .then((r) => r.json().then((datos) => ({ ok: r.ok, datos })))
        .then(({ ok, datos }) => {
            if (!ok || !datos.ok) {
                revertir((datos && datos.error) || "No se pudo mover el proceso.");
            } else {
                /* Recarga simple: los contadores/sumas/distribución de cada
                 * columna son agregados del servidor, no vale la pena
                 * reimplementarlos en JS solo para este caso. */
                window.location.reload();
            }
        })
        .catch(function () {
            revertir("Error de red al mover el proceso.");
        });
}
