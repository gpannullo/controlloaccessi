"use strict";

document.addEventListener("DOMContentLoaded", () => {
    const video = document.getElementById("camera-preview");
    const canvas = document.getElementById("document-canvas");

    const startButton = document.getElementById("start-camera");
    const captureButton = document.getElementById("capture-document");
    const stopButton = document.getElementById("stop-camera");

    const statusBox = document.getElementById("ocr-status");
    const errorBox = document.getElementById("camera-error");

    const nomeInput = document.getElementById("id_nome");
    const cognomeInput = document.getElementById("id_cognome");
    const tipoInput = document.getElementById("id_documento_tipo");
    const numeroInput = document.getElementById("id_documento_numero");
    const scadenzaInput = document.getElementById("id_documento_scadenza");

    let mediaStream = null;

    function showError(message) {
        errorBox.textContent = message;
        errorBox.classList.remove("d-none");
    }

    function hideError() {
        errorBox.textContent = "";
        errorBox.classList.add("d-none");
    }

    function showStatus(message) {
        statusBox.textContent = message;
        statusBox.classList.remove("d-none");
    }

    function hideStatus() {
        statusBox.textContent = "";
        statusBox.classList.add("d-none");
    }

    async function startCamera() {
        hideError();

        if (
            !navigator.mediaDevices ||
            !navigator.mediaDevices.getUserMedia
        ) {
            showError(
                "Il browser non supporta l'accesso alla webcam."
            );
            return;
        }

        try {
            mediaStream = await navigator.mediaDevices.getUserMedia({
                video: {
                    width: { ideal: 1920 },
                    height: { ideal: 1080 },
                    facingMode: { ideal: "environment" }
                },
                audio: false
            });

            video.srcObject = mediaStream;

            captureButton.disabled = false;
            stopButton.disabled = false;
            startButton.disabled = true;

        } catch (error) {
            console.error(error);

            showError(
                "Impossibile accedere alla webcam. " +
                "Verificare i permessi del browser e la connessione HTTPS."
            );
        }
    }

    function stopCamera() {
        if (mediaStream) {
            mediaStream.getTracks().forEach((track) => track.stop());
            mediaStream = null;
        }

        video.srcObject = null;

        captureButton.disabled = true;
        stopButton.disabled = true;
        startButton.disabled = false;
    }

    function captureImage() {
        const width = video.videoWidth;
        const height = video.videoHeight;

        if (!width || !height) {
            throw new Error("La webcam non è ancora pronta.");
        }

        canvas.width = width;
        canvas.height = height;

        const context = canvas.getContext("2d");

        context.drawImage(
            video,
            0,
            0,
            width,
            height
        );

        canvas.classList.remove("d-none");

        return canvas;
    }

    function normalizeText(text) {
        return text
            .replace(/\r/g, "")
            .replace(/[|]/g, "I")
            .replace(/[ \t]+/g, " ")
            .trim();
    }

    function lineAfterLabel(lines, labels) {
        for (let index = 0; index < lines.length; index += 1) {
            const line = lines[index].toUpperCase();

            for (const label of labels) {
                if (line.includes(label)) {
                    const inlineValue = line
                        .replace(label, "")
                        .replace(/^[:\-\s]+/, "")
                        .trim();

                    if (inlineValue) {
                        return inlineValue;
                    }

                    if (lines[index + 1]) {
                        return lines[index + 1].trim();
                    }
                }
            }
        }

        return "";
    }

    function normalizeName(value) {
        return value
            .replace(/[^A-ZÀ-ÖØ-Ý' -]/gi, "")
            .replace(/\s+/g, " ")
            .trim();
    }

    function findDocumentNumber(text) {
        const patterns = [
            /(?:NUMERO\s+(?:DEL\s+)?DOCUMENTO|DOCUMENT\s+NO)[\s:.-]*([A-Z]{1,3}[0-9A-Z]{5,10})/i,
            /\b([A-Z]{2}[0-9]{5}[A-Z0-9]{2})\b/i
        ];

        for (const pattern of patterns) {
            const match = text.match(pattern);

            if (match) {
                return match[1].toUpperCase();
            }
        }

        return "";
    }

    function findExpiryDate(text) {
        const labelledPattern =
            /(?:SCADENZA|DATE\s+OF\s+EXPIRY|EXPIRY)[^\d]*(\d{2}[\/.\-]\d{2}[\/.\-]\d{4})/i;

        let match = text.match(labelledPattern);

        if (!match) {
            const allDates = text.match(
                /\b\d{2}[\/.\-]\d{2}[\/.\-]\d{4}\b/g
            );

            if (allDates && allDates.length) {
                match = [allDates[allDates.length - 1], allDates[allDates.length - 1]];
            }
        }

        if (!match) {
            return "";
        }

        const parts = match[1].split(/[\/.\-]/);

        return `${parts[2]}-${parts[1]}-${parts[0]}`;
    }

    function fillFormFromOCR(rawText) {
        const text = normalizeText(rawText);

        const lines = text
            .split("\n")
            .map((line) => line.trim())
            .filter(Boolean);

        const cognome = normalizeName(
            lineAfterLabel(
                lines,
                ["COGNOME", "SURNAME"]
            )
        );

        const nome = normalizeName(
            lineAfterLabel(
                lines,
                ["NOME", "GIVEN NAMES", "NAME"]
            )
        );

        const numero = findDocumentNumber(text);
        const scadenza = findExpiryDate(text);

        if (nome) {
            nomeInput.value = nome;
        }

        if (cognome) {
            cognomeInput.value = cognome;
        }

        if (numero) {
            numeroInput.value = numero;
        }

        if (scadenza) {
            scadenzaInput.value = scadenza;
        }

        tipoInput.value = "CIE";

        return {
            nome,
            cognome,
            numero,
            scadenza
        };
    }

    async function recognizeDocument() {
        hideError();

        try {
            captureImage();

            captureButton.disabled = true;
            showStatus("Lettura del documento in corso…");

            const result = await Tesseract.recognize(
                canvas,
                "ita+eng",
                {
                    logger: (message) => {
                        if (
                            message.status === "recognizing text" &&
                            Number.isFinite(message.progress)
                        ) {
                            const percent = Math.round(
                                message.progress * 100
                            );

                            showStatus(
                                `Lettura del documento: ${percent}%`
                            );
                        }
                    }
                }
            );

            const extracted = fillFormFromOCR(
                result.data.text
            );

            if (
                !extracted.nome &&
                !extracted.cognome &&
                !extracted.numero
            ) {
                showError(
                    "Non è stato possibile riconoscere correttamente " +
                    "il documento. Migliorare l'illuminazione e riprovare."
                );
            } else {
                showStatus(
                    "Lettura completata. Verificare i dati compilati."
                );
            }

        } catch (error) {
            console.error(error);

            showError(
                "Si è verificato un errore durante la lettura " +
                "del documento."
            );

            hideStatus();

        } finally {
            captureButton.disabled = false;
        }
    }

    startButton.addEventListener("click", startCamera);
    stopButton.addEventListener("click", stopCamera);
    captureButton.addEventListener("click", recognizeDocument);

    window.addEventListener("beforeunload", stopCamera);
});