window.licitapro = window.licitapro || {};

/* Detecta un "@token" justo antes del cursor y pide sugerencias al backend.
 * Vive fuera de HTMX porque necesita la posición del cursor, no solo el
 * valor del campo. */
licitapro.actualizarMencion = function (textarea) {
    const cursor = textarea.selectionStart;
    const antesDelCursor = textarea.value.slice(0, cursor);
    const match = antesDelCursor.match(/@([\w.]*)$/);
    const contenedor = document.getElementById("mencion-sugerencias");

    if (!match) {
        contenedor.innerHTML = "";
        return;
    }

    fetch(`/social/usuarios/autocompletar/?q=${encodeURIComponent(match[1])}`)
        .then((respuesta) => respuesta.text())
        .then((html) => {
            contenedor.innerHTML = html;
        });
};

licitapro.insertarMencion = function (username, textareaId) {
    const textarea = document.getElementById(textareaId);
    const cursor = textarea.selectionStart;
    const antes = textarea.value.slice(0, cursor).replace(/@([\w.]*)$/, `@${username} `);
    const despues = textarea.value.slice(cursor);

    textarea.value = antes + despues;
    document.getElementById("mencion-sugerencias").innerHTML = "";
    textarea.focus();
};
