function imageExportControls(prefix, enlarge, download) {
    const container = get(prefix + "Files");
    const format = document.createElement("select");
    format.id = prefix + "Format";
    format.append(...["PNG", "PDF", "SVG"].map(value => new Option(value, value.toLowerCase())));
    const dpi = document.createElement("select");
    dpi.id = prefix + "Dpi";
    dpi.append(...["300", "600"].map(value => new Option(value + " DPI", value)));
    const formatLabel = document.createElement("label");
    formatLabel.append("Formato ", format);
    const dpiLabel = document.createElement("label");
    dpiLabel.append("Resolução ", dpi);
    const zoom = document.createElement("button");
    zoom.id = prefix + "Enlarge";
    zoom.type = "button";
    zoom.className = "button secondary";
    zoom.textContent = "Ampliar imagem";
    zoom.onclick = enlarge;
    const save = document.createElement("button");
    save.id = prefix + "Download";
    save.type = "button";
    save.className = "button secondary";
    save.textContent = "↓ Baixar imagem";
    const note = document.createElement("p");
    note.className = "field-note";
    note.hidden = true;
    container.append(note, formatLabel, dpiLabel, zoom, save);
    format.addEventListener("change", () => { dpiLabel.hidden = format.value !== "png"; });
    save.addEventListener("click", () => download(format.value, dpi.value));
    return {container, dpi, note, save, zoom};
}

function requestImageDownload(url) {
    const link = document.createElement("a");
    link.href = url;
    link.download = "";
    link.click();
}

function temporalPdf(jpeg, pixelWidth, pixelHeight) {
    const width = 8 * 72;
    const height = width * pixelHeight / pixelWidth;
    const content = `q ${width} 0 0 ${height} 0 0 cm /Image Do Q\n`;
    const objects = [
        ["<< /Type /Catalog /Pages 2 0 R >>"],
        ["<< /Type /Pages /Kids [3 0 R] /Count 1 >>"],
        [`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${width} ${height}] /Resources << /XObject << /Image 4 0 R >> >> /Contents 5 0 R >>`],
        [`<< /Type /XObject /Subtype /Image /Width ${pixelWidth} /Height ${pixelHeight} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpeg.size} >>\nstream\n`, jpeg, "\nendstream"],
        [`<< /Length ${content.length} >>\nstream\n${content}endstream`]
    ];
    const parts = ["%PDF-1.4\n"];
    const offsets = [];
    let position = parts[0].length;
    objects.forEach((object, index) => {
        offsets.push(position);
        const blocks = [`${index + 1} 0 obj\n`, ...object, "\nendobj\n"];
        parts.push(...blocks);
        position += blocks.reduce((size, block) => size + (typeof block === "string" ? block.length : block.size), 0);
    });
    parts.push("xref\n0 6\n0000000000 65535 f \n",
        ...offsets.map(offset => `${String(offset).padStart(10, "0")} 00000 n \n`),
        `trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${position}\n%%EOF\n`);
    return new Blob(parts, {type: "application/pdf"});
}

async function embedPngDpi(blob, dpi) {
    const bytes = new Uint8Array(await blob.arrayBuffer());
    const source = new DataView(bytes.buffer);
    const chunk = new Uint8Array(21);
    const info = new DataView(chunk.buffer);
    info.setUint32(0, 9);
    chunk.set([112, 72, 89, 115], 4); // pHYs
    const pixelsPerMeter = Math.round(dpi / .0254);
    info.setUint32(8, pixelsPerMeter);
    info.setUint32(12, pixelsPerMeter);
    chunk[16] = 1;
    let crc = 0xffffffff;
    for (const byte of chunk.subarray(4, 17)) {
        crc ^= byte;
        for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
    }
    info.setUint32(17, crc ^ 0xffffffff);
    const parts = [bytes.subarray(0, 33), chunk]; // PNG signature and IHDR
    for (let offset = 33; offset < bytes.length;) {
        const end = offset + source.getUint32(offset) + 12;
        if (source.getUint32(offset + 4) !== 0x70485973) parts.push(bytes.subarray(offset, end));
        offset = end;
    }
    return new Blob(parts, {type: "image/png"});
}

document.querySelectorAll(".image-lightbox").forEach(dialog => {
    dialog.addEventListener("click", event => { if (event.target === dialog) dialog.close(); });
});
