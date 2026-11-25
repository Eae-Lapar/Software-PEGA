const assert = require("node:assert/strict");
const path = require("node:path");
const {chromium} = require(process.env.PEGA_PLAYWRIGHT_MODULE || "playwright-core");
const estiloCaptura = '.header {visibility: hidden} #spatialCharts::before {content: "Exemplo sintético"; display: block; color: #71e8cc}';

async function main() {
    const browser = await chromium.launch({
        executablePath: process.env.PEGA_BROWSER_EXECUTABLE || undefined
    });
    try {
        const context = await browser.newContext({viewport: {width: 1280, height: 900}});
        const page = await context.newPage();
        const errors = [];
        page.on("pageerror", error => errors.push(error.message));
        const origin = process.argv[2];
        await page.goto(origin);
        await page.locator("#serverStatus.online").waitFor();
        const upload = contents => page.locator("#fileInput").setInputFiles({
            name: "sintetico.csv", mimeType: "text/csv", buffer: Buffer.from(contents)
        });
        const header = "ID;Fuel_type;Granted_power_MW;latitude;longitude;year;Fuel_consumed_plant_GJ\n";
        await upload(header + "001;Biomass_thermal;20;0;0;2017;-1\n");
        await page.locator("#message.error").waitFor();
        assert.equal(await page.locator("#nextButton").isDisabled(), true);
        await upload(header + [
            "001;Biomass_thermal;20;-23.5;-46.6;2017;1000",
            "RJ01;Biomass_thermal;30;-22.92;-43.25;2017;700",
            "002;Natural Gas;20;-23.5;-46.6;2017;1000",
            "003;Biogas;20;-23.5;-46.6;2018;1000"
        ].join("\n"));
        await page.locator("#message.success").waitFor();
        await page.locator("#nextButton").click();
        await page.waitForFunction(() => document.querySelector("#sectorSelect").value === "1.A.1.a");
        assert.equal(await page.locator("#sectorSelect").inputValue(), "1.A.1.a");
        await page.locator("#yearSelect").selectOption("2017");
        await page.locator("#fuelSelect").selectOption("Biomass");
        await page.locator("#fuelMapping").waitFor();
        assert.match(await page.locator("#fuelMapping").innerText(), /Biomass_thermal → Biomass/);
        await page.locator("#calculateButton").click();
        await page.locator("#resultContent").waitFor();
        await page.locator("#speciateButton").click();
        await page.locator("#speciationStatus.success").waitFor();
        await page.locator("#temporalSource").selectOption("especiada");
        await page.locator("#temporalRun").click();
        await page.locator("#temporalStatus.success").waitFor();
        const grade = {type: "FeatureCollection", features: [{type: "Feature",
            properties: {id_grid: "A"}, geometry: {type: "Polygon", coordinates: [
                [[-48, -25], [-46, -25], [-46, -22], [-48, -22], [-48, -25]]
            ]}}]};
        await page.locator("#spatialGrid").setInputFiles({
            name: "sintetico.geojson", mimeType: "application/geo+json",
            buffer: Buffer.from(JSON.stringify(grade))
        });
        await page.locator("#spatialRun").click();
        await page.locator("#spatialStatus.success").waitFor();
        await page.locator("#modelingPanel summary").click();
        await page.locator("#modelingDomain").setInputFiles(process.argv[3]);
        await page.locator("#modelingAnnual").check();
        await page.locator("#modelingClock").fill("UTC");
        await page.locator("#modelingRun").click();
        await page.locator("#modelingStatus.success").waitFor();
        assert.match(await page.locator("#modelingStatus").innerText(), /8760 horas \(UTC\)/);
        assert.match(await page.locator("#speciationWarnings").innerText(), /PM2\.5/);
        await page.getByRole("tab", {name: "Tabelas"}).click();
        assert.match(await page.locator("#speciesSummary").innerText(), /PSO4/);
        assert.match(await page.locator("#emissionSummary").innerText(), /PM2\.5/);
        await page.getByRole("tab", {name: "Imagens e gráficos"}).click();
        await page.locator("#figureImage").waitFor();
        assert.match(await page.locator("#figureCaption").innerText(), /Totais por poluente/);
        const scientificPdf = page.waitForEvent("download");
        await page.locator("#figurePdf").click();
        assert.match((await scientificPdf).suggestedFilename(), /totais-2017.*\.pdf$/);
        await page.locator("#figureCategory").selectOption("especiacao");
        await page.waitForFunction(() => document.querySelector("#figureCaption").textContent.includes("Balanço"));
        await page.locator("#figureCategory").selectOption("temporal");
        await page.locator("#figureType").selectOption("mensal");
        await page.locator("#figureStart").fill("2017-02-01");
        await page.locator("#figureEnd").fill("2017-02-28");
        await page.waitForFunction(() => document.querySelector("#figureCaption").textContent.includes("UTC") &&
            !document.querySelector("#figurePreview").hidden);
        if (process.env.PEGA_EXEMPLOS) {
            await page.locator("#chartsPanel").screenshot({
                path: path.join(process.env.PEGA_EXEMPLOS, "interface-projecao-anual-sintetica.png"), style: estiloCaptura
            });
        }
        await page.locator("#figureCategory").selectOption("espacial");
        await page.locator("#spatialMap img").waitFor();
        await page.locator("#spatialMode").selectOption("grade");
        await page.locator("#spatialMap img").waitFor();
        await page.locator("#spatialPalette").selectOption("plasma");
        await page.locator("#spatialScale").selectOption("log");
        await page.locator("#spatialMode").selectOption("interativo");
        await page.locator("#spatialMap circle").first().focus();
        assert.match(await page.locator("#spatialPointInfo").innerText(), /001/);
        const svgMapa = page.locator("#spatialMap svg");
        if (process.env.PEGA_EXEMPLOS) {
            await page.locator("#spatialCharts").screenshot({
                path: path.join(process.env.PEGA_EXEMPLOS, "interativo-brasil.png"), style: estiloCaptura
            });
        }
        let liberar, interceptar;
        const aguardando = new Promise(resolve => { liberar = resolve; });
        const interceptada = new Promise(resolve => { interceptar = resolve; });
        const atraso = async route => { interceptar(); await aguardando; await route.continue(); };
        await page.route("**/territorio/*?**", atraso, {times: 1});
        const scale = page.locator("#spatialScale");
        await scale.scrollIntoViewIfNeeded();
        await scale.focus();
        const medir = () => page.evaluate(() => ({
            scroll: window.scrollY, altura: document.querySelector("#spatialMap").offsetHeight,
            foco: document.activeElement.id
        }));
        const antesDaConsulta = await medir();
        await scale.selectOption("linear");
        await interceptada;
        assert.deepEqual(await medir(), antesDaConsulta);
        liberar();

        await page.waitForFunction(() => !document.querySelector("#spatialMap").hasAttribute("aria-busy"));
        assert.deepEqual(await medir(), antesDaConsulta);
        assert.equal(await scale.inputValue(), "linear");
        const viewBoxInicial = await svgMapa.getAttribute("viewBox");
        await svgMapa.locator('[data-uf="33"]').press("Enter");
        await page.waitForFunction(() => document.querySelector("#spatialIndicators").textContent.includes("Rio de Janeiro"));
        await page.waitForFunction(inicial => {
            const atual = document.querySelector("#spatialMap svg")?.getAttribute("viewBox");
            return atual && Number(atual.split(" ")[2]) < Number(inicial.split(" ")[2]) * .13;
        }, viewBoxInicial);
        assert.equal(await svgMapa.locator('circle[role="button"]').count(), 1);
        await page.locator("#spatialSeries").selectOption({label: "PM2.5"});
        await page.waitForFunction(() => document.querySelector("#spatialLegend").textContent.includes("PM2.5"));
        await svgMapa.locator('circle[role="button"]').focus();
        assert.match(await page.locator("#spatialPointInfo").innerText(), /RJ01.*Rio de Janeiro.*Potência informada/);
        if (process.env.PEGA_EXEMPLOS) {
            await page.locator("#spatialCharts").screenshot({
                path: path.join(process.env.PEGA_EXEMPLOS, "interativo-rio.png"), style: estiloCaptura
            });
        }
        await page.getByRole("tab", {name: "Arquivos"}).click();
        const nc = page.waitForEvent("download");
        await page.getByRole("link", {name: "Baixar inventário em grade (NetCDF)"}).click();
        assert.equal((await nc).suggestedFilename(), "emissoes-grade.nc");
        const mapaRJ = page.getByRole("link", {name: "Baixar mapa (SVG)"});
        const urlRJ = await mapaRJ.getAttribute("href");
        assert.match(urlRJ, /codigo=33/);
        assert.match(await (await context.request.get(origin + urlRJ)).text(), /Rio de Janeiro/);
        await page.getByRole("tab", {name: "Imagens e gráficos"}).click();
        await page.locator("#spatialNational").click();
        await page.waitForFunction(() => document.querySelector("#spatialIndicators").textContent.startsWith("Brasil"));
        await svgMapa.waitFor();
        const antesDoZoom = await svgMapa.getAttribute("viewBox");
        await svgMapa.dispatchEvent("wheel", {deltaY: -120, cancelable: true});
        assert.notEqual(await svgMapa.getAttribute("viewBox"), antesDoZoom);
        await page.setViewportSize({width: 390, height: 844});
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
        await page.setViewportSize({width: 1280, height: 900});
        await page.locator("#figureCategory").selectOption("temporal");
        await page.locator("#figureType").selectOption("interativo");
        assert.equal(await page.locator("#temporalPreview circle title").count(), 24);
        await page.locator("#temporalPlot").selectOption("semanal");
        assert.equal(await page.locator("#temporalPreview rect").count(), 8);
        await page.locator("#temporalPlot").selectOption("combinado");
        assert.equal((await page.locator("#temporalPreview polyline").getAttribute("points")).split(" ").length, 168);
        await page.locator("#temporalPlot").selectOption("calor");
        assert.equal(await page.locator("#temporalPreview rect title").count(), 168);
        await page.locator("#temporalUnit").selectOption("kg");
        const svg = page.waitForEvent("download");
        await page.locator("#temporalSvg").click();
        assert.match((await svg).suggestedFilename(), /\.svg$/);
        const png = page.waitForEvent("download");
        await page.locator("#temporalPng").click();
        assert.match((await png).suggestedFilename(), /\.png$/);
        await page.evaluate(() => { window.print = () => {}; });
        await page.locator("#temporalPdf").click();
        assert.equal(await page.locator("#temporalPreview rect").first().getAttribute("fill"), "#ffffff");
        const pdf = await page.pdf();
        assert.equal(pdf.subarray(0, 5).toString(), "%PDF-");

        await page.getByRole("tab", {name: "Arquivos"}).click();
        const derived = page.getByRole("link", {name: "Baixar resumo por espécie (CSV)"});
        const derivedDownload = page.waitForEvent("download");
        await derived.click();
        assert.equal((await derivedDownload).suggestedFilename(), "resumo_especies.csv");
        const summary = page.getByRole("link", {name: "Baixar resumo (CSV)"});
        const summaryPath = await summary.getAttribute("href");
        const downloaded = page.waitForEvent("download");
        await summary.click();
        assert.equal((await downloaded).suggestedFilename(), "resumo.csv");
        const response = await context.request.get(origin + summaryPath);
        assert.match(await response.text(), /PM2\.5,226100/);
        const otherContext = await browser.newContext();
        assert.equal((await otherContext.request.get(origin + summaryPath)).status(), 404);
        await otherContext.close();

        await page.locator("#fuelSelect").selectOption("Natural Gas");
        const choice = page.getByLabel("Referência para SOx");
        await choice.waitFor();
        assert.equal(await page.locator("#calculateButton").isDisabled(), true);
        await choice.selectOption({index: 2});
        await page.locator("#calculateButton").click();
        await page.waitForFunction(() =>
            document.querySelector("#resultMetrics").textContent.includes("Natural Gas"));
        await page.locator("#yearSelect").selectOption("2018");
        assert.equal(await page.locator("#fuelSelect").inputValue(), "Biogas");
        await page.locator("#factorWarnings").waitFor();
        assert.match(await page.locator("#factorWarnings").innerText(), /Pb/);
        await page.locator("#calculateButton").click();
        await page.waitForFunction(() =>
            document.querySelector("#resultMetrics").textContent.includes("Biogas"));
        await page.waitForFunction(() => document.querySelector("#calculationHistory").options.length === 4);
        await page.reload();
        await page.locator("#resultContent").waitFor();
        assert.match(await page.locator("#resultMetrics").innerText(), /Biogas/);
        await page.locator("#calculationHistory").selectOption({index: 3});
        await page.waitForFunction(() =>
            document.querySelector("#resultMetrics").textContent.includes("Biomass") &&
            !document.querySelector("#resultContent").hidden);
        await page.locator("#speciationStatus.success").waitFor();

        await page.setViewportSize({width: 390, height: 844});
        assert.equal(await page.evaluate(() =>
            document.documentElement.scrollWidth <= window.innerWidth), true);
        page.once("dialog", dialog => dialog.accept());
        await page.locator("#deleteInventory").click();
        await page.getByText("Inventário excluído com sucesso.").waitFor();
        assert.equal((await context.request.get(origin + summaryPath)).status(), 404);
        assert.deepEqual(errors, []);
        console.log("Fluxo aprovado: upload, fatores, emissões, especiação, temporal, gráficos, histórico, downloads e exclusão.");
    } finally {
        await browser.close();
    }
}

main().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
