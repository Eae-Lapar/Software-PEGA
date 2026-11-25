const pegaLocale = (() => {
    const catalog = new Map(englishUI.filter(parts => parts.length === 2));
    catalog.set("PEGA | Inventários de Emissões", "PEGA | Emission Inventories");
    const folded = new Map([...catalog].map(([key, value]) => [key.toLocaleLowerCase("pt-BR"), value]));
    const patterns = englishPatterns.map(([source, target]) => {
        const expression = source.split("{}").map(part => part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("(.+?)");
        return [new RegExp("^" + expression + "$", "s"), target];
    });
    const original = new WeakMap();
    const attributes = ["aria-label", "title", "placeholder", "alt"];
    const select = document.getElementById("uiLanguage");
    let language = "pt-BR";
    try { if (localStorage.getItem("pega.language") === "en-US") language = "en-US"; } catch {}
    const formatterCache = new Map();
    const numbers = new Map();

    function format(value, options) {
        const key = language + JSON.stringify(options);
        if (!formatterCache.has(key)) formatterCache.set(key, new Intl.NumberFormat(language, options));
        return formatterCache.get(key).format(value);
    }

    function lookup(normalized) {
        let translation = catalog.get(normalized) || folded.get(normalized.toLocaleLowerCase("pt-BR"));
        if (!translation) {
            for (const [pattern, target] of patterns) {
                const match = normalized.match(pattern);
                if (match) {
                    translation = target.replace(/\{(\d+)\}/g, (_, i) =>
                        Number(i) < match.length ? (catalog.get(match[i]) || folded.get(match[i].toLocaleLowerCase("pt-BR")) || match[i]) : "");
                    break;
                }
            }
        }
        return translation;
    }

    function translate(text) {
        if (language === "pt-BR") return text;
        const normalized = text.trim().replace(/\s+/g, " ");
        if (text.trim().includes("\n") && !catalog.has(normalized)) return text.split("\n").map(translate).join("\n");
        const translation = lookup(normalized) || (normalized.includes(" · ")
            ? normalized.split(" · ").map(part => lookup(part) || part).join(" · ") : null);
        return translation ? text.replace(/\S[\s\S]*\S|\S/, translation) : text;
    }

    function update(node, key, value, apply) {
        const state = original.get(node) || {};
        const previous = state[key];
        const source = previous?.rendered === value ? previous.source : value;
        const numeric = node.nodeType === Node.TEXT_NODE &&
            node.parentElement?.closest(".numeric-cell,.metric-grid dd,#totalRows");
        const match = numeric && source.match(/^([^ ]+)( GJ)?$/);
        const stored = match && numbers.get(match[1]);
        const rendered = stored ? format(stored.value, stored.options) + (match[2] || "") : translate(source);
        state[key] = {source, rendered};
        original.set(node, state);
        if (rendered !== value) apply(rendered);
    }

    function visit(node) {
        if (node.nodeType === Node.TEXT_NODE) {
            if (node.data.trim() && !node.parentElement?.closest("script,style,code,#temporalPreview,#temporalDialog") &&
                (!node.parentElement?.closest("tbody") || node.parentElement?.closest(".numeric-cell"))) {
                update(node, "text", node.data, value => { node.data = value; });
            }
            return;
        }
        if (node.nodeType !== Node.ELEMENT_NODE || node.matches("script,style,#uiLanguage option")) return;
        for (const attribute of attributes) {
            if (node.hasAttribute(attribute)) update(node, attribute, node.getAttribute(attribute),
                value => node.setAttribute(attribute, value));
        }
        for (const child of node.childNodes) visit(child);
    }

    const observer = new MutationObserver(records => {
        for (const record of records) {
            if (record.type === "childList") record.addedNodes.forEach(visit);
            else if (record.type === "attributes") {
                const node = record.target;
                const attr = record.attributeName;
                if (node.hasAttribute(attr)) update(node, attr, node.getAttribute(attr), value => node.setAttribute(attr, value));
            } else visit(record.target);
        }
    });
    const defaults = ["figureLocale", "spatialLanguage", "exportLanguage"];
    const manual = new Set();
    const dates = document.querySelectorAll('input[type="date"]');
    function dateLabel(input) {
        if (!input.value) return input.removeAttribute("title");
        input.title = new Intl.DateTimeFormat(language, {dateStyle: "short", timeZone: "UTC"})
            .format(new Date(input.value + "T00:00:00Z"));
    }
    dates.forEach(input => input.addEventListener("change", () => dateLabel(input)));
    for (const id of defaults) document.getElementById(id).addEventListener("change", () => manual.add(id));
    function apply() {
        observer.disconnect();
        document.documentElement.lang = select.value = language;
        select.closest("label").dataset.language = language;
        for (const id of defaults) {
            const input = document.getElementById(id);
            const currentFigure = id === "figureLocale" ? document.getElementById("figureImage").hasAttribute("src") :
                id === "spatialLanguage" && document.querySelector("#spatialMap > *");
            if (!manual.has(id) && !currentFigure) input.value = language === "en-US" ? "en" : "pt";
        }
        visit(document.documentElement);
        dates.forEach(dateLabel);
        observer.observe(document.documentElement, {subtree: true, childList: true, characterData: true,
            attributes: true, attributeFilter: attributes});
    }
    select.onchange = () => {
        language = select.value;
        try { localStorage.setItem("pega.language", language); } catch {}
        apply();
    };
    apply();
    return {translate, defaultFigureLanguage(id) {
        if (!manual.has(id)) document.getElementById(id).value = language === "en-US" ? "en" : "pt";
    }, numeric: value => numbers.get(value)?.value, number(options) {
        return {format(value) {
            const result = format(value, options);
            if (numbers.size < 20000) numbers.set(result, {value, options});
            return result;
        }};
    }};
})();
