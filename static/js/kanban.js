document.addEventListener("DOMContentLoaded", function () {
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

    fetch(`/procesos/${procesoId}/mover/${estadoDestino}/`, {
        method: "POST",
        headers: { "X-CSRFToken": licitapro.csrfToken() },
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
