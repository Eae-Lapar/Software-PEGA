(() => {
    const source = get("spatialSource");
    const series = get("spatialSeries");
    const tableSeries = get("spatialTableSeries");
    const mode = get("spatialMode");
    const map = get("spatialMap");
    const level = get("spatialLevel");
    const territory = get("spatialTerritory");
    const marker = get("spatialSize");
    const layers = {estados: "showStates", regioes: "showRegions", pontos: "showPoints",
        territorial: "showTerritorial", calor: "showHeat", grade: "showGrid"};
    const units = {g: 1, kg: .001, t: .000001};
    const percentage = new Intl.NumberFormat("pt-BR", {maximumFractionDigits: 2});
    const settings = {
        unidade: get("spatialUnit"), paleta: get("spatialPalette"), escala: get("spatialScale"),
        idioma: get("spatialLanguage"), dpi: get("spatialDpi"), escopo: get("spatialScope")
    };
    let result;
    let states;
    let version = 0;
    let chartVersion = 0;
    let tableVersion = 0;
    let viewer, lastSelection;

    const territorialSelection = () => level.value === "brasil" ? "" : territory.value;
    const territorioUrl = (id, params) => `${endpoint()}/territorio/${id}?${params}`;
    const capture = () => Object.fromEntries(Object.entries(layers).map(([k, v]) => [k, get(v).checked]));

    const endpoint = () => `${resultUrl(activeResult)}/espacial/${source.value}`;
    const label = row => row.pol === row.pol_origem ? row.pol : `${row.pol} (${row.pol_origem})`;
    const fields = ["spatialTables", "spatialCharts", "spatialDownloads"];

    function clear() {
        result = null;
        viewer = null;
        lastSelection = null;
        chartVersion++;
        tableVersion++;
        for (const id of [...fields, "spatialMapDownloads", "spatialBalance", "spatialZoom", "spatialPointInfo"]) {
            get(id).hidden = true;
        }
        map.replaceChildren();
        map.removeAttribute("aria-busy");
        status("spatialStatus");
        status("spatialMapStatus");
    }

    async function load(execute = false) {
        const current = ++version;
        clear();
        if (!activeResult) return;
        let body;
        if (execute) {
            working = true;
            updateControls();
            status("spatialStatus", "Processando fontes…");
            body = new FormData();
            const file = get("spatialGrid").files[0];
            if (file) body.set("grade", file);
            body.set("epsg", file ? get("spatialEpsg").value : "4326");
        }
        try {
            const data = await api(endpoint(), {method: execute ? "POST" : "GET", body});
            if (current !== version) return;
            result = data;
            for (const s of [series, tableSeries]) {
                options(s, data.series.map(row => [String(row.id), label(row)]), "Selecione");
                s.selectedIndex = 1;
            }
            mode.querySelector('option[value="grade"]')?.remove();
            if (data.grade) mode.add(new Option("Emissões agregadas em grade", "grade"));
            if (!mode.value) mode.value = "pontos";
            for (const id of fields) get(id).hidden = false;
            get("spatialCellsDetails").hidden = !data.grade;
            get("spatialGridLayer").hidden = !data.grade;
            if (!data.grade) get("showGrid").checked = false;
            const files = [["fontes.csv", "Baixar fontes espaciais (CSV)"], ["metadados.json", "Baixar metadados espaciais (JSON)"]];
            if (data.grade) files.push(["celulas.csv", "Baixar massas por célula (CSV)"], ["grade.geojson", "Baixar grade utilizada (GeoJSON)"]);
            renderDownloads("spatialDownloads", endpoint(), files);
            status("spatialStatus", data.grade ? `Grade processada · EPSG:${data.grade_epsg}.` : "Fontes pontuais processadas.", "success");
            if (execute) setStep(5);
            updateBalance();
            showTable();
            showMap();
        } catch (error) {
            if (current !== version) return;
            if (!execute && error.status === 404) return;
            status("spatialStatus", error.status === 404
                ? "Base indisponível. Execute a especiação para usar espécies."
                : error.message, "error");
        } finally {
            if (execute) {
                working = false;
                updateControls();
            }
        }
    }

    function updateBalance() {
        if (!result || !series.value) return;
        const row = result.series[Number(series.value)];
        const b = row.balanco_g;
        get("spatialBalance").textContent = `${label(row)} · ${row.fontes} fontes · ${number.format(row.massa_g)} g no inventário. ${number.format(b.mapeada)} g mapeados, ${number.format(b.fora_grade)} g fora da grade, ${number.format(b.ambigua)} g em interseções ambíguas e ${number.format(b.coordenada_invalida)} g com coordenadas inválidas.`;
        get("spatialBalance").hidden = false;
    }

    async function showTable() {
        const request = ++tableVersion;
        if (!result || !tableSeries.value) return;
        try {
            const params = query();
            params.set("pontos", "false");
            const data = await api(territorioUrl(tableSeries.value, params));
            if (request !== tableVersion) return;
            renderTable([["id", "Fonte"], ["lat", "Latitude"], ["lon", "Longitude"], ["alt", "Altitude"],
                ["uf", "UF (código)"], ["situacao", "Classificação territorial"], ["registros", "Registros"],
                ["massa_g", "Massa (g)"]], data.amostra, "spatialSourcesTable");
            renderTable([["id_grid", "Célula"], ["massa_g", "Massa (g)"]],
                Object.entries(data.celulas).slice(0, 100).map(([id_grid, massa_g]) => ({id_grid, massa_g})),
                "spatialCellsTable");
        } catch (error) {
            if (request === tableVersion) status("spatialStatus", error.message, "error");
        }
    }

    function query() {
        const params = new URLSearchParams(Object.entries(settings).map(([key, select]) => [key, select.value]));
        params.set("modo", mode.value === "interativo" ? "pontos" : mode.value);
        params.set("marcador", marker.value);
        params.set("nivel", level.value);
        params.set("codigo", territorialSelection());
        return params;
    }

    function mapUrl(format, params) {
        return `${endpoint()}/mapas/${series.value}.${format}?${params}`;
    }

    function mapLinks() {
        const list = get("spatialMapDownloads");
        list.replaceChildren();
        list.hidden = !result || !series.value;
        if (list.hidden) return;
        const tabela = document.createElement("a");
        tabela.href = `${endpoint()}/territorio/${series.value}/fontes.csv?${query()}`;
        tabela.className = "button secondary";
        tabela.textContent = "Baixar fontes do território (CSV)";
        list.append(tabela);
        for (const format of ["png", "pdf", "svg"]) {
            const params = query();
            params.set("download", "true");
            const a = document.createElement("a");
            a.href = mapUrl(format, params);
            a.className = "button secondary";
            a.textContent = `Baixar mapa (${format.toUpperCase()}${format === "png" ? `, ${settings.dpi.value} DPI` : ""})`;
            list.append(a);
        }
    }

    function nomes() {
        return {
            uf: Object.fromEntries(states.features.map(f => [String(f.properties.CD_UF), f.properties.NM_UF])),
            regiao: Object.fromEntries(states.regioes.map(f => [String(f.properties.CD_REGIAO), f.properties.NM_REGIAO]))
        };
    }

    async function selectTerritory(nivel, codigo) {
        try {
            states ??= await api("/api/cartografia/ibge");
            const itens = Object.entries(nomes()[nivel] || {}).sort((a, b) => a[1].localeCompare(b[1], "pt-BR"));
            level.value = nivel;
            options(territory, itens, "Selecione");
            territory.value = codigo ? String(codigo) : itens[0]?.[0] || "";
            get("spatialTerritoryLabel").hidden = nivel === "brasil";
            await Promise.all([showMap(), showTable()]);
        } catch (error) {
            status("spatialMapStatus", error.message, "error");
        }
    }

    function showPoints(group, selected, pagina = 0, total = selected.coincidentes || group.length) {
        const target = get("spatialPointInfo");
        target.replaceChildren();
        target.hidden = false;
        const select = document.createElement("select");
        select.setAttribute("aria-label", "Fontes na coordenada");
        group.forEach((p, i) => select.add(new Option(`${p.id} · ${p.alt || "—"} m`, i)));
        select.selectedIndex = Math.max(0, group.indexOf(selected));
        const detail = document.createElement("p");
        function render() {
            const p = group[select.selectedIndex];
            const labels = nomes();
            const campos = [p.id, label(result.series[Number(series.value)]),
                `${number.format(p.valor)} ${settings.unidade.value}`,
                p.lon == null ? "Coordenadas inválidas" : `${number.format(p.lat)}°, ${number.format(p.lon)}°`,
                labels.uf[p.uf] ?? "UF não classificada", labels.regiao[p.regiao],
                `${result.ano} · ${result.combustivel} · ${result.setor}`,
                p.potencia_mw == null ? null : `Potência informada: ${number.format(p.potencia_mw)} MW`,
                p.consumo_gj == null ? null : `Consumo: ${number.format(p.consumo_gj)} GJ`,
                `${p.registros} registro(s)`];
            detail.textContent = campos.filter(Boolean).join(" · ");
        }
        if (group.length > 1) target.append(select);
        target.append(detail);
        select.addEventListener("change", render);
        render();
        if (selected.lon == null || total <= group.length && !pagina) return;
        function botao(titulo, destino) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "button secondary";
            button.textContent = titulo;
            button.onclick = async () => {
                const request = chartVersion;
                const params = query();
                params.set("lon", selected.lon);
                params.set("lat", selected.lat);
                params.set("pagina", destino);
                try {
                    const {fontes} = await api(`${endpoint()}/territorio/${series.value}/coincidentes?${params}`);
                    if (request !== chartVersion || !button.isConnected || !fontes.length) return;
                    for (const p of fontes) p.valor = p.massa_g * units[settings.unidade.value];
                    showPoints(fontes, fontes[0], destino, total);
                } catch (error) {
                    if (request === chartVersion) status("spatialMapStatus", error.message, "error");
                }
            };
            target.append(button);
        }
        if (!pagina) botao(`Consultar as ${total} fontes nesta coordenada`, 1);
        if (pagina > 1) botao("Página anterior", pagina - 1);
        if (pagina && pagina * 100 < total) botao("Próxima página", pagina + 1);
    }

    function renderIndicadores(data) {
        const s = data.indicadores;
        const unidade = settings.unidade.value;
        const massa = g => `${number.format(g * units[unidade])} ${unidade}`;
        const resumo = [data.nome, `Total: ${massa(s.total_g)}`,
            `${s.fontes} ${s.fontes === 1 ? "fonte" : "fontes"} · ${s.registros} ${s.registros === 1 ? "registro" : "registros"}`,
            `Média: ${massa(s.media_g)}`, `Maior fonte: ${massa(s.maximo_g)}`,
            `Participação no total classificado no Brasil: ${s.participacao_pct == null ? "indisponível" : percentage.format(s.participacao_pct) + "%"}`,
            `${s.sem_classificacao} fontes sem UF na base selecionada`];
        if (!s.fontes) resumo.push("Nenhuma fonte para esta seleção.");
        get("spatialIndicators").textContent = resumo.join(" · ");
        const ranking = get("spatialRanking");
        ranking.replaceChildren();
        for (const p of data.ranking) {
            const li = document.createElement("li");
            const button = document.createElement("button");
            button.type = "button";
            button.className = "button secondary";
            button.textContent = `${p.id} · ${massa(p.massa_g)}`;
            button.onclick = () => viewer?.destacar(p);
            li.append(button);
            ranking.append(li);
        }
        const comparacao = get("spatialComparison");
        comparacao.replaceChildren();
        const nivel = get("spatialCompare").value;
        const linhas = Object.entries(data.totais[nivel]).sort((a, b) => b[1] - a[1]);
        const rotulos = nomes()[nivel];
        for (const [codigo, total] of linhas) {
            const li = document.createElement("li");
            const button = document.createElement("button");
            const barra = document.createElement("meter");
            button.type = "button";
            button.className = "button secondary";
            button.textContent = `${rotulos[codigo]} · ${massa(total)}`;
            barra.max = linhas[0][1] || 1;
            barra.value = total;
            barra.setAttribute("aria-hidden", "true");
            button.append(barra);
            button.onclick = () => selectTerritory(nivel, codigo);
            li.append(button);
            comparacao.append(li);
        }
    }

    function renderLegenda(data, camadas) {
        const target = get("spatialLegend");
        const legenda = data.legenda;
        target.replaceChildren();
        target.hidden = false;
        const texto = document.createElement("p");
        const min = legenda.min == null ? "sem faixa de cores" : `${number.format(legenda.min)}–${number.format(legenda.max)} ${legenda.unidade}`;
        const origem = legenda.escopo === "local" ? "Território selecionado" : "Base nacional";
        const estilo = settings.escala.value === "log" ? "logarítmica; zero em cinza" : "linear";
        texto.textContent = `${label(data.serie)} · ${origem} · ${estilo} · ${min}`;
        target.append(texto);
        if (legenda.min != null) {
            const cores = document.createElement("span");
            cores.className = "spatial-legend-band";
            cores.style.background = `linear-gradient(to right, ${legenda.cores.join(",")})`;
            target.append(cores);
        }
        if (camadas.territorial) {
            const linha = document.createElement("p");
            linha.textContent = legenda.min_uf == null ? "Sem massa classificada por UF." :
                `Preenchimento das UFs: massa total · ${number.format(legenda.min_uf)}–${number.format(legenda.max_uf)} ${legenda.unidade}.`;
            target.append(linha);
        }
        if (camadas.grade) {
            const linha = document.createElement("p");
            linha.textContent = data.grade_visual?.limitada ? "A grade excede o limite de 2.500 células da camada interativa." :
                `Grade: massa total por célula${data.grade_visual?.min == null ? "" : ` · ${number.format(data.grade_visual.min)}–${number.format(data.grade_visual.max)} ${legenda.unidade}`}.`;
            target.append(linha);
        }
        if (camadas.calor) {
            const linha = document.createElement("p");
            linha.textContent = "Halos indicam intensidade visual das emissões pontuais. Sem interpretação como concentração, dispersão ou exposição.";
            target.append(linha);
        }
        const credito = document.createElement("p");
        credito.textContent = "Cartografia: IBGE, Malha UF 2025 (adaptada).";
        target.append(credito);
    }

    async function showMap() {
        const request = ++chartVersion;
        const regional = mode.querySelector('[value="regional"]');
        if (regional) {
            regional.disabled = level.value === "uf";
            if (regional.disabled && mode.value === "regional") mode.value = "territorial";
        }
        mapLinks();
        if (!result || !series.value || get("chartsPanel").hidden || get("spatialFigures").hidden) return;
        map.setAttribute("aria-busy", "true");
        status("spatialMapStatus", "Atualizando mapa…");
        try {
            const params = query();
            const camadas = capture();
            params.set("top", get("spatialTop").value);
            params.set("ordem", get("spatialOrder").value);
            params.set("pontos", String(mode.value === "interativo" && (camadas.calor || camadas.pontos)));
            params.set("grade_visual", String(mode.value === "interativo" && camadas.grade && result.grade));
            const [basemap, data] = await Promise.all([
                states ?? api("/api/cartografia/ibge"),
                api(territorioUrl(series.value, params))
            ]);
            if (request !== chartVersion) return;
            states = basemap;
            if (mode.value === "interativo") {
                if (lastSelection !== `${level.value}:${territorialSelection()}`) get("spatialPointInfo").hidden = true;
                const selecionado = `${level.value}:${territorialSelection()}`;
                viewer = criarMapaTerritorial({basemap, dados: data, nivel: level.value,
                    codigo: territorialSelection(), unidade: settings.unidade.value, marcador: marker.value,
                    fator: units[settings.unidade.value], camadas, selecionar: selectTerritory, mostrar: showPoints,
                    anterior: lastSelection !== selecionado ? viewer?.caixa() : null,
                    atual: lastSelection === selecionado ? viewer?.caixa() : null});
                lastSelection = selecionado;
                const focused = map.contains(document.activeElement) ? document.activeElement.dataset.uf : null;
                map.replaceChildren(viewer.svg);
                if (focused) viewer.svg.querySelector(`[data-uf="${CSS.escape(focused)}"]`)?.focus({preventScroll: true});
                renderIndicadores(data);
                get("spatialZoom").hidden = true;
                for (const id of ["spatialControls", "spatialLayers", "spatialExploration"]) get(id).hidden = false;
                renderLegenda(data, camadas);
                const total = data.total_pontos;
                const limitado = data.pontos.length > 0 && total > data.pontos.length;
                status("spatialMapStatus", limitado ? `Exibindo as ${data.pontos.length} maiores fontes de ${total}. Indicadores usam toda a seleção.`
                    : "Selecione um território ou fonte. Arraste para deslocar e use a rolagem ou os botões para zoom.");
            } else {
                params.set("dpi", "100");
                const image = new Image();
                image.alt = "Mapa científico da série selecionada";
                image.src = mapUrl("png", params);
                await image.decode();
                if (request !== chartVersion) return;
                map.replaceChildren(image);
                renderIndicadores(data);
                get("spatialPointInfo").hidden = true;
                for (const id of ["spatialLegend", "spatialControls", "spatialLayers", "spatialExploration"]) get(id).hidden = true;
                get("spatialZoom").hidden = false;
                status("spatialMapStatus");
            }
        } catch (error) {
            if (request === chartVersion) status("spatialMapStatus", error.message || "Mapa indisponível para esta seleção.", "error");
        } finally {
            if (request === chartVersion) map.removeAttribute("aria-busy");
        }
    }

    document.addEventListener("pega:result", () => {
        get("spatialGrid").value = "";
        load();
    });
    source.addEventListener("change", () => load());
    get("spatialRun").addEventListener("click", () => load(true));
    tableSeries.addEventListener("change", showTable);
    series.addEventListener("change", () => {
        tableSeries.value = series.value;
        updateBalance();
        showTable();
    });
    level.addEventListener("change", () => selectTerritory(level.value));
    territory.addEventListener("change", () => { showTable(); showMap(); });
    get("spatialNational").onclick = () => selectTerritory("brasil");
    get("spatialIn").onclick = () => viewer?.zoom(.78);
    get("spatialOut").onclick = () => viewer?.zoom(1.28);
    get("spatialRestore").onclick = () => viewer?.enquadrar();
    get("spatialFullscreen").onclick = async () => {
        try { await (document.fullscreenElement ? document.exitFullscreen() : map.requestFullscreen()); }
        catch { status("spatialMapStatus", "Tela cheia indisponível neste navegador.", "error"); }
    };
    for (const select of [series, mode, ...Object.values(settings), marker,
        ...["spatialTop", "spatialOrder", "spatialCompare", ...Object.values(layers)].map(get)]) {
        select.addEventListener("change", showMap);
    }
    const chartObserver = new MutationObserver(showMap);
    for (const id of ["chartsPanel", "spatialFigures"]) {
        chartObserver.observe(get(id), {attributes: true, attributeFilter: ["hidden"]});
    }
    get("spatialZoom").addEventListener("click", () => {
        const params = query();
        params.set("dpi", "300");
        get("spatialDialog").querySelector("img").src = mapUrl("png", params);
        get("spatialDialog").showModal();
    });
})();
