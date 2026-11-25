(() => {
    const category = get("figureCategory");
    const type = get("figureType");
    const base = get("figureBase");
    const series = get("figureSeries");
    const unit = get("figureUnit");
    const territory = get("figureTerritory");
    const image = get("figureImage");
    const fields = {
        Scale: "escala", Palette: "paleta", Locale: "idioma", Order: "ordem", Top: "top",
        Start: "inicio", End: "fim", CompareStart: "comparar_inicio", CompareEnd: "comparar_fim"
    };
    const emissions = [
        ["totais", "Totais por poluente"], ["fontes", "Ranking por fonte"],
        ["participacao", "Participação das fontes"], ["acumulada", "Emissão acumulada das fontes"],
        ["distribuicao", "Distribuição entre fontes"], ["uf", "Emissões por UF"], ["regiao", "Emissões por região"]
    ];
    const chemistry = [["balanco", "Balanço de massa"], ["especies", "Massa por espécie"], ["perfil", "Frações do perfil"]];
    const relative = [["horario", "Perfil horário"], ["semanal", "Perfil semanal"],
        ["combinado", "Perfil de 168 horas"], ["calor", "Mapa de calor relativo"]];
    const annual = [["mensal", "Massas mensais"], ["diario", "Massas diárias"], ["horas", "Acumulados por hora do dia"],
        ["serie-anual", "Série anual"], ["calendario", "Calendário de massas diárias"]];
    const spatial = [["grade-wrf", "Massa por célula WRF"], ["dominio-wrf", "Domínio computacional WRF"]];
    let data, version = 0, drawVersion = 0, currentImage, currentQuery, pending;

    function fill(select, items) {
        const previous = select.value;
        select.replaceChildren(...items.map(([value, label]) => new Option(label, value)));
        if (items.some(([value]) => value === previous)) select.value = previous;
    }

    function clearPreview() {
        ++drawVersion;
        pending?.abort();
        get("figurePreview").hidden = true;
        get("figurePreview").removeAttribute("aria-busy");
        get("figureFiles").hidden = true;
        image.removeAttribute("src");
        if (currentImage) URL.revokeObjectURL(currentImage);
        currentImage = null;
        currentQuery = null;
        downloads();
        if (get("figureDialog").open) get("figureDialog").close();
        get("figureDialog").querySelector("img").removeAttribute("src");
    }

    const endpoint = () => `${resultUrl(activeResult)}/visualizacoes`;
    const chartUrl = (format, params) => `${endpoint()}/figura.${format}?${params}`;
    const label = (name, visible) => { get(`figure${name}Label`).hidden = !visible; };

    async function draw() {
        if (!data || get("figureControls").hidden) return;
        const revision = ++drawVersion;
        pending?.abort();
        currentQuery = null;
        downloads();
        controls.save.disabled = controls.zoom.disabled = true;
        get("figurePreview").setAttribute("aria-busy", "true");
        pending = new AbortController();
        pegaLocale.defaultFigureLanguage("figureLocale");
        const selected = !get("figureSeriesLabel").hidden && series.value ? JSON.parse(series.value) : ["", ""];
        const [nivel, codigo] = get("figureTerritoryLabel").hidden ? ["brasil", ""] : territory.value.split(":");
        const params = new URLSearchParams({tipo: type.value, origem: base.value || "original",
            pol_origem: selected[0], pol: selected[1], nivel, codigo,
            unidade: get("figureUnitLabel").hidden ? "g" : unit.value, dpi: "100"});
        for (const [name, key] of Object.entries(fields)) {
            if (!get(`figure${name}Label`)?.hidden && get(`figure${name}`).value) {
                params.set(key, get(`figure${name}`).value);
            }
        }
        status("figureStatus", currentImage
            ? "Atualizando a visualização. A imagem anterior permanece visível durante a geração."
            : "Gerando visualização científica…");
        try {
            const response = await fetch(chartUrl("png", params), {cache: "no-store", signal: pending.signal});
            if (!response.ok) {
                const message = await response.json().catch(() => ({}));
                throw new Error(typeof message.detail === "string" ? message.detail : "Figura indisponível para esta seleção.");
            }
            const blob = await response.blob();
            if (revision !== drawVersion) return;
            if (currentImage) URL.revokeObjectURL(currentImage);
            currentImage = URL.createObjectURL(blob);
            image.src = currentImage;
            image.alt = type.selectedOptions[0].textContent;
            currentQuery = params;
            get("figureCaption").textContent = data.modelos[base.value]?.calendario &&
                [...annual, spatial[0]].some(([value]) => value === type.value)
                ? `Massa acumulada por intervalo · ${data.modelos[base.value].calendario.convencao}` : image.alt;
            get("figurePreview").hidden = false;
            get("figureFiles").hidden = false;
            controls.save.disabled = controls.zoom.disabled = false;
            downloads();
            status("figureStatus");
        } catch (error) {
            if (revision === drawVersion) status("figureStatus",
                currentImage ? `${error.message} A imagem exibida é da configuração anterior.` : error.message, "error");
        } finally {
            if (revision === drawVersion) get("figurePreview").removeAttribute("aria-busy");
        }
    }

    function downloadUrl(format, dpi) {
        if (!currentQuery) return;
        const params = new URLSearchParams(currentQuery);
        params.set("download", "true");
        params.set("dpi", dpi);
        return chartUrl(format, params);
    }

    function downloads() {
        const links = currentQuery ? ["png", "pdf", "svg"].map(format => ({
            url: downloadUrl(format, controls.dpi.value),
            label: `Baixar gráfico filtrado (${format.toUpperCase()}${format === "png" ? `, ${controls.dpi.value} DPI` : ""})`
        })) : [];
        document.dispatchEvent(new CustomEvent("pega:figure-exports", {detail: links}));
    }

    function filters() {
        const group = category.value;
        const model = data.modelos[base.value];
        const t = type.value;
        const temporal = relative.some(([key]) => key === t);
        const projection = annual.some(([key]) => key === t);
        const seriesData = group === "especiacao" ? data.quimica.map(pol => [pol, pol])
            : projection || t === "grade-wrf" ? model?.series || [] : data.series[base.value] || [];
        fill(series, seriesData.map(([origin, pol]) => [JSON.stringify([origin, pol]),
            pol === origin ? pol : `${pol} ← ${origin}`]));
        fill(unit, [...(temporal ? [["%", "%"]] : t === "especies" ? [["%", "% da massa original"]] : t === "acumulada" ? [["%", "% da seleção"]] : []), ...["g", "kg", "t"].map(u => [u, u])]);
        label("Series", t !== "totais" && t !== "dominio-wrf" && (!temporal || unit.value !== "%"));
        label("Unit", !["participacao", "perfil", "dominio-wrf"].includes(t));
        label("Territory", group === "emissoes");
        label("Scale", !["balanco", "perfil", "calor", "calendario", "dominio-wrf", "acumulada"].includes(t));
        label("Order", ["totais", "fontes", "participacao", "uf", "regiao"].includes(t));
        label("Top", ["fontes", "participacao"].includes(t));
        const period = projection || (t === "grade-wrf" && model?.calendario);
        for (const name of ["Start", "End", "CompareStart", "CompareEnd"]) {
            const comparing = name.startsWith("Compare");
            label(name, period && (!comparing || (projection && t !== "calendario")));
            get(`figure${name}`).min = `${data.ano}-01-01`;
            get(`figure${name}`).max = `${data.ano}-12-31`;
        }
        draw();
    }

    function layout() {
        if (!data || get("chartsPanel").hidden) return;
        const group = category.value;
        const available = Object.keys(data.series);
        const maps = data.espaciais.length
            ? [["mapa-interativo", "Mapa interativo"], ["mapa-cientifico", "Mapa científico"]] : [];
        const sources = group === "temporal" ? available.filter(o => data.temporais.includes(o) || data.modelos[o]?.calendario)
            : group === "espacial" ? available.filter(o => data.modelos[o]) : available;
        fill(base, sources.map(o => [o, o === "original" ? "Original" : "Especiada"]));
        label("Base", group !== "especiacao" && sources.length > 1);
        const types = group === "emissoes" ? emissions : group === "especiacao" ? chemistry : group === "espacial"
            ? [...maps, ...(data.modelos[base.value] ? spatial : [])]
            : [...(data.temporais.length ? [["interativo", "Perfis relativos interativos"]] : []),
                ...(data.temporais.includes(base.value) ? relative : []),
                ...(data.modelos[base.value]?.calendario ? annual : [])];
        fill(type, types);
        if (requestedFigure && types.some(([value]) => value === requestedFigure)) type.value = requestedFigure;
        requestedFigure = null;

        const mapSelected = maps.some(([value]) => value === type.value);
        const existing = mapSelected || type.value === "interativo";
        get("relativeFigures").hidden = type.value !== "interativo";
        get("spatialFigures").hidden = !mapSelected;
        if (mapSelected) document.dispatchEvent(new CustomEvent("pega:mapa", {detail: type.value}));
        get("figureControls").hidden = !type.value || (existing && types.length <= 1);
        get("figureControls").classList.toggle("figure-selection-only", existing);
        if (existing) label("Base", false);
        if (existing) {
            clearPreview();
            status("figureStatus");
        } else if (type.value) {
            filters();
        }
    }

    async function load() {
        if (!activeResult || get("chartsPanel").hidden || data) return;
        const current = ++version;
        try {
            const info = await api(endpoint());
            if (current !== version) return;
            data = info;
            category.querySelector('[value="especiacao"]').hidden = !data.quimica.length;
            category.querySelector('[value="temporal"]').hidden = !data.temporais.length &&
                !Object.values(data.modelos).some(model => model.calendario);
            category.querySelector('[value="espacial"]').hidden = !data.espaciais.length && !Object.keys(data.modelos).length;
            if (category.selectedOptions[0].hidden) category.value = "emissoes";
            const areas = [["brasil:", "Brasil"]];
            for (const level of ["regiao", "uf"]) {
                for (const [code, name] of Object.entries(data.territorios[level])) areas.push([`${level}:${code}`, name]);
            }
            fill(territory, areas);
            if (requestedCategory && !category.querySelector(`[value="${requestedCategory}"]`)?.hidden) {
                category.value = requestedCategory;
            }
            requestedCategory = null;
            layout();
        } catch (error) {
            if (current !== version) return;
            get("figureControls").hidden = false;
            status("figureStatus", error.message, "error");
        }
    }

    let requestedCategory, requestedFigure;
    document.addEventListener("pega:abrir-figuras", ({detail}) => {
        requestedFigure = detail.type;
        if (data) {
            category.value = detail.category;
            layout();
        } else {
            requestedCategory = detail.category;
            load();
        }
    });
    document.addEventListener("pega:artefatos", () => { data = null; load(); });

    category.addEventListener("change", layout);
    base.addEventListener("change", layout);
    type.addEventListener("change", layout);
    unit.addEventListener("change", filters);
    for (const control of [series, territory, ...Object.keys(fields).map(key => get(`figure${key}`))]) {
        control.addEventListener("change", draw);
    }
    const controls = imageExportControls("figure", () => {
        const dialog = get("figureDialog");
        dialog.querySelector("img").src = currentImage;
        dialog.showModal();
    }, (format, dpi) => {
        const url = downloadUrl(format, dpi);
        if (url) requestImageDownload(url);
    });
    controls.dpi.addEventListener("change", downloads);
    document.addEventListener("pega:result", () => {
        ++version;
        requestedCategory = null;
        requestedFigure = null;
        data = null;
        clearPreview();
        for (const name of ["Start", "End", "CompareStart", "CompareEnd"]) get(`figure${name}`).value = "";
        load();
    });
    new MutationObserver(load).observe(get("chartsPanel"), {attributes: true, attributeFilter: ["hidden"]});
})();
