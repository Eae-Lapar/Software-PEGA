/* Navegação vetorial local, com visualização simplificada do IBGE. */
function criarMapaTerritorial(config) {
    const {basemap, dados, nivel, codigo, unidade, marcador, camadas, selecionar, mostrar} = config;
    const namespace = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(namespace, "svg");
    const add = (parent, tag, attrs) => {
        const el = document.createElementNS(namespace, tag);
        for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
        parent.append(el);
        return el;
    };
    svg.setAttribute("role", "group");
    svg.setAttribute("aria-label", "Mapa interativo de fontes emissoras");
    const rings = geo => (geo.type === "Polygon" ? [geo.coordinates] : geo.coordinates).flat();
    const path = geo => rings(geo).map(ring =>
        "M" + ring.map(([x, y]) => `${x * 10},${-y * 10}`).join("L") + "Z").join("");
    const dentro = f => nivel === "brasil" ||
        String(f.properties[nivel === "uf" ? "CD_UF" : "CD_REGIAO"]) === codigo;
    const limites = [Infinity, Infinity, -Infinity, -Infinity];
    const incluir = (x, y) => {
        limites[0] = Math.min(limites[0], x);
        limites[1] = Math.min(limites[1], y);
        limites[2] = Math.max(limites[2], x);
        limites[3] = Math.max(limites[3], y);
    };
    for (const f of basemap.features.filter(dentro)) {
        for (const ring of rings(f.geometry)) for (const [x, y] of ring) incluir(x * 10, -y * 10);
    }
    const pontos = [...dados.pontos];
    const presentes = new Set(pontos.map(p => JSON.stringify([p.id, p.lat, p.lon, p.alt])));
    for (const p of dados.ranking) {
        const chave = JSON.stringify([p.id, p.lat, p.lon, p.alt]);
        if (p.lon != null && !presentes.has(chave)) pontos.push(p);
    }
    const largura = Math.max(5, limites[2] - limites[0]);
    const altura = Math.max(5, limites[3] - limites[1]);
    const alvo = [limites[0] - largura * .07, limites[1] - altura * .07, largura * 1.14, altura * 1.14];
    let box = config.anterior || config.atual || alvo;
    let frame;
    const atualizar = () => svg.setAttribute("viewBox", box.join(" "));
    const enquadrar = destino => {
        cancelAnimationFrame(frame);
        const anterior = [...box];
        const inicio = performance.now();
        const reduzir = matchMedia("(prefers-reduced-motion: reduce)").matches;
        function animar(agora) {
            const progresso = reduzir ? 1 : Math.min(1, (agora - inicio) / 330);
            const s = 1 - (1 - progresso) ** 3;
            box = anterior.map((v, i) => v + (destino[i] - v) * s);
            atualizar();
            if (progresso < 1) frame = requestAnimationFrame(animar);
        }
        frame = requestAnimationFrame(animar);
    };
    atualizar();
    if (config.anterior) enquadrar(alvo);
    const zoom = fator => {
        cancelAnimationFrame(frame);
        if (box[2] * fator < 2 || box[2] * fator > 5000) return;
        box = [box[0] + box[2] * (1 - fator) / 2, box[1] + box[3] * (1 - fator) / 2,
            box[2] * fator, box[3] * fator];
        atualizar();
    };
    const clicavel = (el, nome, acao) => {
        el.setAttribute("role", "button");
        el.setAttribute("tabindex", "0");
        el.setAttribute("aria-label", nome);
        el.addEventListener("click", acao);
        el.addEventListener("keydown", e => {
            if (e.key === "Enter" || e.key === " ") { e.preventDefault(); acao(); }
        });
    };
    for (const f of basemap.features) {
        const a = f.properties;
        const sombreado = camadas.territorial && dentro(f) && dados.cores_uf[a.CD_UF];
        const el = add(svg, "path", {d: path(f.geometry), fill: sombreado || (dentro(f) ? "#2f4968" : "#1e3046"),
            "fill-rule": "evenodd", stroke: camadas.estados ? (dentro(f) ? "#cbd8e7" : "#7488a3") : "none",
            "stroke-width": dentro(f) ? 1.4 : .5, "vector-effect": "non-scaling-stroke",
            "data-uf": a.CD_UF});
        if (camadas.territorial) {
            const massa = dados.totais.uf[a.CD_UF];
            add(el, "title", {}).textContent = massa == null ? a.NM_UF :
                `${a.NM_UF} · ${number.format(massa * config.fator)} ${unidade} (massa total)`;
        }
        clicavel(el, nivel === "regiao" ? a.NM_REGIAO : a.NM_UF,
            () => nivel === "regiao" ? selecionar("regiao", a.CD_REGIAO) : selecionar("uf", a.CD_UF));
    }
    if (camadas.regioes) {
        for (const f of basemap.regioes) {
            add(svg, "path", {d: path(f.geometry), fill: "none", stroke: "#71e8cc", "stroke-width": 1.25,
                "vector-effect": "non-scaling-stroke", "pointer-events": "none"});
        }
    }
    for (const celula of dados.grade_visual?.features || []) {
        const el = add(svg, "path", {d: path(celula.geometry), fill: celula.cor || "none",
            "fill-opacity": .64, "fill-rule": "evenodd", stroke: "#f0dcb8", "stroke-width": .7,
            "vector-effect": "non-scaling-stroke", "pointer-events": "none"});
        add(el, "title", {}).textContent = `Célula ${celula.id}`;
    }
    const grupos = new Map();
    for (const p of pontos) {
        const chave = `${p.lon},${p.lat}`;
        if (!grupos.has(chave)) grupos.set(chave, []);
        grupos.get(chave).push(p);
    }
    const maximo = dados.legenda.max || 1;
    let destaque;
    const escalaMarcadores = Math.max(0.14, Math.min(largura, altura) / 420);
    const marcadores = new Map();
    const seleciona = (p, posicionar) => {
        const chave = `${p.lon},${p.lat}`;
        if (destaque) destaque.setAttribute("stroke", "#ffffff");
        destaque = marcadores.get(chave);
        if (destaque) destaque.setAttribute("stroke", "#ffbf47");
        mostrar(grupos.get(chave) || [p], p);
        if (posicionar && p.lon != null) {
            const tamanho = Math.min(box[2], Math.max(alvo[2] * .3, 12));
            const alt = tamanho * alvo[3] / alvo[2];
            enquadrar([p.lon * 10 - tamanho / 2, -p.lat * 10 - alt / 2, tamanho, alt]);
        }
    };
    if (camadas.calor) {
        const defs = add(svg, "defs", {});
        const gradiente = add(defs, "radialGradient", {id: "spatialHeat"});
        add(gradiente, "stop", {offset: "0%", "stop-color": "#ff9940", "stop-opacity": ".85"});
        add(gradiente, "stop", {offset: "100%", "stop-color": "#ff9940", "stop-opacity": "0"});
    }
    for (const [chave, grupo] of grupos) {
        const p = grupo.reduce((maior, atual) => atual.valor > maior.valor ? atual : maior);
        const fracao = Math.min(1, Math.max(0, p.valor / maximo));
        const x = p.lon * 10, y = -p.lat * 10;
        if (camadas.calor && fracao) {
            add(svg, "circle", {cx: x, cy: y, r: escalaMarcadores * 22, fill: "url(#spatialHeat)",
                opacity: .23 + .77 * fracao, "pointer-events": "none"});
        }
        if (!camadas.pontos) continue;
        const el = add(svg, "circle", {cx: x, cy: y, r: escalaMarcadores * (marcador === "cor" ? 3.2 : Math.sqrt(8 + 38 * fracao)),
            fill: marcador === "tamanho" ? "#71e8cc" : p.cor, stroke: "#ffffff", "stroke-width": .8,
            "vector-effect": "non-scaling-stroke"});
        const nome = grupo.length === 1 ? p.id : `${grupo.length} fontes coincidentes`;
        add(el, "title", {}).textContent = `${nome} · ${number.format(p.valor)} ${unidade}`;
        clicavel(el, nome, () => seleciona(p, false));
        el.addEventListener("focus", () => seleciona(p, false));
        marcadores.set(chave, el);
    }
    svg.addEventListener("wheel", e => { e.preventDefault(); zoom(e.deltaY > 0 ? 1.16 : .86); }, {passive: false});
    let toque;
    svg.addEventListener("pointerdown", e => { toque = [e.clientX, e.clientY]; });
    svg.addEventListener("pointermove", e => {
        if (!toque) return;
        const dx = e.clientX - toque[0], dy = e.clientY - toque[1];
        if (Math.abs(dx) + Math.abs(dy) < 4) return;
        cancelAnimationFrame(frame);
        svg.setPointerCapture(e.pointerId);
        const fator = svg.getScreenCTM().a;
        box[0] -= dx / fator;
        box[1] -= dy / fator;
        toque = [e.clientX, e.clientY];
        atualizar();
    });
    for (const e of ["pointerup", "pointercancel"]) svg.addEventListener(e, () => { toque = null; });
    return {svg, zoom, enquadrar: () => enquadrar(alvo), caixa: () => [...box], destacar: p => seleciona(p, true)};
}
