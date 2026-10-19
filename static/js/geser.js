// Drag-to-scroll with the mouse for tab strips that overflow sideways (every
// nav.overflow-x-auto, or anything marked data-geser). Touch screens scroll
// them natively; a mouse can only drag. A drag of more than a few pixels
// doesn't count as a click on the tab under the pointer.
(function () {
    let el = null, startX = 0, startScroll = 0, digeser = false;

    document.addEventListener("mousedown", function (e) {
        if (e.button !== 0) return;
        const strip = e.target.closest("nav.overflow-x-auto, [data-geser]");
        if (!strip || strip.scrollWidth <= strip.clientWidth) return;
        el = strip; startX = e.clientX; startScroll = strip.scrollLeft; digeser = false;
        e.preventDefault(); // no native dragging of the tab links
    });

    document.addEventListener("mousemove", function (e) {
        if (!el) return;
        const dx = e.clientX - startX;
        if (!digeser && Math.abs(dx) > 5) {
            digeser = true;
            el.style.cursor = "grabbing";
        }
        if (digeser) el.scrollLeft = startScroll - dx;
    });

    document.addEventListener("mouseup", function () {
        if (!el) return;
        el.style.cursor = "";
        el = null;
        if (digeser) {
            // Swallow the click that ends the drag.
            const tahan = function (e) { e.preventDefault(); e.stopPropagation(); };
            document.addEventListener("click", tahan, { capture: true, once: true });
            setTimeout(function () { document.removeEventListener("click", tahan, { capture: true }); }, 0);
        }
    });
})();
