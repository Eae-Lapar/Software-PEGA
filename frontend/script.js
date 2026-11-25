
const get = id => document.getElementById(id);

const dropZone = get("dropZone");
const fileInput = get("fileInput");
const selectButton = get("selectButton");
const resetButton = get("resetButton");

let uploading = false;
let inventory = null;
let analysis = null;
let working = false;
let loadingSector = false;
let analysisVersion = 0;
let resultVersion = 0;
let supportedFuels = [];
let supportedSectors;
let activeResult = null;
const inventoryKey = "pega.inventario";
const resultKey = "pega.execucao";


// STATUS DO SERVIDOR

async function checkServer() {

    const status = get("serverStatus");

    try {

        const response = await fetch("/api/health");

        if (!response.ok) {
            throw new Error("Servidor indisponível");
        }

        const data = await response.json();

        if (data.status !== "online") {
            throw new Error("Servidor indisponível");
        }

        status.className = "server-status online";

        status.innerHTML = `
            <span class="status-dot"></span>
            Servidor online
        `;

    } catch {

        status.className = "server-status offline";

        status.innerHTML = `
            <span class="status-dot"></span>
            Servidor offline
        `;
    }
}


// SELEÇÃO DO ARQUIVO

selectButton.addEventListener("click", () => {
    if (!uploading) {
        fileInput.click();
    }
});

fileInput.addEventListener("change", () => {

    const file = fileInput.files[0];

    if (file) {
        uploadFile(file);
    }
});


// ARRASTAR E SOLTAR

["dragenter", "dragover"].forEach(eventName => {

    dropZone.addEventListener(eventName, event => {

        event.preventDefault();

        if (!uploading && !working && !loadingSector) {
            dropZone.classList.add("dragover");
        }
    });
});

["dragleave", "drop"].forEach(eventName => {

    dropZone.addEventListener(eventName, event => {

        event.preventDefault();

        dropZone.classList.remove("dragover");
    });
});

dropZone.addEventListener("drop", event => {

    if (uploading || working || loadingSector) return;

    const files = event.dataTransfer.files;

    if (files.length !== 1) {

        showMessage(
            "Envie apenas uma planilha por vez.",
            "error"
        );

        return;
    }

    uploadFile(files[0]);
});


// MENSAGENS

function showMessage(text, type) {

    const message = get("message");

    message.textContent = text;

    message.className = `message ${type}`;

    message.hidden = false;
}


// PROGRESSO

function updateProgress(percent) {

    get("progressBar").style.width = `${percent}%`;

    get("progressValue").textContent = `${percent}%`;
}


// UPLOAD

function uploadFile(file) {

    if (uploading || working || loadingSector) return;

    resetInterface();

    get("fileName").textContent = file.name;

    const extension = file.name
        .split(".")
        .pop()
        .toLowerCase();

    if (!["csv", "txt", "xlsx"].includes(extension)) {

        showMessage(
            "Formato inválido. Envie CSV, TXT ou XLSX.",
            "error"
        );

        return;
    }

    if (file.size > 50 * 1024 * 1024) {
        showMessage("O arquivo excede o limite de 50 MB.", "error");
        return;
    }

    uploading = true;
    updateControls();

    selectButton.disabled = true;

    setStep(0, true);
    get("progressContainer").hidden = false;

    get("progressText").textContent =
        "Enviando arquivo...";

    updateProgress(0);

    const formData = new FormData();

    formData.append("arquivo", file);

    const xhr = new XMLHttpRequest();

    xhr.open("POST", "/api/upload");

    xhr.upload.addEventListener("progress", event => {

        if (event.lengthComputable) {

            const percent = Math.round(
                event.loaded / event.total * 100
            );

            updateProgress(percent);
        }
    });

    xhr.upload.addEventListener("load", () => {

        updateProgress(100);
        setStep(8, true);

        get("progressText").textContent =
            "Validando dados da planilha...";
    });

    xhr.addEventListener("load", () => {

        try {

            const data = JSON.parse(xhr.responseText);

            if (xhr.status >= 200 && xhr.status < 300) {

                showResults(data);

            } else {

                const detail =
                    typeof data.detail === "string"
                        ? data.detail
                        : "Não foi possível importar o arquivo.";

                showMessage(detail, "error");
            }

        } catch {

            showMessage(
                "Resposta inválida do servidor.",
                "error"
            );

        } finally {

            finishUpload();
        }
    });

    xhr.addEventListener("error", () => {

        showMessage(
            "Não foi possível conectar ao servidor.",
            "error"
        );

        finishUpload();
    });

    xhr.addEventListener("abort", () => {

        showMessage("Envio cancelado.", "error");

        finishUpload();
    });

    xhr.send(formData);
}


// FINALIZAÇÃO

function finishUpload() {

    uploading = false;
    if (!inventory) setStep(0);
    updateControls();

    selectButton.disabled = false;

    get("progressContainer").hidden = true;

    fileInput.value = "";
}


// RESULTADOS

function showResults(data) {

    get("results").hidden = false;

    get("totalRows").textContent =
        number.format(data.total_linhas);

    get("years").textContent =
        data.validacao.anos.join(", ") || "—";

    get("fuels").textContent =
        data.validacao.combustiveis.join(", ") || "—";

    const extras = get("extraColumns");
    const extraColumns = data.colunas_extras ?? [];

    extras.hidden = extraColumns.length === 0;
    if (extraColumns.length > 0) {

        extras.textContent =
            "Colunas adicionais ignoradas: " +
            extraColumns.join(", ");

        extras.hidden = false;
    }

    renderTable(data.colunas, data.previa);

    if (data.validacao.valido) {

        showMessage(
            "Planilha importada e validada com sucesso!",
            "success"
        );

    } else {

        showMessage(
            "Foram identificados problemas na planilha:\n\n" +
            data.validacao.problemas.join("\n"),
            "error"
        );
    }

    inventory = data.inventario_id ? data : null;
    if (inventory) rememberInventory(data.inventario_id);
    setStep(inventory ? 1 : 0);
    get("deleteInventory").hidden = !inventory;
    updateControls();
}


// TABELA

function renderTable(columns, rows, tableId = "previewTable") {

    const table = get(tableId);

    const thead = table.tHead || table.createTHead();

    const tbody = table.tBodies[0] || table.createTBody();

    thead.replaceChildren();

    tbody.replaceChildren();

    const headerRow = document.createElement("tr");

    const fields = columns.map(column => Array.isArray(column) ? column : [column, column]);
    fields.forEach(([, label]) => {

        const th = document.createElement("th");

        th.textContent = label;
        th.scope = "col";

        headerRow.appendChild(th);
    });

    thead.appendChild(headerRow);

    enhanceTable(table, fields, rows);
}


// LIMPAR INTERFACE

function resetInterface() {

    inventory = null;
    analysis = null;
    analysisVersion++;
    resultVersion++;
    activeResult = null;
    document.dispatchEvent(new Event("pega:result"));
    setStep(0);
    get("processamento").hidden = true;
    get("factorPanel").hidden = true;
    get("resultsEmpty").hidden = false;
    get("historyLabel").hidden = true;
    status("resultStatus");
    get("resultContent").hidden = true;
    get("deleteInventory").hidden = true;
    get("results").hidden = true;

    get("message").hidden = true;

    get("extraColumns").hidden = true;

    get("progressContainer").hidden = true;

    get("fileName").textContent = "";

    get("nextButton").disabled = true;

    updateProgress(0);
    updateControls();
}

resetButton.addEventListener("click", () => {

    resetInterface();

    fileInput.value = "";

    dropZone.scrollIntoView({
        behavior: "smooth",
        block: "center"
    });
});


// PROCESSAMENTO E RESULTADOS PRIVADOS

const factorColumns = [
    ["pol", "Poluente"], ["ef", "Fator"], ["unit", "Unidade"],
    ["source", "Fonte"], ["reference", "Referência"], ["other", "Observação"]
];
const number = pegaLocale.number({maximumSignificantDigits: 12});
const sectorSelect = get("sectorSelect");
const yearSelect = get("yearSelect");
const fuelSelect = get("fuelSelect");
const historySelect = get("calculationHistory");

function rememberInventory(id) {
    try {
        if (id) sessionStorage.setItem(inventoryKey, id);
        else {
            sessionStorage.removeItem(inventoryKey);
            sessionStorage.removeItem(resultKey);
        }
    } catch {
        // O fluxo continua disponível quando o navegador bloqueia a sessão local.
    }
}

function inventoryUrl(id = inventory.inventario_id) {
    return `/api/inventarios/${encodeURIComponent(id)}`;
}

async function api(url, options) {
    const response = await fetch(url, {cache: "no-store", ...options});
    const data = await response.json().catch(() => null);
    if (!response.ok || !data) {
        const detail = typeof data?.detail === "string" ? data.detail : "Resposta inesperada do servidor.";
        const error = new Error(detail);
        error.status = response.status;
        throw error;
    }
    return data;
}

function status(id, message = "", type = "") {
    const element = get(id);
    element.textContent = message;
    element.className = `message ${type}`;
    element.hidden = !message;
    analysisState(id, message, type);
}

function options(select, items, placeholder) {
    select.replaceChildren(new Option(placeholder, ""));
    for (const [value, label] of items) select.add(new Option(label, value));
}

function updateControls() {
    const busy = working || uploading || loadingSector;
    selectButton.disabled = busy;
    resetButton.disabled = busy;
    for (const element of [get("deleteInventory"), get("nextButton")]) {
        element.disabled = busy || !inventory;
    }
    for (const element of [sectorSelect, yearSelect, fuelSelect, historySelect]) {
        element.disabled = busy;
    }
    const choices = [...get("factorChoices").querySelectorAll("select")];
    for (const select of choices) select.disabled = busy;
    get("calculateButton").disabled = busy || !analysis || choices.some(select => !select.value);
    get("speciateButton").disabled = busy || !activeResult;
    get("temporalRun").disabled = busy || !activeResult;
    get("temporalSource").disabled = busy;
    get("spatialRun").disabled = busy || !activeResult;
    for (const id of ["spatialSource", "spatialGrid", "spatialEpsg"]) get(id).disabled = busy;
    get("modelingRun").disabled = busy || !activeResult;
    for (const id of ["modelingSource", "modelingDomain", "modelingAnnual", "modelingClock"]) get(id).disabled = busy;
}

function showWarnings(id, warnings) {
    const list = get(id);
    list.replaceChildren();
    for (const warning of warnings) {
        const item = document.createElement("li");
        item.textContent = [
            warning.poluente || warning.pol, warning.motivo, warning.reference,
            warning.quantidade == null ? "" : `${warning.quantidade} registro(s)`
        ].filter(Boolean).join(" — ");
        list.append(item);
    }
    list.hidden = warnings.length === 0;
}

function updateFuelMapping() {
    const originals = inventory.atividades
        .filter(item => item.ano === yearSelect.value &&
            item.combustivel.toLowerCase() === fuelSelect.value.toLowerCase() &&
            item.combustivel_original !== fuelSelect.value)
        .map(item => item.combustivel_original);
    const note = get("fuelMapping");
    note.textContent = originals.length ? `${[...new Set(originals)].join(", ")} → ${fuelSelect.value}` : "";
    note.hidden = !originals.length;
}

function updateFuelOptions() {
    const previous = fuelSelect.value;
    const imported = new Set(inventory.atividades.filter(item => item.ano === yearSelect.value)
        .map(item => item.combustivel.toLowerCase()));
    const available = supportedFuels.filter(fuel => imported.has(fuel.toLowerCase()));
    options(fuelSelect, available.map(fuel => [fuel, fuel]), "Selecione o combustível");
    if (available.includes(previous)) fuelSelect.value = previous;
    else if (available.length === 1) fuelSelect.value = available[0];
    updateFuelMapping();
}

async function analyzeFactors() {
    const version = ++analysisVersion;
    analysis = null;
    get("factorPanel").hidden = true;
    get("factorChoices").replaceChildren();
    updateControls();
    if (!sectorSelect.value || !yearSelect.value || !fuelSelect.value) {
        status("processingStatus", fuelSelect.options.length === 1 && yearSelect.value && sectorSelect.value
            ? "Nenhum combustível deste ano é suportado pelo setor selecionado."
            : "Selecione setor, ano e combustível.");
        return;
    }
    status("processingStatus", "Consultando fatores científicos…");
    const query = new URLSearchParams({setor: sectorSelect.value, combustivel: fuelSelect.value});
    try {
        const data = await api(`/api/fatores/analise?${query}`);
        if (version !== analysisVersion) return;
        renderTable(factorColumns, data.automaticos, "automaticFactors");
        for (const group of data.escolhas) {
            const label = document.createElement("label");
            label.textContent = `Referência para ${group.poluente}`;
            const select = document.createElement("select");
            select.required = true;
            select.dataset.pollutant = group.poluente;
            options(select, group.opcoes.map(factor => [factor.fator_id,
                [number.format(factor.ef), factor.unit, factor.reference, factor.other]
                    .filter(Boolean).join(" — ")]), "Escolha uma referência");
            select.addEventListener("change", updateControls);
            label.append(select);
            get("factorChoices").append(label);
        }
        showWarnings("factorWarnings", data.indisponiveis);
        get("factorPanel").hidden = false;
        if (data.total_automaticos || data.total_escolhas) {
            analysis = data;
            setStep(2);
            status("processingStatus", data.requer_escolha ? "Selecione as referências obrigatórias." : "");
        } else {
            status("processingStatus", "Nenhum fator válido disponível.", "error");
        }
    } catch (error) {
        if (version === analysisVersion) status("processingStatus", error.message, "error");
    } finally {
        if (version === analysisVersion) updateControls();
    }
}

async function changeSector() {
    const version = ++analysisVersion;
    loadingSector = true;
    analysis = null;
    supportedFuels = [];
    updateFuelOptions();
    get("factorPanel").hidden = true;
    updateControls();
    status("processingStatus", "Consultando combustíveis do setor…");
    try {
        if (sectorSelect.value) {
            const data = await api(`/api/setores/${encodeURIComponent(sectorSelect.value)}/combustiveis`);
            if (version !== analysisVersion) return;
            supportedFuels = data.combustiveis;
        }
        updateFuelOptions();
        await analyzeFactors();
    } catch (error) {
        if (version === analysisVersion) status("processingStatus", error.message, "error");
    } finally {
        loadingSector = false;
        updateControls();
    }
}

async function openProcessing() {
    get("processamento").hidden = false;
    get("processamento").scrollIntoView();
    working = true;
    updateControls();
    status("processingStatus", "Consultando setores suportados…");
    try {
        supportedSectors ??= (await api("/api/setores/suportados")).setores;
        options(sectorSelect, supportedSectors.map(sector => [sector, sector]), "Selecione o setor");
        options(yearSelect, inventory.validacao.anos.map(year => [year, year]), "Selecione o ano");
        if (supportedSectors.length === 1) sectorSelect.value = supportedSectors[0];
        if (inventory.validacao.anos.length === 1) yearSelect.value = inventory.validacao.anos[0];
        await changeSector();
    } catch (error) {
        status("processingStatus", error.message, "error");
    } finally {
        working = false;
        updateControls();
    }
}

function displayCalculation(data) {
    if (activeResult !== data.calculo_id) {
        activeResult = data.calculo_id;
        try {
            sessionStorage.setItem(resultKey, JSON.stringify([inventory.inventario_id, activeResult]));
        } catch {
            // A seleção continua ativa na página atual.
        }
        clearSpeciation();
        loadSpeciation(data.calculo_id);
        document.dispatchEvent(new Event("pega:result"));
    }
    get("resultsEmpty").hidden = true;
    get("historyLabel").hidden = false;
    get("resultContent").hidden = false;
    showMetrics(data);
    showWarnings("calculationWarnings", data.avisos);
    renderTable([["pol", "Poluente"], ["emissions", "Emissão"], ["unit_emissions", "Unidade"]],
        data.resumo.map(row => ({...row, emissions: number.format(row.emissions)})), "emissionSummary");
    renderTable([["id", "Fonte"], ["pol", "Poluente"], ["activity", "Atividade (GJ)"],
        ["emissions", "Emissão (g)"]], data.previa, "emissionPreview");
    renderTable(factorColumns, data.fatores_utilizados, "usedFactors");

    updateControls();
}

function resultUrl(id) {
    return `${inventoryUrl()}/calculos/${encodeURIComponent(id)}`;
}

async function loadHistory(current = null) {
    const version = ++resultVersion;
    const url = inventoryUrl();
    const data = await api(`${url}/calculos`);
    if (version !== resultVersion) return;
    options(historySelect, data.calculos.map((item, index) => [item.calculo_id,
        `Execução ${data.calculos.length - index} · ${item.ano} · ${item.combustivel}`]), "Selecione uma execução");
    if (!data.calculos.length) return;
    let remembered;
    try {
        const [id, calculation] = JSON.parse(sessionStorage.getItem(resultKey) || "[]");
        if (id === inventory.inventario_id && data.calculos.some(item => item.calculo_id === calculation)) {
            remembered = calculation;
        }
    } catch {
        // O histórico ainda pode abrir a primeira execução disponível.
    }
    historySelect.value = current?.calculo_id ?? remembered ?? data.calculos[0].calculo_id;
    if (current) displayCalculation(current);
    else await selectCalculation();
}

async function selectCalculation() {
    const version = ++resultVersion;
    activeResult = null;
    document.dispatchEvent(new Event("pega:result"));
    get("resultContent").hidden = true;
    if (!historySelect.value) {
        status("resultStatus");
        return;
    }
    status("resultStatus", "Carregando resultado…");
    try {
        const data = await api(resultUrl(historySelect.value));
        if (version !== resultVersion) return;
        displayCalculation(data);
        status("resultStatus");
    } catch (error) {
        if (version === resultVersion) status("resultStatus", error.message, "error");
    }
}

function setStep(number, busy = false) {
    const mapped = [0, 2, 3, 5, 4, 4, 4, 5, 1][number];
    const labels = {done: "Conclu\u00edda", pending: "Pendente", ready: "Dispon\u00edvel",
        busy: "Em processamento", optional: "Opcional"};
    [...get("inventorySteps").children].forEach((step, index) => {
        const state = index === mapped ? (busy ? "busy" : "ready")
            : index === 4 ? "optional" : index < mapped || (mapped === 4 && index === 5) ? "done" : "pending";
        step.dataset.state = state;
        step.querySelector("span").textContent = labels[state];
        if (index === mapped) step.setAttribute("aria-current", "step");
        else step.removeAttribute("aria-current");
    });
}

const resultTabs = [...document.querySelectorAll(".result-tabs button")];
function selectTab(tab, focus = false) {
    for (const button of resultTabs) {
        const selected = button === tab;
        button.setAttribute("aria-selected", selected);
        button.tabIndex = selected ? 0 : -1;
        get(button.getAttribute("aria-controls")).hidden = !selected;
    }
    if (tab.id === "filesTab") setStep(7);
    if (focus) tab.focus();
}

resultTabs.forEach((tab, index) => {
    tab.addEventListener("click", () => selectTab(tab));
    tab.addEventListener("keydown", event => {
        const count = resultTabs.length;
        const positions = {ArrowRight: (index + 1) % count, ArrowLeft: (index + count - 1) % count,
            Home: 0, End: count - 1};
        if (!(event.key in positions)) return;
        event.preventDefault();
        selectTab(resultTabs[positions[event.key]], true);
    });
});

function clearSpeciation() {
    get("speciationTables").hidden = true;
    get("speciationWarnings").hidden = true;
    get("speciateButton").hidden = false;
    status("speciationStatus");
    selectTab(get("overviewTab"));
    setStep(3);
}

function displaySpeciation(data) {
    get("speciateButton").hidden = true;
    get("speciationTables").hidden = false;
    get("profileReference").textContent = data.referencia_perfil;
    showWarnings("speciationWarnings", data.avisos.map(motivo => ({motivo})));
    renderTable([["pol_origem", "Poluente de origem"], ["soma_fracoes", "Soma das frações"],
        ["original_g", "Original (g)"], ["derivado_g", "Derivado (g)"], ["residuo_g", "Saldo (g)"]],
    data.balanco.map(row => ({...row, original_g: row.disponivel ? number.format(row.original_g) : "Indisponível",
        derivado_g: row.disponivel ? number.format(row.derivado_g) : "—",
        residuo_g: row.disponivel ? number.format(row.residuo_g) : "—"})), "speciationBalance");
    renderTable([["pol_origem", "Poluente de origem"], ["pol", "Espécie ou poluente"],
        ["emissions", "Emissão (g)"]], data.resumo.map(row =>
        ({...row, emissions: number.format(row.emissions)})), "speciesSummary");
    renderTable([["pol_origem", "Poluente de origem"], ["especie", "Espécie"],
        ["fracao", "Fração"], ["mw", "Massa molecular (g/mol)"]],
    data.perfil.map(row => ({...row, mw: row.mw ?? "Indisponível"})), "speciesProfile");
    renderTable([["id", "Fonte"], ["lat", "Latitude"], ["lon", "Longitude"],
        ["pol_origem", "Poluente de origem"], ["pol", "Espécie ou poluente"],
        ["emissions", "Emissão (g)"]], data.previa.map(row =>
        ({...row, emissions: number.format(row.emissions)})), "speciesPreview");
    status("speciationStatus", `Especiação concluída. ${number.format(data.total_registros)} registros derivados.`, "success");
}

async function loadSpeciation(id) {
    const version = resultVersion;
    try {
        const data = await api(`${resultUrl(id)}/especiacao`);
        if (version === resultVersion && activeResult === id) displaySpeciation(data);
    } catch (error) {
        if (version === resultVersion && activeResult === id && error.status !== 404) {
            status("speciationStatus", error.message, "error");
        }
    }
}

get("speciateButton").addEventListener("click", async () => {
    if (!activeResult) return;
    working = true;
    updateControls();
    status("speciationStatus", "Executando especiação química…");
    try {
        displaySpeciation(await api(`${resultUrl(activeResult)}/especiacao`, {method: "POST"}));
    } catch (error) {
        status("speciationStatus", error.message, "error");
    } finally {
        working = false;
        updateControls();
    }
});

get("nextButton").addEventListener("click", openProcessing);
sectorSelect.addEventListener("change", changeSector);
yearSelect.addEventListener("change", () => {
    updateFuelOptions();
    analyzeFactors();
});
fuelSelect.addEventListener("change", () => {
    updateFuelMapping();
    analyzeFactors();
});
historySelect.addEventListener("change", selectCalculation);

get("calculationForm").addEventListener("submit", async event => {
    event.preventDefault();
    if (get("calculateButton").disabled) return;
    const selections = Object.fromEntries([...get("factorChoices").querySelectorAll("select")]
        .map(select => [select.dataset.pollutant, select.value]));
    working = true;
    updateControls();
    setStep(2, true);
    status("processingStatus", "Calculando emissões…");
    try {
        const data = await api(`${inventoryUrl()}/calcular`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({setor: sectorSelect.value, ano: Number(yearSelect.value),
                combustivel: fuelSelect.value, selecoes: selections})
        });
        ++resultVersion;
        displayCalculation(data);
        status("resultStatus");
        get("calculationResults").scrollIntoView();
        status("processingStatus", "Cálculo concluído.", "success");
        try {
            await loadHistory(data);
        } catch {
            options(historySelect, [[data.calculo_id, "Execução atual"]], "Selecione uma execução");
            historySelect.value = data.calculo_id;
            status("resultStatus", "Histórico indisponível. Recarregue a página para tentar novamente.", "error");
        }
    } catch (error) {
        status("processingStatus", error.message, "error");
    } finally {
        working = false;
        updateControls();
    }
});

get("deleteInventory").addEventListener("click", async () => {
    if (!window.confirm(pegaLocale.translate("Excluir este inventário e todas as suas execuções?"))) return;
    working = true;
    updateControls();
    showMessage("Excluindo inventário…", "");
    try {
        const data = await api(inventoryUrl(), {method: "DELETE"});
        rememberInventory(null);
        resetInterface();
        showMessage(data.mensagem, "success");
    } catch (error) {
        if (error.status === 404) {
            rememberInventory(null);
            resetInterface();
        }
        showMessage(error.message, "error");
    } finally {
        working = false;
        updateControls();
    }
});

async function restoreInventory() {
    let id;
    try {
        id = sessionStorage.getItem(inventoryKey);
    } catch {
        return;
    }
    if (!id) return;
    working = true;
    updateControls();
    showMessage("Carregando inventário…", "");
    try {
        const data = await api(inventoryUrl(id));
        get("fileName").textContent = data.arquivo;
        showResults(data);
        showMessage("Inventário restaurado.", "success");
        await loadHistory();
    } catch (error) {
        if (error.status === 404 && !inventory) rememberInventory(null);
        showMessage(error.message, "error");
    } finally {
        working = false;
        updateControls();
    }
}

// RESPEITAR PREFERÊNCIA DE MOVIMENTO

if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    for (const video of document.querySelectorAll(".hero-video video, .brand-video")) {
        video.autoplay = false;
        video.pause();
        if (video.closest(".hero-video")) video.controls = true;
    }
}


// INICIALIZAÇÃO

checkServer();
restoreInventory();
