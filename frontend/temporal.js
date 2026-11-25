(() => {
    const source = get("temporalSource");
    const pollutant = get("temporalPollutant");
    const plot = get("temporalPlot");
    const unit = get("temporalUnit");
    const preview = get("temporalPreview");
    const width = 840;
    const height = 420;
    const factors = {"%": 100, g: 1, kg: 1e-3, t: 1e-6};
    let temporal;
    let requestVersion = 0;

    function endpoint() {
        return `${resultUrl(activeResult)}/temporal/${source.value}`;
    }

    function selected() {
        return temporal.resumo[Number(pollutant.value)];
    }

    function label(row) {
        return row.especiado ? `${row.pol} (${row.pol_origem})` : row.pol;
    }

    function clear() {
        temporal = null;
        for (const id of ["temporalTables", "temporalCharts", "temporalDownloads"]) get(id).hidden = true;
        status("temporalStatus");
        status("temporalChartStatus");
        preview.replaceChildren();
    }

    function show(data, executed) {
        temporal = data;
        for (const id of ["temporalTables", "temporalCharts", "temporalDownloads"]) get(id).hidden = false;
        options(pollutant, data.resumo.map((row, i) => [String(i), label(row)]), "Selecione");
        pollutant.selectedIndex = 1;
        get("temporalWeights").textContent = `Somas dos pesos: horário bruto ${number.format(data.somas_pesos.horario_original)}, horário normalizado ${number.format(data.somas_pesos.horario)}, semanal ${number.format(data.somas_pesos.semanal)}, combinado ${number.format(data.somas_pesos.combinado)}. Os 168 intervalos repartem a massa da base sem calendário.`;
        renderTable([["pol_origem", "Origem"], ["pol", "Poluente ou espécie"], ["massa_base_g", "Base (g)"]],
            data.resumo.map(row => ({...row, massa_base_g: number.format(row.massa_base_g)})), "temporalSummary");
        renderTable([["hora", "Hora"], ["peso_original", "Peso no R"], ["peso", "Peso normalizado"]],
            data.horario, "temporalHourly");
        renderTable([["dia", "Dia do perfil"], ["peso", "Peso semanal"]], data.semanal, "temporalWeekly");
        renderDownloads("temporalDownloads", endpoint(), [
            ["perfil_temporal.json", "Baixar perfil e resumos (JSON)"],
            ["alocacao_relativa.csv", "Baixar alocação relativa por fonte (CSV)"]
        ]);
        const residual = data.balanco_especiacao.some(row => row.residuo_g);
        status("temporalStatus", `Perfil relativo disponível. ${residual ? "Os saldos da especiação permanecem fora da alocação." : ""}`, "success");
        if (executed) setStep(4);
        redraw();
    }

    async function load(execute = false) {
        const version = ++requestVersion;
        clear();
        if (!activeResult) return;
        if (execute) {
            working = true;
            updateControls();
        }
        status("temporalStatus", execute ? "Calculando distribuição relativa…" : "Consultando resultados temporais…");
        try {
            const data = await api(endpoint(), {method: execute ? "POST" : "GET"});
            if (version === requestVersion) show(data, execute);
        } catch (error) {
            if (version === requestVersion) {
                status("temporalStatus", error.status === 404
                    ? (execute ? "Base indisponível. Para usar espécies, execute primeiro a especiação química." : "")
                    : error.message, execute || error.status !== 404 ? "error" : "");
            }
        } finally {
            if (execute) {
                working = false;
                updateControls();
            }
        }
    }

    function draw(white) {
        const kind = plot.value;
        const row = selected();
        const scale = factors[unit.value] * (unit.value === "%" ? 1 : row.massa_base_g);
        const weights = temporal[kind === "calor" ? "combinado" : kind];
        const values = weights.map(item => item.peso * scale);
        const maximum = Math.max(...values) || 1;
        const ns = "http://www.w3.org/2000/svg";
        const svg = document.createElementNS(ns, "svg");
        svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
        svg.setAttribute("width", width);
        svg.setAttribute("height", height);
        svg.setAttribute("role", "img");
        const ink = white ? "#172033" : "#eaf2ff";
        const accent = white ? "#17665b" : "#6ce4bc";
        const add = (tag, attrs, text) => {
            const node = document.createElementNS(ns, tag);
            for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, value);
            if (text != null) node.textContent = text;
            svg.append(node);
            return node;
        };
        const annotate = (node, i) => {
            const tooltip = document.createElementNS(ns, "title");
            const interval = [weights[i].dia, weights[i].hora == null ? null : `${weights[i].hora} h`].filter(Boolean).join(" ");
            tooltip.textContent = `${interval} · ${label(row)} · ${number.format(values[i])} ${unit.value}`;
            node.append(tooltip);
        };
        const text = (x, y, value, size = 13, anchor = "start") =>
            add("text", {x, y, fill: ink, "font-size": size, "text-anchor": anchor,
                "font-family": "sans-serif"}, value);
        const title = `${plot.selectedOptions[0].textContent} — ${label(row)}`;
        add("title", {}, title);
        add("rect", {width, height, fill: white ? "#ffffff" : "#142338"});
        text(24, 29, title, 19);
        text(24, 52, `${temporal.setor} · ${temporal.combustivel} · ${temporal.ano} | ${unit.value === "%" ? "Peso relativo" : "Massa alocada por intervalo"} (${unit.value})`);
        text(24, 399, "Perfil do R sem calendário · os intervalos não representam uma semana real.");
        const left = 105, top = 85, w = 690, h = 245;
        if (kind === "calor") {
            const cellW = w / 24;
            const cellH = h / 7;
            values.forEach((value, i) => {
                const color = `hsl(166 58% ${88 - 60 * value / maximum}%)`;
                const rect = add("rect", {x: left + i % 24 * cellW, y: top + Math.floor(i / 24) * cellH,
                    width: cellW - 1, height: cellH - 1, fill: color});
                const tooltip = document.createElementNS(ns, "title");
                tooltip.textContent = `${weights[i].dia} ${weights[i].hora} h: ${number.format(value)} ${unit.value}`;
                rect.append(tooltip);
            });
            temporal.semanal.forEach(({dia}, i) => text(left - 12, top + (i + .65) * cellH, dia, 12, "end"));
            for (let hour = 0; hour < 24; hour += 3) text(left + (hour + .5) * cellW, top + h + 18, hour, 12, "middle");
            text(left, 377, `Hora do dia · Cor: 0 a ${number.format(Math.max(...values))} ${unit.value}`);
        } else {
            for (let tick = 0; tick <= 4; tick++) {
                const y = top + h * (1 - tick / 4);
                add("line", {x1: left, x2: left + w, y1: y, y2: y, stroke: ink, opacity: ".23"});
                text(left - 10, y + 4, number.format(Math.max(...values) * tick / 4), 11, "end");
            }
            const x = i => left + (kind === "semanal" ? (i + .5) / 7 : i / (values.length - 1)) * w;
            const y = value => top + h * (1 - value / maximum);
            if (kind === "semanal") {
                values.forEach((value, i) => annotate(add("rect", {x: x(i) - 30, y: y(value), width: 60,
                    height: top + h - y(value), fill: accent}), i));
            } else {
                add("polyline", {points: values.map((value, i) => `${x(i)},${y(value)}`).join(" "),
                    stroke: accent, "stroke-width": 2, fill: "none"});
                values.forEach((value, i) => {
                    const hourly = kind === "horario";
                    annotate(add(hourly ? "circle" : "rect", hourly
                        ? {cx: x(i), cy: y(value), r: 3, fill: accent}
                        : {x: x(i) - 3, y: y(value) - 7, width: 6, height: 14, fill: "transparent"}), i);
                });
            }
            const step = kind === "semanal" ? 1 : kind === "horario" ? 3 : 24;
            for (let i = 0; i < values.length; i += step) {
                text(x(i), top + h + 18, kind === "semanal" ? weights[i].dia : i, 12, "middle");
            }
            text(left, 377, kind === "semanal" ? "Dia do perfil" : "Hora do perfil");
        }
        return svg;
    }

    function redraw() {
        if (!temporal || !pollutant.value) return;
        status("temporalChartStatus");
        const row = selected();
        get("temporalCaption").textContent = `Base: ${number.format(row.massa_base_g * (unit.value === "%" ? 1 : factors[unit.value]))} ${unit.value === "%" ? "g" : unit.value}. Perfil relativo sem calendário. Em unidades de massa, os valores são alocações modeladas, sem taxa horária. Os perfis de 24 e 7 intervalos são marginais.`;
        renderTable([["dia", "Dia"], ["hora", "Hora"], ["peso", "Peso"],
            ["massa", "Massa alocada (g)"]], temporal.combinado.map(item => ({
            ...item, massa: number.format(item.peso * row.massa_base_g)
        })), "temporalCombined");
        preview.replaceChildren(draw(false));
    }

    function svgBlob() {
        return new Blob([new XMLSerializer().serializeToString(draw(true))], {type: "image/svg+xml"});
    }

    function download(blob, format) {
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `perfil-temporal-${source.value}-${plot.value}.${format}`;
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    document.addEventListener("pega:result", () => load());
    source.addEventListener("change", () => load());
    get("temporalRun").addEventListener("click", () => load(true));
    for (const select of [plot, pollutant, unit]) select.addEventListener("change", redraw);
    get("temporalSvg").addEventListener("click", () => download(svgBlob(), "svg"));
    get("temporalPng").addEventListener("click", async () => {
        const url = URL.createObjectURL(svgBlob());
        try {
            const image = new Image();
            image.src = url;
            await image.decode();
            const canvas = document.createElement("canvas");
            canvas.width = Number(get("temporalDpi").value) * 8;
            canvas.height = canvas.width * height / width;
            canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
            const blob = await new Promise(resolve => canvas.toBlob(resolve, "image/png"));
            if (!blob) throw new Error("Não foi possível gerar o PNG.");
            download(blob, "png");
        } catch (error) {
            status("temporalChartStatus", error.message, "error");
        } finally {
            URL.revokeObjectURL(url);
        }
    });
    get("temporalPdf").addEventListener("click", () => {
        preview.replaceChildren(draw(true));
        document.body.classList.add("temporal-print");
        window.addEventListener("afterprint", () => {
            document.body.classList.remove("temporal-print");
            redraw();
        }, {once: true});
        window.print();
    });
})();
