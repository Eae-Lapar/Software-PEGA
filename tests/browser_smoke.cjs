const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs/promises");
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
        const ux = process.env.PEGA_UX_CAPTURAS;
        const capture = async (name, locator) => {
            if (ux) await locator.screenshot({path: path.join(ux, name + ".png"), animations: "disabled"});
        };
        await page.goto(origin);
        await page.locator("#serverStatus.online").waitFor();
        const language = page.locator("#uiLanguage");
        assert.equal(await page.locator(".required-columns code").count(), 7);
        await capture("colunas", page.locator(".required-columns"));
        await capture("inicio", page.locator(".hero"));
        await language.selectOption("en-US");
        await page.getByRole("heading", {name: "Required columns"}).waitFor();
        await capture("inicio-en", page.locator(".hero"));
        await capture("navbar-en", page.locator(".header"));
        await page.reload();
        assert.equal(await language.inputValue(), "en-US");
        await page.locator("#fileInput").setInputFiles({
            name: "synthetic.csv", mimeType: "text/csv", buffer: Buffer.from("ID;year\ns1;2017")
        });
        await page.getByText(/Required columns not found:/).waitFor();
        await language.selectOption("pt-BR");
        await page.setViewportSize({width: 390, height: 844});
        await page.locator("#menuToggle").focus();
        await page.keyboard.press("Enter");
        await page.getByRole("navigation").getByRole("link", {name: "Inventário"}).waitFor();
        await page.keyboard.press("Escape");
        assert.equal(await page.locator("#menuToggle").getAttribute("aria-expanded"), "false");
        await page.setViewportSize({width: 1366, height: 900});
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
        await capture("importacao", page.locator("#importacao"));
        await page.locator("#nextButton").click();
        await page.waitForFunction(() => document.querySelector("#sectorSelect").value === "1.A.1.a");
        assert.equal(await page.locator("#sectorSelect").inputValue(), "1.A.1.a");
        await page.locator("#yearSelect").selectOption("2017");
        await page.locator("#fuelSelect").selectOption("Biomass");
        await page.locator("#fuelMapping").waitFor();
        assert.match(await page.locator("#fuelMapping").innerText(), /Biomass_thermal → Biomass/);
        await capture("configuracao", page.locator("#processamento"));
        await page.locator("#calculateButton").click();
        await page.locator("#resultContent").waitFor();
        assert.equal(await page.locator("#resultMetrics dt").count(), 8);
        async function fullZip() {
            await page.getByRole("tab", {name: "Arquivos"}).click();
            const ready = page.waitForResponse(r => r.url().endsWith("/exportacoes/lotes") && r.request().method() === "POST");
            const downloaded = page.waitForEvent("download");
            await page.locator("#exportZipAll").click();
            const result = await ready;
            assert.equal(result.status(), 200, await result.text());
            assert.deepEqual((await result.json()).omitidos, []);
            assert.equal(await (await downloaded).failure(), null);
            if (ux) {
                await page.getByText(/ZIP pronto com/).waitFor();
                await capture("zip", page.locator("#exportStatus"));
            }
            await page.getByRole("tab", {name: "Visão geral"}).click();
        }
        await fullZip();
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
        await fullZip();
        await page.locator("#modelingPanel summary").click();
        await page.locator("#modelingDomain").setInputFiles(process.argv[3]);
        await page.locator("#modelingAnnual").check();
        await page.locator("#modelingClock").fill("UTC");
        await page.locator("#modelingRun").click();
        await page.locator("#modelingStatus.success").waitFor();
        await capture("dashboard", page.locator("#resultMetrics"));
        await capture("analises", page.locator(".analysis-grid"));
        assert.match(await page.locator("#modelingStatus").innerText(), /8760 horas \(UTC\)/);
        assert.match(await page.locator("#speciationWarnings").innerText(), /PM2\.5/);
        await page.getByRole("tab", {name: "Tabelas"}).click();
        const speciesSearch = page.getByRole("searchbox", {name: "Buscar em Emissões por espécie e poluentes preservados", exact: true});
        await speciesSearch.fill("PSO4");
        assert.equal(await page.locator("#speciesSummary tbody tr").count(), 2);
        await speciesSearch.clear();
        assert.match(await page.locator("#emissionSummary").innerText(), /PM2\.5/);
        const emissionTable = page.locator("#emissionSummary");
        const emissionTools = page.locator(".table-toolbar").filter({has: page.getByRole("link", {name: "Baixar CSV", exact: true})}).first();
        await emissionTools.locator("input").fill("PM2.5");
        assert.equal(await emissionTable.locator("tbody tr").count(), 1);
        await emissionTools.locator("input").clear();
        await emissionTable.getByRole("button", {name: "Emissão", exact: true}).click();
        assert.equal(await emissionTable.locator("th[aria-sort]").getAttribute("aria-sort"), "ascending");
        await capture("tabelas", page.locator("#tablesPanel"));
        await page.getByRole("tab", {name: "Imagens e gráficos"}).click();
        await page.locator("#figureImage").waitFor();
        await page.locator("#figureEnlarge").click();
        await page.locator("#figureDialog[open]").waitFor();
        if (ux) await page.screenshot({path: path.join(ux, "ampliacao.png")});
        await page.keyboard.press("Escape");
        assert.equal(await page.locator("#figureDialog").evaluate(dialog => dialog.open), false);
        assert.equal(await page.locator("#figureEnlarge").evaluate(button => document.activeElement === button), true);
        await page.locator("#figureEnlarge").click();
        await page.locator("#figureDialog .lightbox-close").click();
        await page.locator("#figureEnlarge").click();
        await page.mouse.click(1, 1);
        assert.equal(await page.locator("#figureDialog").evaluate(dialog => dialog.open), false);
        await capture("graficos", page.locator("#figureControls"));
        assert.match(await page.locator("#figureCaption").innerText(), /Totais por poluente/);
        async function imageDownload(prefix, format, dpi) {
            await page.locator(`#${prefix}Format`).selectOption(format);
            if (dpi) await page.locator(`#${prefix}Dpi`).selectOption(dpi);
            const event = page.waitForEvent("download");
            await page.locator(`#${prefix}Download`).click();
            const downloaded = await event;
            assert.equal(await downloaded.failure(), null);
            assert.ok(downloaded.suggestedFilename().endsWith("." + format));
            const bytes = await fs.readFile(await downloaded.path());
            if (format === "pdf") assert.equal(bytes.subarray(0, 5).toString(), "%PDF-");
            if (format === "svg") assert.match(bytes.toString(), /<svg/);
            if (format === "png") {
                assert.equal(bytes.subarray(1, 4).toString(), "PNG");
                const phys = bytes.indexOf("pHYs");
                assert.ok(phys > 0);
                assert.equal(bytes.readUInt32BE(phys + 4), Math.round(Number(dpi) / .0254));
            }
            return {name: downloaded.suggestedFilename(), bytes, url: downloaded.url()};
        }
        assert.match((await imageDownload("figure", "pdf")).name, /totais-2017.*\.pdf$/);
        await page.locator("#figureCategory").selectOption("especiacao");
        await page.waitForFunction(() => document.querySelector("#figureCaption").textContent.includes("Balanço"));
        await imageDownload("figure", "svg");
        await page.locator("#figureCategory").selectOption("temporal");
        await page.locator("#figureType").selectOption("mensal");
        await page.locator("#figureStart").fill("2017-02-01");
        await page.locator("#figureEnd").fill("2017-02-28");
        await page.waitForFunction(() => document.querySelector("#figureCaption").textContent.includes("UTC") &&
            !document.querySelector("#figurePreview").hidden);
        const annual = await imageDownload("figure", "png", "600");
        assert.match(annual.name, /^mensal-/);
        if (process.env.PEGA_EXEMPLOS) {
            await page.locator("#chartsPanel").screenshot({
                path: path.join(process.env.PEGA_EXEMPLOS, "interface-projecao-anual-sintetica.png"), style: estiloCaptura
            });
        }
        await page.locator("#figureCategory").selectOption("espacial");
        const svgMapa = page.locator("#spatialMap svg");
        await svgMapa.waitFor();
        await capture("mapa", page.locator("#spatialCharts"));
        const viewBox = await svgMapa.getAttribute("viewBox");
        await language.selectOption("en-US");
        await page.getByRole("heading", {name: "Interactive map", exact: true}).waitFor();
        assert.equal(await svgMapa.getAttribute("viewBox"), viewBox);
        await capture("mapa-en", page.locator("#spatialCharts"));
        await language.selectOption("pt-BR");
        assert.equal(await page.locator("#figureType").inputValue(), "mapa-interativo");
        assert.equal(await page.locator("#spatialModeLabel").isHidden(), true);
        await page.locator("#figureType").selectOption("mapa-cientifico");
        await page.locator("#spatialMap img").waitFor();
        assert.equal(await svgMapa.count(), 0);
        const firstMap = await imageDownload("spatial", "png", "300");
        await page.locator("#spatialPalette").selectOption("plasma");
        const nextMap = await imageDownload("spatial", "png", "300");
        assert.match(nextMap.name, /plasma/);
        assert.notDeepEqual(firstMap.bytes, nextMap.bytes);
        function mapFilters(url) {
            const params = new URL(url).searchParams;
            params.delete("dpi");
            params.delete("download");
            return Object.fromEntries(params);
        }
        const previewMap = await page.locator("#spatialMap img").evaluate(img => img.src);
        assert.deepEqual(mapFilters(nextMap.url), mapFilters(previewMap));
        await imageDownload("spatial", "png", "600");
        if (process.env.PEGA_EXEMPLOS) {
            await page.locator("#spatialCharts").screenshot({
                path: path.join(process.env.PEGA_EXEMPLOS, "controles-mapa-cientifico.png"), style: estiloCaptura
            });
        }
        await page.locator("#spatialMode").selectOption("grade");
        await page.waitForFunction(() => document.querySelector("#spatialMap img")?.src.includes("modo=grade"));
        await page.locator("#spatialPalette").selectOption("plasma");
        await page.locator("#spatialScale").selectOption("log");
        await page.locator("#figureType").selectOption("mapa-interativo");
        await svgMapa.waitFor();
        await page.locator("#spatialMap circle").first().focus();
        assert.match(await page.locator("#spatialPointInfo").innerText(), /001/);
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
        await page.locator("#spatialLevel").selectOption("regiao");
        await page.locator("#spatialTerritory").selectOption("3");
        await page.waitForFunction(() => document.querySelector("#spatialIndicators").textContent.startsWith("Sudeste"));
        assert.match(await page.locator("#spatialRanking").innerText(), /001.*RJ01|RJ01.*001/s);
        await page.locator("#spatialNational").click();
        await page.waitForFunction(() => document.querySelector("#spatialIndicators").textContent.startsWith("Brasil"));
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
        const rjExport = await imageDownload("spatial", "svg");
        assert.match(rjExport.name, /PM2\.5.*33/);
        if (process.env.PEGA_EXEMPLOS) {
            await page.locator("#spatialCharts").screenshot({
                path: path.join(process.env.PEGA_EXEMPLOS, "interativo-rio.png"), style: estiloCaptura
            });
        }
        await page.getByRole("tab", {name: "Arquivos"}).click();
        const nc = page.waitForEvent("download");
        await page.getByRole("link", {name: "Baixar inventário em grade · original (NC)"}).click();
        assert.equal((await nc).suggestedFilename(), "original-emissoes-grade.nc");
        const mapaRJ = page.getByRole("link", {name: "Baixar mapa (SVG)"});
        const urlRJ = await mapaRJ.getAttribute("href");
        assert.match(urlRJ, /codigo=33/);
        assert.match(await (await context.request.get(origin + urlRJ)).text(), /Rio de Janeiro/);
        await page.getByRole("tab", {name: "Imagens e gráficos"}).click();
        await page.locator("#spatialNational").click();
        await page.waitForFunction(() => document.querySelector("#spatialIndicators").textContent.startsWith("Brasil"));
        await svgMapa.waitFor();
        await svgMapa.locator('[data-uf="35"]').press("Enter");
        await page.waitForFunction(() => document.querySelector("#spatialIndicators").textContent.startsWith("São Paulo"));
        await page.locator("#spatialSeries").selectOption({label: "BC"});
        const spExport = await imageDownload("spatial", "pdf");
        assert.match(spExport.name, /BC.*35/);
        await page.locator("#spatialNational").click();
        await page.waitForFunction(() => document.querySelector("#spatialIndicators").textContent.startsWith("Brasil"));
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
        await imageDownload("temporal", "svg");
        await imageDownload("temporal", "png", "300");
        await imageDownload("temporal", "pdf");
        if (process.env.PEGA_EXEMPLOS) {
            await page.locator("#temporalCharts").screenshot({
                path: path.join(process.env.PEGA_EXEMPLOS, "controles-perfil-temporal.png"), style: estiloCaptura
            });
        }

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
        await page.locator('[data-category="inventario"]').check();
        assert.equal(await page.locator('input[data-id^="inventario/"]:checked').count(), 5);
        const categoryZip = page.waitForEvent("download");
        await page.locator("#exportZip").click();
        assert.equal(await (await categoryZip).failure(), null);
        await page.locator("#exportAll").check();
        assert.equal(await page.locator("input[data-id]:not(:checked)").count(), 0);
        await page.locator("#exportAll").uncheck();
        await page.locator('[data-id="inventario/resumo.csv"]').check();
        const zip = page.waitForEvent("download");
        await page.locator("#exportZip").click();
        assert.match((await zip).suggestedFilename(), /^PEGA-.+\.zip$/);
        await page.locator("#exportMode").selectOption("resumido");
        await page.locator("#exportLanguage").selectOption("en");
        await page.locator("#exportUnit").selectOption("kg");
        await page.locator("#exportPollutants").selectOption(["PM2.5"]);
        await capture("relatorios", page.locator("#exportReport"));
        await capture("exportacoes", page.locator("#exportCatalog"));
        const resolution = page.locator(".export-resolution select");
        await resolution.selectOption("600");
        const figureRow = page.locator(".export-file").filter({has: page.locator("select[data-format]")}).first();
        assert.match(await figureRow.getByRole("link").getAttribute("href"), /-600dpi\.png$/);
        await figureRow.locator("select").selectOption("pdf");
        assert.match(await figureRow.getByRole("link").getAttribute("href"), /\.pdf$/);
        await figureRow.locator("select").selectOption("svg");
        assert.match(await figureRow.getByRole("link").getAttribute("href"), /\.svg$/);
        await capture("resolucao", page.locator(".export-group").filter({has: resolution}));
        const report = page.waitForEvent("download");
        await page.locator("#exportPdf").click();
        assert.equal((await report).suggestedFilename(), "resumo-executivo.pdf");
        await page.setViewportSize({width: 390, height: 844});
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
        await page.setViewportSize({width: 1280, height: 900});
        if (process.env.PEGA_EXEMPLOS) {
            await page.locator("#filesPanel").screenshot({
                path: path.join(process.env.PEGA_EXEMPLOS, "central-exportacoes-sintetica.png"), style: estiloCaptura
            });
        }
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
        await page.waitForFunction(() => document.querySelector("#resultMetrics").textContent.includes("Biogas"));
        const biomass = await page.locator("#calculationHistory option").filter({hasText: "Biomass"}).getAttribute("value");
        await page.locator("#calculationHistory").selectOption(biomass);
        await page.waitForFunction(() =>
            document.querySelector("#resultMetrics").textContent.includes("Biomass") &&
            !document.querySelector("#resultContent").hidden);
        await page.locator("#speciationStatus.success").waitFor();
        for (const width of [390, 768, 1024, 1366, 1920]) {
            await page.setViewportSize({width, height: 900});
            for (const name of ["Visão geral", "Tabelas", "Imagens e gráficos", "Arquivos"]) {
                await page.getByRole("tab", {name}).click();
                if (name === "Imagens e gráficos") await page.locator("#figureImage").waitFor();
                if (name === "Arquivos") await page.locator("#exportActions").waitFor();
                const overflowing = await page.evaluate(() => {
                    if (document.documentElement.scrollWidth <= innerWidth) return [];
                    return [...document.querySelectorAll("body *")].filter(el =>
                        !el.closest(".table-container,svg") && el.getBoundingClientRect().right > innerWidth + 1)
                        .slice(0, 12).map(el => el.id || el.className || el.tagName);
                });
                assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true,
                    `Rolagem horizontal a ${width}px em ${name}: ${overflowing.join(", ")}`);
            }
        }
        await page.getByRole("tab", {name: "Visão geral"}).click();
        await language.selectOption("en-US");
        await page.getByText("Inventory year", {exact: true}).waitFor();
        assert.match(await page.locator("#resultMetrics").innerText(), /1,700 GJ/);
        await capture("dashboard-en", page.locator("#resultMetrics"));
        await page.getByRole("tab", {name: "Files", exact: true}).click();
        await page.getByRole("heading", {name: "Maps and figures", exact: true}).waitFor();
        await capture("exportacoes-en", page.locator("#exportCatalog"));
        for (const width of [390, 768, 1024, 1366, 1920]) {
            await page.setViewportSize({width, height: 900});
            for (const name of ["Overview", "Tables", "Figures and charts", "Files"]) {
                await page.getByRole("tab", {name, exact: true}).click();
                assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true,
                    `Overflow in English at ${width}px in ${name}`);
            }
        }
        await language.selectOption("pt-BR");
        await page.getByRole("tab", {name: "Visão geral"}).click();

        await page.setViewportSize({width: 390, height: 844});
        if (ux) {
            await page.locator("#calculationResults").evaluate(section =>
                section.scrollIntoView({block: "start", behavior: "instant"}));
            await page.screenshot({path: path.join(ux, "mobile.png"), animations: "disabled"});
        }
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
