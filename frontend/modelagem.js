(() => {
    const source = get("modelingSource");
    const domain = get("modelingDomain");
    const annual = get("modelingAnnual");
    const clock = get("modelingClock");
    let revision = 0;

    const endpoint = () => `${resultUrl(activeResult)}/modelagem/${source.value}`;

    function show(data) {
        const grid = `Domínio ${data.grid_id} · ${data.nx} × ${data.ny} · ${number.format(data.dx_m)} × ${number.format(data.dy_m)} m projetados.`;
        const temporal = data.calendario
            ? ` ${data.calendario.horas} horas (${data.calendario.convencao}). ${data.calendario.horario_materializado
                ? "Massas horárias para os pares série/célula ativos."
                : "Massas horárias recuperáveis a partir da massa por célula e dos pesos horários."}`
            : " Massas da base por célula.";
        status("modelingStatus", grid + temporal, "success");
        renderTable([["pol_origem", "Origem"], ["pol", "Série"], ["total", "Base (g)"],
            ["mapped", "Na grade (g)"], ["outside", "Fora do domínio (g)"],
            ["boundary", "Em borda (g)"], ["invalid", "Coordenada inválida (g)"]],
        data.series.map(s => ({...s, total: number.format(s.massa_base_g),
            mapped: number.format(s.massa_grade_g), outside: number.format(s.balanco_g.fora_grade),
            boundary: number.format(s.balanco_g.borda_grade),
            invalid: number.format(s.balanco_g.coordenada_invalida)})), "modelingBalance");
        get("modelingTables").hidden = false;
        get("modelingDownloads").hidden = false;
        renderDownloads("modelingDownloads", endpoint(), [
            ["emissoes-grade.nc", "Baixar inventário em grade (NetCDF)"],
            ["metadados-modelagem.json", "Baixar balanço e metadados (JSON)"]
        ]);
    }

    async function load(form) {
        const current = ++revision;
        get("modelingTables").hidden = true;
        get("modelingDownloads").hidden = true;
        status("modelingStatus");
        if (!activeResult) return;
        if (form) status("modelingStatus", "Validando domínio e gerando NetCDF…");
        try {
            const data = await api(endpoint(), form ? {method: "POST", body: form} : undefined);
            if (current !== revision) return;
            show(data);
            if (form) setStep(6);
        } catch (error) {
            if (current !== revision || (!form && error.status === 404)) return;
            const message = error.status === 404
                ? "Base indisponível. Para usar espécies, execute primeiro a especiação química."
                : error.message;
            status("modelingStatus", message, "error");
        }
    }

    annual.addEventListener("change", () => {
        get("modelingClockLabel").hidden = !annual.checked;
        get("modelingCalendarNote").hidden = !annual.checked;
        clock.required = annual.checked;
    });
    document.addEventListener("pega:result", () => {
        domain.value = "";
        load();
    });
    source.addEventListener("change", () => load());
    get("modelingForm").addEventListener("submit", async event => {
        event.preventDefault();
        if (working || !domain.files[0]) return;
        const form = new FormData();
        form.set("dominio", domain.files[0]);
        if (annual.checked) {
            form.set("anual", "true");
            form.set("convencao", clock.value.trim());
        }
        working = true;
        updateControls();
        try {
            await load(form);
        } finally {
            working = false;
            updateControls();
        }
    });
})();
