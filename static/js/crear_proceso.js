window.licitapro = window.licitapro || {};

licitapro.buscarEntidad = function (input) {
    const termino = input.value;
    const contenedor = document.getElementById("entidad-opciones");
    document.getElementById("id-entidad-valor").value = "";

    if (!termino) {
        contenedor.innerHTML = "";
        return;
    }

    fetch(`/entidades/seleccionar/?q=${encodeURIComponent(termino)}`)
        .then((respuesta) => respuesta.text())
        .then((html) => {
            contenedor.innerHTML = html;
        });
};

licitapro.seleccionarEntidad = function (id, nombre) {
    document.getElementById("id-entidad-valor").value = id;
    document.getElementById("id-entidad-busqueda").value = nombre;
    document.getElementById("entidad-opciones").innerHTML = "";
};
