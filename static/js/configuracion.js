window.licitapro = window.licitapro || {};

licitapro.alternarModulo = function (boton) {
    const modulo = boton.closest(".matriz-permisos__modulo");
    const casillas = modulo.querySelectorAll('input[type="checkbox"]');
    const todasMarcadas = Array.from(casillas).every((casilla) => casilla.checked);
    casillas.forEach((casilla) => {
        casilla.checked = !todasMarcadas;
    });
};
