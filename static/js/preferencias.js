window.licitapro = window.licitapro || {};

const LICITAPRO_DENSIDADES = ["compacta", "normal", "comoda"];

/* Aplica al instante en el DOM (cero parpadeo en la próxima carga porque
 * el servidor ya renderiza el atributo) y persiste en segundo plano. */
licitapro.aplicarPreferencia = function (campo, atributoDom, valor) {
    document.documentElement.setAttribute("data-" + atributoDom, valor);
    htmx.ajax("POST", "/preferencias/", { values: { campo: campo, valor: valor }, swap: "none" });
};

licitapro.alternarTema = function () {
    const actual = document.documentElement.dataset.tema;
    licitapro.aplicarPreferencia("tema", "tema", actual === "oscuro" ? "claro" : "oscuro");
};

licitapro.ciclarDensidad = function () {
    const actual = document.documentElement.dataset.densidad;
    const siguiente = LICITAPRO_DENSIDADES[(LICITAPRO_DENSIDADES.indexOf(actual) + 1) % LICITAPRO_DENSIDADES.length];
    licitapro.aplicarPreferencia("densidad", "densidad", siguiente);
};

licitapro.cambiarVista = function (valor) {
    licitapro.aplicarPreferencia("vista_preferida", "vista", valor);
};

licitapro.csrfToken = function () {
    try {
        return JSON.parse(document.body.getAttribute("hx-headers"))["X-CSRFToken"];
    } catch (e) {
        return "";
    }
};

licitapro.avisoFlash = function (mensaje, tipo) {
    const contenedor = document.querySelector(".contenido");
    const aviso = document.createElement("div");
    aviso.className = "mensajes";
    aviso.innerHTML = `<div class="mensaje ${tipo || "error"}">${mensaje}</div>`;
    contenedor.prepend(aviso);
    setTimeout(() => aviso.remove(), 4000);
};
