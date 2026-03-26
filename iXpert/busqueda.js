const pageGroups = [
    {
        keywords: ["pin", "ping", "pim", "pink", "pimg", "pimk", "activar pin", "token", "iToken", "tiktoken", "toquen", "toke"],
        title: "Activar PIN & iToken",
        description: "Para realizar transacciones seguras, necesitarás tu PIN de Transacción y el iToken para mayor seguridad.",
        link: "tuto4.html"
    },
        {
        keywords: ["pin", "ping", "pim", "pink", "pimg", "pimk", "activar pin", "tx", "token", "iToken", "tiktoken", "toquen", "toke"],
        title: "Guía de Activación ",
        description: "Filtros y procesos de Activación de PIN de Transacción.",
        link: "varios/pinactivate.html"
    },
    {
        keywords: ["excepcion", "excepción", "Excepcional", "ecepcion", "exepcion"],
        title: "iToken Excepcional",
        description: "Proceos para excepcionar la carga del iToken.",
        link: "bpm_excepcional.html"
    },
    {
        keywords: ["devolución", "devolucion", "devolver", "debolucion"],
        title: "Devolución Online",
        description: "Verificar si una transacción corresponde a una devolución online y confirmar el comercio asociado.",
        link: "tuto5.html"
    },
    {
        keywords: ["duplicado", "doble"],
        title: "Pago Duplicado TC",
        description: "Pago doble de TC habiendo ya un débito automático",
        link: "tuto6.html"
    },
    {
        keywords: ["delivery", "tracking", "traking", "currier"],
        title: "Tracking de envíos",
        description: "Es el seguimiento en tiempo real del estado y ubicación de una Tarjeta Física hasta su entrega.",
        link: "tuto7.html"
    },
    {
        keywords: ["contrakargo", "contracargo"],
        title: "Contracargo",
        description: "Es cuando un cliente no reconoce un cargo en su tarjeta de crédito o débito.",
        link: "tuto8.html"
    },
    {
        keywords: ["cta", "cuenta", "salario", "PGS", "Ahorro", "prestamo", "préstamos", "mantenimiento"],
        title: "Cuentas Bancarias",
        description: "Una cuenta bancaria es un servicio que te permite guardar tu dinero y hacer operaciones como pagos, depósitos o transferencias.",
        link: "tuto9.html"
    },
    {
        keywords: ["intervale"],
        title: "Cuentas Bancarias",
        description: "Una cuenta bancaria es un servicio que te permite guardar tu dinero y hacer operaciones como pagos, depósitos o transferencias.",
        link: "intervale.html"
    },
    {
        keywords: ["tarifario"],
        title: "Cuentas Bancarias",
        description: "Una cuenta bancaria es un servicio que te permite guardar tu dinero y hacer operaciones como pagos, depósitos o transferencias.",
        link: "tarifario.html"
    },
    {
        keywords: ["sac.com", "saccom", "sac"],
        title: "SAC.COM",
        description: "Plataforma principal del SAC.",
        link: "saccom.html"
    },
    {
        keywords: ["bancard"],
        title: "Bancard",
        description: "Plataforma de gestión Bancard.",
        link: "bancard.html"
    },
    {
        keywords: ["alias", "alías", "alas", "alia"],
        title: "Alias Itaú",
        description: "Paso a paso para activar tu Alias.",
        link: "alias.html"
    },
    {
        keywords: ["resumen"],
        title: "Resumen TC",
        description: "Resumen de TC online.",
        link: "resumentc.html"
    },
        {
        keywords: ["tipificacion","tipificación","registro","registros","tipificaciones","codificación","tipificar","tipificado","registrar"],
        title: "Registros",
        description: "Proceso de registros",
        link: "tipificaciones.html"
    },
        {
        keywords: ["mat", "matriz", "gestionessihb"],
        title: "MAT SIHB",
        description: "Gestiones del Área",
        link: "sihb/Matriz_Soporte.html"
    },
        {
        keywords: ["mat", "matriz", "gestionescib"],
        title: "MAT CIB",
        description: "Gestiones del Área",
        link: "sihb/Matriz_CIB.html"
    },
        {
        keywords: ["programada", "transferencia", "cancelar"],
        title: "Cancelar Transferencia Programada",
        description: "Como realizar los pasos para cancelar una transferencia programada",
        link: "varios/cancelartransferencia.html"
    },
        {
        keywords: ["pix", "pic", "PIX"],
        title: "QR PIX",
        description: "Funcionamiento QR PIX",
        link: "varios/qrpix.html"
    },
        {
        keywords: ["nps", "NPS", "calculadora"],
        title: "Calculadora NPS",
        description: "Calcula tu NPS",
        link: "varios/Calculadora_NPS 2.0.html"
    },
        {
        keywords: ["extracto", "resumen", "Extracto"],
        title: "Resumen de Extracto vía Mail",
        description: "Pasos para abrir el resumen de extractos por mail",
        link: "varios/extractoxmail.html"
    },
        {
        keywords: ["anulaciones", "confirmaciones", "anulaciones y confirmaciones"],
        title: "Proceso de Anulación y Confirmación",
        description: "Pronet, Netel, Bancard",
        link: "sihb/anulacionesyconfirmaciones.html"
    },
        {
        keywords: ["retención", "retencion", "reubicación", "reubicar", "reubicacion"],
        title: "Retención y Reubicación",
        description: "Proceso en un solo flujo",
        link: "varios/retencionyreubicacion.html"
    },
        {
        keywords: ["cnb", "agencias", "snb", "cnv", "seenebe"],
        title: "CNBs",
        description: "Direcciones y horarios.",
        link: "varios/cnb.html"
    },
        {
        keywords: ["game","Trivia","trivia"],
        title: "Trivia",
        description: "Mide tu capacidad de conocimiento.",
        link: "varios/game1.html"
    },
        {
        keywords: ["aumento","AUMENTO","Aumento","aumentar"],
        title: "Aumento de línea TC",
        description: "Verificación del proceso de aumento de línea en TC.",
        link: "varios/aumentolineatc.html"
    },
        {
        keywords: ["extracto", "descargar", "Extracto"],
        title: "Descargar Extracto TC",
        description: "Como realizar descargas de extractos desde la web",
        link: "varios/extractotc.html"
    }
];
document.querySelector(".search-bar form").addEventListener("submit", function(e) {
    e.preventDefault();

    const query = document.getElementById("searchInput").value.toLowerCase();
    const resultContainer = document.getElementById("results");

    resultContainer.innerHTML = "";

    let found = false;

    for (const page of pageGroups) {
        if (page.keywords.some(keyword => keyword.includes(query))) {
            found = true;

            const card = document.createElement("div");
            card.className = "result-card";
            card.innerHTML = `
                <h3>${page.title}</h3>
                <p>${page.description}</p>
                <a href="${page.link}" class="button">Ver más</a>
            `;
            resultContainer.appendChild(card);
        }
    }

    if (!found) {
        resultContainer.innerHTML = "<p>No se encontraron resultados para: " + query + "</p>";
    }
});