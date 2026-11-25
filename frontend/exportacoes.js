(() => {
    const panel = get("filesPanel");
    const list = get("exportCatalog");
    const selected = new Set();
    const categories = {
        inventario: ["Inventário e emissões", "▤"], especiacao: ["Especiação química", "◇"],
        temporal: ["Distribuição temporal", "◷"], espacial: ["Distribuição espacial", "⌖"],
        figuras: ["Mapas e gráficos", "▧"], modelagem: ["Modelagem atmosférica", "▦"],
        relatorios: ["Relatórios científicos", "▤"]
    };
    const sections = {
        fatores: "Fatores e referências", especiacao: "Especiação química", temporal: "Distribuição temporal",
        espacial: "Distribuição espacial", modelagem: "Modelagem atmosférica"
    };
    const route = () => activeResult ? `${resultUrl(activeResult)}/exportacoes` : "";
    const size = pegaLocale.number({maximumFractionDigits: 2});
    let version = 0, files = [], busy = false, loaded = false;
    let resolution = "300";
    const formats = new Map();
    const variant = item => item.variants?.find(v => v.formato === (formats.get(item.id) || "png") &&
        (v.formato !== "png" || v.nome.includes(`-${resolution}dpi`))) || item;

    function controls() {
        get("exportCount").textContent = `${selected.size} de ${files.length} selecionados`;
        get("exportAll").checked = files.length > 0 && files.every(item => selected.has(item.id));
        get("exportAll").indeterminate = selected.size > 0 && !get("exportAll").checked;
        get("exportAll").disabled = busy || !loaded;
        get("exportZip").disabled = busy || !selected.size;
        get("exportZipAll").disabled = busy || !loaded;
        for (const box of list.querySelectorAll("input,select")) box.disabled = busy;
        for (const box of list.querySelectorAll("input[data-category]")) {
            const group = files.filter(f => f.categoria === box.dataset.category);
            box.checked = group.every(item => selected.has(item.id));
            box.indeterminate = !box.checked && group.some(item => selected.has(item.id));
        }
        for (const box of list.querySelectorAll("input[data-id]")) box.checked = selected.has(box.dataset.id);
    }

    function set(items, checked) {
        for (const item of items) {
            if (checked) selected.add(item.id);
            else selected.delete(item.id);
        }
        controls();
    }

    function show(items, url) {
        list.replaceChildren();
        for (const [category, [name]] of Object.entries(categories)) {
            const group = items.filter(item => item.categoria === category);
            if (!group.length) continue;
            const section = document.createElement("section");
            section.className = "export-group";
            const heading = document.createElement("h3");
            heading.textContent = name;
            const select = document.createElement("label");
            const all = document.createElement("input");
            all.type = "checkbox";
            all.dataset.category = category;
            all.addEventListener("change", () => set(group, all.checked));
            select.append(all, ` Selecionar ${name.toLowerCase()}`);
            section.append(heading, select);
            if (category === "figuras") {
                const quality = document.createElement("select");
                for (const dpi of ["300", "600"]) quality.add(new Option(dpi + " DPI", dpi, false, dpi === resolution));
                const field = document.createElement("label");
                field.className = "export-resolution";
                field.append("Resolução PNG ", quality);
                section.append(field);
                quality.onchange = () => {
                    resolution = quality.value;
                    section.querySelectorAll("select[data-format]").forEach(select => select.dispatchEvent(new Event("change")));
                };
            }
            for (const item of group) {
                const row = document.createElement("div");
                row.className = "export-file";
                const checkbox = document.createElement("input");
                checkbox.type = "checkbox";
                checkbox.dataset.id = item.id;
                checkbox.setAttribute("aria-label", `Selecionar ${item.titulo} · ${item.formato.toUpperCase()}`);
                checkbox.addEventListener("change", () => set([item], checkbox.checked));
                const label = document.createElement("div");
                const title = document.createElement("strong");
                const badge = document.createElement("span");
                badge.className = "format-badge";
                badge.textContent = item.formato.toUpperCase();
                title.textContent = item.titulo;
                const detail = document.createElement("small");
                const availability = item.sob_demanda ? "Gerado sob demanda" : item.bytes < 1024
                    ? `${item.bytes} B` : item.bytes < 1024 ** 2
                        ? `${size.format(item.bytes / 1024)} KiB` : `${size.format(item.bytes / 1024 ** 2)} MiB`;
                label.append(badge, title, detail);
                const link = document.createElement("a");
                link.className = "button secondary";
                link.textContent = "Baixar";
                const updateLink = () => {
                    const file = variant(item);
                    badge.textContent = file.formato.toUpperCase();
                    detail.textContent = `${item.descricao} ${file.formato.toUpperCase()} · ${availability}`;
                    link.setAttribute("aria-label", `Baixar ${item.titulo.toLowerCase()} (${file.formato.toUpperCase()})`);
                    link.href = `${url}/arquivo/${file.id.split("/").map(encodeURIComponent).join("/")}`;
                    link.download = file.nome;
                };
                if (item.variants) {
                    const format = document.createElement("select");
                    format.dataset.format = item.id;
                    format.setAttribute("aria-label", "Formato da figura");
                    for (const value of ["png", "pdf", "svg"]) format.add(new Option(value.toUpperCase(), value));
                    format.value = formats.get(item.id) || "png";
                    format.onchange = () => { formats.set(item.id, format.value); updateLink(); };
                    label.append(format);
                }
                updateLink();
                row.append(checkbox, label, link);
                section.append(row);
            }
            list.append(section);
        }
        controls();
    }

    function reportOptions(data) {
        const pollutant = get("exportPollutants");
        const section = get("exportSections");
        pollutant.replaceChildren(...data.poluentes.map(p => new Option(p, p, true, true)));
        const available = new Set(data.arquivos.map(item => item.categoria));
        section.replaceChildren(...Object.entries(sections)
            .filter(([key]) => key === "fatores" || available.has(key))
            .map(([key, name]) => new Option(name, key, true, true)));
        const territory = get("exportTerritory");
        territory.replaceChildren(new Option("Brasil", "brasil:"));
        for (const level of ["regiao", "uf"]) {
            for (const [code, name] of Object.entries(data.territorios[level])) {
                territory.add(new Option(name, `${level}:${code}`));
            }
        }
        get("exportMapLabel").hidden = !data.arquivos.some(i => i.id === "espacial/original-metadados.json");
        get("exportMap").checked = false;
        updateReport();
    }

    function updateReport() {
        const full = get("exportMode").value === "completo";
        get("exportSectionsLabel").hidden = !full;
        const names = full ? [...get("exportSections").selectedOptions].map(option => option.text) : [];
        if (get("exportChart").checked) names.push("gráfico por poluente");
        if (get("exportMap").checked) names.push(`mapa · ${get("exportTerritory").selectedOptions[0].text}`);
        get("exportTerritoryLabel").hidden = !get("exportMap").checked;
        get("exportReportPreview").textContent =
            `Capa, identificação, metodologia, totais e alertas${names.length ? ", " + names.join(", ") : ""}.`;
    }

    async function load() {
        const url = route();
        if (!url || panel.hidden || loaded) return;
        const current = ++version;
        try {
            const data = await api(url);
            if (current !== version || url !== route()) return;
            const first = !loaded;
            loaded = true;
            const groups = new Map();
            files = data.arquivos.flatMap(item => {
                if (item.categoria !== "figuras") return [item];
                const id = item.nome.replace(/(?:-(?:300|600)dpi)?\.(?:png|pdf|svg)$/, "");
                if (groups.has(id)) { groups.get(id).variants.push(item); return []; }
                const group = {...item, id, titulo: item.titulo.replace(/ · \d+ DPI$/, ""), variants: [item]};
                groups.set(id, group);
                return [group];
            });
            for (const id of selected) if (!files.some(item => item.id === id)) selected.delete(id);
            show(files, url);
            if (first) reportOptions(data);
            get("exportActions").hidden = get("exportReport").hidden = false;
        } catch (error) {
            if (current === version) status("exportStatus", error.message, "error");
        }
    }

    const filtered = get("filteredFigureDownloads");
    const maps = get("spatialMapDownloads");
    function showFilteredFigures() {
        get("activeFigureExports").hidden = filtered.hidden && maps.hidden;
    }
    document.addEventListener("pega:figure-exports", ({detail}) => {
        filtered.replaceChildren(...detail.map(({url, label}) => {
            const link = document.createElement("a");
            link.className = "button secondary";
            link.href = url;
            link.textContent = label;
            return link;
        }));
        filtered.hidden = !detail.length;
        showFilteredFigures();
    });
    new MutationObserver(showFilteredFigures).observe(maps, {attributes: true, attributeFilter: ["hidden"]});

    function download(url, filename) {
        const link = document.createElement("a");
        link.href = url;
        link.download = filename;
        link.click();
    }

    async function batch(complete) {
        const url = route();
        const run = activeResult;
        const token = crypto.randomUUID();
        const progress = get("exportProgress");
        let finished = false;
        busy = true;
        controls();
        progress.hidden = false;
        progress.removeAttribute("value");
        status("exportStatus", "Preparando ZIP…");
        async function poll() {
            while (!finished && url === route()) {
                await new Promise(resolve => setTimeout(resolve, 450));
                if (finished || url !== route()) break;
                try {
                    const job = await api(`${url}/lotes/${token}`);
                    if (finished || url !== route()) break;
                    progress.max = job.total;
                    progress.value = job.concluidos;
                    status("exportStatus", `${job.concluidos} de ${job.total} arquivos. ${job.atual}`);
                } catch { /* A primeira consulta pode preceder a reserva do lote. */ }
            }
        }
        poll();
        try {
            const result = await api(`${url}/lotes`, {method: "POST", headers: {"Content-Type": "application/json"},
                body: JSON.stringify({token,
                    arquivos: complete ? null : files.filter(item => selected.has(item.id)).map(item => variant(item).id),
                    variantes: complete ? Object.fromEntries(files.filter(item => item.variants)
                        .map(item => [item.id, variant(item).id])) : {}})});
            if (url !== route()) return;
            download(`${url}/lotes/${token}/zip`, `PEGA-${run}.zip`);
            const omitted = result.omitidos.map(item => `${item.titulo}: ${item.motivo}`).join(" ");
            status("exportStatus", `ZIP pronto com ${result.incluidos.length} arquivos. Consulte o manifesto para ver a lista.${omitted ? ` Omitidos: ${omitted}` : ""}`, omitted ? "" : "success");
        } catch (error) {
            if (url === route()) status("exportStatus", error.message, "error");
        } finally {
            finished = true;
            busy = false;
            progress.hidden = true;
            controls();
        }
    }

    get("exportAll").addEventListener("change", event => set(files, event.target.checked));
    get("exportZip").addEventListener("click", () => batch(false));
    get("exportZipAll").addEventListener("click", () => batch(true));
    get("exportReport").addEventListener("change", updateReport);
    get("exportReport").addEventListener("submit", async event => {
        event.preventDefault();
        const url = route();
        const button = get("exportPdf");
        const modo = get("exportMode").value;
        const [nivel, codigo] = get("exportMap").checked ? get("exportTerritory").value.split(":") : ["brasil", ""];
        const values = id => [...get(id).selectedOptions].map(option => option.value);
        button.disabled = true;
        status("exportStatus", "Gerando relatório…");
        try {
            const response = await fetch(`${url}/relatorio`, {method: "POST",
                headers: {"Content-Type": "application/json"}, body: JSON.stringify({
                    modo, nivel, codigo, idioma: get("exportLanguage").value, unidade: get("exportUnit").value,
                    poluentes: values("exportPollutants"), secoes: values("exportSections"),
                    grafico: get("exportChart").checked, mapa: get("exportMap").checked
                })});
            if (!response.ok) throw new Error((await response.json()).detail || "Relatório indisponível.");
            const blob = await response.blob();
            if (url !== route()) return;
            const object = URL.createObjectURL(blob);
            download(object, modo === "completo" ? "relatorio-cientifico.pdf" : "resumo-executivo.pdf");
            setTimeout(() => URL.revokeObjectURL(object), 3000);
            status("exportStatus", "Relatório pronto. Download solicitado.", "success");
        } catch (error) {
            if (url === route()) status("exportStatus", error.message, "error");
        } finally {
            button.disabled = false;
        }
    });
    document.addEventListener("pega:result", () => {
        loaded = false;
        selected.clear();
        files = [];
        list.replaceChildren();
        get("exportActions").hidden = get("exportReport").hidden = true;
        status("exportStatus");
        load();
    });
    new MutationObserver(() => {
        if (!panel.hidden) {
            load();
        }
    }).observe(panel, {attributes: true, attributeFilter: ["hidden"]});
    document.addEventListener("pega:artefatos", () => { loaded = false; load(); });
})();
