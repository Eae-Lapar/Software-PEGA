document.addEventListener("DOMContentLoaded", () => {
    const header = document.querySelector(".header");
    const menu = get("menuToggle");
    const nav = get("mainNav");

    function closeMenu() {
        menu.setAttribute("aria-expanded", "false");
    }

    function markLocation() {
        const active = location.hash || "#inicio";
        for (const link of nav.querySelectorAll("a[href^='#']")) {
            const target = link.getAttribute("href");
            const current = target === active ||
                (target === "#importacao" && active === "#processamento");
            if (current) link.setAttribute("aria-current", "location");
            else link.removeAttribute("aria-current");
        }
    }

    menu.onclick = () => menu.setAttribute("aria-expanded", String(menu.getAttribute("aria-expanded") !== "true"));
    nav.addEventListener("click", event => { if (event.target.closest("a")) closeMenu(); });
    header.addEventListener("keydown", event => {
        if (event.key === "Escape" && menu.getAttribute("aria-expanded") === "true") {
            closeMenu();
            menu.focus();
        }
    });
    window.addEventListener("hashchange", markLocation);
    markLocation();

    document.querySelectorAll("[data-view]").forEach(button => {
        button.onclick = () => {
            selectTab(get("chartsTab"), true);
            document.dispatchEvent(new CustomEvent("pega:abrir-figuras", {detail: {
                category: button.dataset.view, type: button.dataset.figure
            }}));
        };
    });
});

function showMetrics(data) {
    const exact = pegaLocale.number({maximumSignificantDigits: 21});
    const entries = [
        ["Ano do inventário", String(data.ano)], ["Setor", data.setor], ["Combustível", data.combustivel],
        ["Fontes", exact.format(data.total_fontes)], ["Atividades", exact.format(data.total_atividades)],
        ["Poluentes", exact.format(data.total_poluentes)], ["Registros calculados", exact.format(data.total_registros)],
        ["Consumo energético", exact.format(data.consumo_total_GJ) + " GJ"]
    ];
    get("resultMetrics").replaceChildren(...entries.map(([label, value]) => {
        const card = document.createElement("div");
        const title = document.createElement("dt");
        const amount = document.createElement("dd");
        title.textContent = label;
        amount.textContent = value;
        card.append(title, amount);
        return card;
    }));
}

function analysisState(id, message, type) {
    const badge = document.querySelector(`[data-status="${id}"]`);
    if (!badge) return;
    const state = type === "success" ? "Concluída" : type === "error" ? "Requer atenção" :
        message ? "Em processamento" : "Disponível";
    badge.textContent = state;
    badge.dataset.state = type || (message ? "busy" : "ready");
    const link = document.querySelector(`[data-ready="${id}"]`);
    if (link) link.hidden = type !== "success";
    if (type === "success") document.dispatchEvent(new Event("pega:artefatos"));
}

function enhanceTable(table, fields, rows) {
    const frame = table.parentElement;
    let toolbar = frame.previousElementSibling;
    if (toolbar?.classList.contains("table-toolbar")) toolbar.remove();
    toolbar = document.createElement("div");
    toolbar.className = "table-toolbar";
    frame.before(toolbar);
    const label = table.id === "previewTable" ? "Prévia dos dados" :
        table.closest("details")?.querySelector("summary")?.textContent.trim() ||
        table.closest("section")?.querySelector("h3")?.textContent.trim() || "Resultados";
    frame.tabIndex = 0;
    frame.setAttribute("role", "region");
    frame.setAttribute("aria-label", label);
    const count = document.createElement("span");
    count.setAttribute("role", "status");
    const search = document.createElement("input");
    search.type = "search";
    search.placeholder = "Buscar na tabela";
    search.setAttribute("aria-label", `Buscar em ${label}`);
    const size = document.createElement("select");
    size.setAttribute("aria-label", `Registros por página de ${label}`);
    for (const n of [10, 25, 50, 100]) size.add(new Option(`${n} por página`, String(n), false, n === 50));
    const prev = document.createElement("button");
    const next = document.createElement("button");
    for (const [button, text] of [[prev, "Anterior"], [next, "Próxima"]]) {
        button.type = "button";
        button.className = "button secondary";
        button.textContent = text;
    }
    if (rows.length > 5) toolbar.append(search);
    if (rows.length > 10) toolbar.append(size, prev, next);
    toolbar.append(count);
    const files = {
        emissionSummary: "arquivos/resumo.csv", emissionPreview: "arquivos/emissoes_base.csv",
        usedFactors: "arquivos/fatores_utilizados.csv", speciesSummary: "especiacao/arquivos/resumo_especies.csv",
        speciesProfile: "especiacao/arquivos/perfil_especiacao.csv",
        speciesPreview: "especiacao/arquivos/emissoes_especiadas.csv"
    };
    if (activeResult && files[table.id]) {
        const link = document.createElement("a");
        link.href = `${resultUrl(activeResult)}/${files[table.id]}`;
        link.className = "button secondary";
        link.textContent = "Baixar CSV";
        toolbar.append(link);
    }

    const collator = new Intl.Collator("pt-BR", {numeric: true, sensitivity: "base"});
    const formatted = new Set(["emissions", "massa", "massa_g", "massa_base_g", "original_g", "residuo_g",
        "derivado_g", "consumo", "mapeada", "fora", "boundary", "invalid"]);
    function numeric(field, value) {
        if (typeof value === "number") return value;
        const localized = pegaLocale.numeric(value);
        if (formatted.has(field) && localized !== undefined) return localized;
        if (!formatted.has(field) || value == null || !/^-?\d[\d.,]*(?:e[+-]?\d+)?$/i.test(value)) return NaN;
        return Number(value.replaceAll(".", "").replace(",", "."));
    }
    const headers = [...table.tHead.querySelectorAll("th")];
    let page = 0, key = null, asc = true;
    headers.forEach((header, i) => {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = header.textContent;
        button.title = "Ordenar coluna";
        header.replaceChildren(button);
        button.onclick = () => {
            asc = key === fields[i][0] ? !asc : true;
            key = fields[i][0];
            headers.forEach(h => h.removeAttribute("aria-sort"));
            header.setAttribute("aria-sort", asc ? "ascending" : "descending");
            page = 0;
            render();
        };
    });

    function render() {
        const query = search.value.trim().toLocaleLowerCase("pt-BR");
        const filtered = query ? rows.filter(row => fields.some(([field]) =>
            String(row[field] ?? "").toLocaleLowerCase("pt-BR").includes(query))) : [...rows];
        if (key !== null) filtered.sort((a, b) => {
            const x = a[key], y = b[key];
            const nx = numeric(key, x), ny = numeric(key, y);
            const order = Number.isFinite(nx) && Number.isFinite(ny) ? nx - ny :
                collator.compare(String(x ?? ""), String(y ?? ""));
            return asc ? order : -order;
        });
        const limit = Number(size.value);
        const start = page * limit;
        const visible = filtered.slice(start, start + limit);
        prev.disabled = start === 0;
        next.disabled = start + limit >= filtered.length;
        count.textContent = visible.length
            ? `${start + 1}–${start + visible.length} de ${filtered.length}${query ? ` (${rows.length} na tabela)` : ""}`
            : "Nenhum registro";
        table.tBodies[0].replaceChildren(...visible.map(row => {
            const tr = document.createElement("tr");
            for (const [field] of fields) {
                const cell = tr.insertCell();
                const value = row[field];
                cell.textContent = value ?? "";
                if (Number.isFinite(numeric(field, value))) cell.className = "numeric-cell";
            }
            return tr;
        }));
    }

    for (const input of [search, size]) input.addEventListener(input === search ? "input" : "change", () => { page = 0; render(); });
    prev.onclick = () => { page--; render(); };
    next.onclick = () => { page++; render(); };
    render();
}
