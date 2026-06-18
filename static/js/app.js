function copyCommand(text) {
    navigator.clipboard.writeText(text);

    alert("Copied: " + text);
}
function showInfo(text) {
    const box = document.getElementById("infoBox");

    if (box) {
        box.innerText = text;
        box.classList.add("active");
    }
}