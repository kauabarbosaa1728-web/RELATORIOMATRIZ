"use strict";

/* ==========================================
   ALMOXARIFADO MATRIZ
   Dashboard, movimentações e importação do SGP
   ========================================== */

const $ = (selector) => document.querySelector(selector);

const currencyFormatter = new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL"
});

const quantityFormatter = new Intl.NumberFormat("pt-BR", {
    maximumFractionDigits: 3
});

const money = (value) => currencyFormatter.format(value);
const quantityText = (value) => quantityFormatter.format(value);

const state = {
    saving: false,
    requestNumber: 0,
    returnRequestNumber: 0,
    returnsLoading: false,
    withdrawals: new Map()
};


/* ELEMENTOS DA DASHBOARD */

const elements = {
    start: $("#start"),
    end: $("#end"),
    message: $("#message"),
    sync: $("#sync"),
    dialog: $("#movement-dialog"),
    form: $("#movement-form"),
    kind: $("#kind"),
    item: $("#item-select"),
    technician: $("#technician-select"),
    original: $("#original"),
    quantity: $("#quantity"),
    date: $("#movement-date"),
    save: $("#save"),
    error: $("#form-error"),
    withdrawFields: $("#withdraw-fields"),
    returnFields: $("#return-fields"),
    unitHint: $("#unit-hint")
};


/* DATAS */

function saoPauloToday() {
    const parts = new Intl.DateTimeFormat("en-US", {
        timeZone: "America/Sao_Paulo",
        year: "numeric",
        month: "2-digit",
        day: "2-digit"
    }).formatToParts(new Date());

    const values = {};

    for (const part of parts) {
        values[part.type] = part.value;
    }

    return `${values.year}-${values.month}-${values.day}`;
}

function dateString(date) {
    const year = date.getFullYear();

    const month = String(
        date.getMonth() + 1
    ).padStart(2, "0");

    const day = String(
        date.getDate()
    ).padStart(2, "0");

    return `${year}-${month}-${day}`;
}

function displayDate(value) {
    return value.split("-").reverse().join("/");
}

function periodQuery() {
    return new URLSearchParams({
        start: elements.start.value,
        end: elements.end.value
    }).toString();
}

function validPeriod() {
    if (!elements.start.value || !elements.end.value) {
        elements.message.textContent =
            "Selecione a data inicial e a data final.";

        return false;
    }

    if (elements.end.value < elements.start.value) {
        elements.message.textContent =
            "A data final deve ser igual ou posterior à inicial.";

        return false;
    }

    const start = new Date(
        `${elements.start.value}T00:00:00Z`
    );

    const end = new Date(
        `${elements.end.value}T00:00:00Z`
    );

    if ((end - start) / 86400000 > 366) {
        elements.message.textContent =
            "Selecione um período de até 367 dias.";

        return false;
    }

    return true;
}

function selectPeriod(mode) {
    const current = new Date(
        `${saoPauloToday()}T12:00:00`
    );

    elements.end.value = dateString(current);

    if (mode === "week") {
        const daysSinceMonday = (
            current.getDay() + 6
        ) % 7;

        current.setDate(
            current.getDate() - daysSinceMonday
        );
    } else {
        current.setDate(1);
    }

    elements.start.value = dateString(current);

    document.querySelectorAll(
        "[data-period]"
    ).forEach((button) => {
        const selected = button.dataset.period === mode;

        button.classList.toggle(
            "selected",
            selected
        );

        button.setAttribute(
            "aria-pressed",
            String(selected)
        );
    });

    refreshDashboard();
}


/* CRIAÇÃO SEGURA DOS ELEMENTOS */

function createNode(tag, text, className) {
    const element = document.createElement(tag);

    if (text !== undefined) {
        element.textContent = text;
    }

    if (className) {
        element.className = className;
    }

    return element;
}


/* REQUISIÇÕES */

async function api(url, options = {}) {
    const controller = new AbortController();

    const timeout = window.setTimeout(() => {
        controller.abort();
    }, 20000);

    try {
        const response = await fetch(url, {
            ...options,
            credentials: "same-origin",
            signal: controller.signal
        });

        if (response.status === 401) {
            window.location.assign("/login");

            throw new Error(
                "Sua sessão terminou. Entre novamente."
            );
        }

        if (!response.ok) {
            let message = "";

            try {
                const contentType = response.headers.get(
                    "Content-Type"
                ) || "";

                if (contentType.includes("application/json")) {
                    const data = await response.json();

                    message = data.error || "";
                }
            } catch {
                message = "";
            }

            if (!message && response.status === 400) {
                message =
                    "Confira os dados. Se o problema continuar, atualize a página.";
            }

            throw new Error(
                message ||
                "Não foi possível concluir a operação. Tente novamente."
            );
        }

        return await response.json();

    } catch (error) {
        if (error.name === "AbortError") {
            throw new Error(
                "O servidor demorou para responder. Confira a conexão e tente novamente."
            );
        }

        throw error;

    } finally {
        window.clearTimeout(timeout);
    }
}


/* GRÁFICOS DE BARRAS */

function renderBars(selector, data) {
    const container = $(selector);

    container.replaceChildren();

    const entries = Object.entries(data);

    if (!entries.length) {
        container.append(
            createNode(
                "div",
                "Nenhuma movimentação neste período.",
                "empty"
            )
        );

        return;
    }

    const maximum = Math.max(
        ...entries.map(([, value]) => Math.abs(value)),
        1
    );

    for (const [name, value] of entries) {
        const row = createNode("div");

        const label = createNode(
            "div",
            undefined,
            "bar-label"
        );

        const valueLabel = createNode(
            "b",
            money(value)
        );

        if (value < 0) {
            valueLabel.classList.add("negative");
        }

        label.append(
            createNode("span", name),
            valueLabel
        );

        const track = createNode(
            "div",
            undefined,
            "track"
        );

        track.setAttribute("aria-hidden", "true");

        const fill = createNode("div");

        fill.style.width = (
            Math.abs(value) / maximum * 100
        ) + "%";

        if (value < 0) {
            fill.style.background = "var(--coral)";
        }

        track.append(fill);

        row.append(
            label,
            track
        );

        container.append(row);
    }
}


/* GRÁFICO DE EVOLUÇÃO */

function renderTimeline(data) {
    const container = $("#timeline");

    container.replaceChildren();

    const entries = Object.entries(data).sort(
        ([first], [second]) => first.localeCompare(second)
    );

    if (!entries.length) {
        container.append(
            createNode(
                "div",
                "Seu histórico começa no primeiro lançamento.\n" +
                "Registre uma retirada para acompanhar a evolução.",
                "empty"
            )
        );

        return;
    }

    const namespace = "http://www.w3.org/2000/svg";

    const svg = document.createElementNS(
        namespace,
        "svg"
    );

    svg.setAttribute("viewBox", "0 0 700 230");
    svg.setAttribute("role", "img");

    svg.setAttribute(
        "aria-label",
        "Evolução dos custos líquidos diários em reais"
    );

    const values = entries.map(
        ([, value]) => value
    );

    const minimum = Math.min(0, ...values);
    const maximum = Math.max(1, ...values);

    const left = 92;
    const right = 675;
    const top = 25;
    const bottom = 185;

    function yPosition(value) {
        const proportion = (
            value - minimum
        ) / (
            maximum - minimum
        );

        return bottom - proportion * (bottom - top);
    }

    function svgElement(tag, attributes, text) {
        const element = document.createElementNS(
            namespace,
            tag
        );

        for (const [name, value] of Object.entries(attributes)) {
            element.setAttribute(
                name,
                String(value)
            );
        }

        if (text !== undefined) {
            element.textContent = text;
        }

        svg.append(element);

        return element;
    }

    for (let index = 0; index < 4; index += 1) {
        const value = minimum + (
            maximum - minimum
        ) * index / 3;

        const y = yPosition(value);

        svgElement("line", {
            x1: left,
            x2: right,
            y1: y,
            y2: y,
            stroke: "#2d4138",
            "stroke-dasharray": "4 5"
        });

        svgElement("text", {
            x: left - 12,
            y: y + 4,
            fill: "#94aaa6",
            "font-size": 10,
            "text-anchor": "end"
        }, money(value));
    }

    const firstTime = Date.parse(
        `${entries[0][0]}T00:00:00Z`
    );

    const lastTime = Date.parse(
        `${entries[entries.length - 1][0]}T00:00:00Z`
    );

    const timeRange = lastTime - firstTime;

    const points = entries.map(([day, value]) => {
        const time = Date.parse(
            `${day}T00:00:00Z`
        );

        const x = timeRange === 0
            ? (left + right) / 2
            : left + (
                (time - firstTime) / timeRange
            ) * (right - left);

        return {
            x,
            y: yPosition(value),
            day,
            value
        };
    });

    svgElement("polyline", {
        points: points.map(
            (point) => `${point.x},${point.y}`
        ).join(" "),
        fill: "none",
        stroke: "#40dfae",
        "stroke-width": 3,
        "stroke-linejoin": "round",
        "stroke-linecap": "round"
    });

    const labelInterval = Math.max(
        1,
        Math.ceil(points.length / 5)
    );

    points.forEach((point, index) => {
        const circle = svgElement("circle", {
            cx: point.x,
            cy: point.y,
            r: 4,
            fill: point.value < 0
                ? "#f48f7e"
                : "#40dfae"
        });

        const title = document.createElementNS(
            namespace,
            "title"
        );

        title.textContent =
            `${displayDate(point.day)}: ${money(point.value)}`;

        circle.append(title);

        const showLabel = (
            index === 0 ||
            index === points.length - 1 ||
            index % labelInterval === 0
        );

        if (showLabel) {
            svgElement("text", {
                x: point.x,
                y: 218,
                fill: "#94aaa6",
                "font-size": 10,
                "text-anchor": "middle"
            }, point.day.slice(5).split("-").reverse().join("/"));
        }
    });

    container.append(svg);
}


/* GRÁFICO DE COMPOSIÇÃO */

function renderComposition(data) {
    $("#donut-value").textContent = money(data.total);

    const valid = (
        data.materials >= 0 &&
        data.equipment >= 0 &&
        data.total > 0
    );

    if (!valid) {
        $("#donut").style.background = "#293832";

        $("#mat-share").textContent = "—";
        $("#eq-share").textContent = "—";

        $("#donut").title =
            "Percentuais disponíveis quando o total é positivo " +
            "e as categorias não têm saldo negativo.";

        return;
    }

    const materialShare = (
        data.materials / data.total
    ) * 100;

    const equipmentShare = 100 - materialShare;

    $("#donut").style.background =
        `conic-gradient(
            #40dfae 0% ${materialShare}%,
            #e6c181 ${materialShare}% 100%
        )`;

    $("#mat-share").textContent =
        materialShare.toFixed(1).replace(".", ",") + "%";

    $("#eq-share").textContent =
        equipmentShare.toFixed(1).replace(".", ",") + "%";

    $("#donut").title =
        `Materiais: ${money(data.materials)}. ` +
        `Equipamentos: ${money(data.equipment)}.`;
}


/* COMPARAÇÃO ENTRE PERÍODOS */

function renderComparison(data) {
    const difference = $("#difference");
    const comparison = $("#comparison");

    difference.classList.toggle(
        "negative",
        data.has_previous && data.difference < 0
    );

    if (!data.has_previous) {
        difference.textContent = "—";

        comparison.textContent =
            "Sem registros no período anterior";

        comparison.title =
            `${displayDate(data.previous_start)} a ` +
            `${displayDate(data.previous_end)}`;

        return;
    }

    difference.textContent = money(data.difference);

    if (data.percent === null) {
        comparison.textContent =
            "Base anterior sem valor positivo";

    } else {
        const percent = Math.abs(
            data.percent
        ).toFixed(1).replace(".", ",");

        if (data.difference > 0) {
            comparison.textContent =
                `${percent}% a menos · período anterior`;

        } else if (data.difference < 0) {
            comparison.textContent =
                `${percent}% a mais · período anterior`;

        } else {
            comparison.textContent =
                "Sem alteração · período anterior";
        }
    }

    comparison.title =
        `Base: ${displayDate(data.previous_start)} a ` +
        `${displayDate(data.previous_end)} · ` +
        money(data.previous);
}


/* HISTÓRICO */

function renderMovements(movements) {
    const body = $("#rows");

    body.replaceChildren();

    if (!movements.length) {
        const row = createNode("tr");

        const cell = createNode(
            "td",
            "Nenhum registro neste período. " +
            "Clique em Nova movimentação para começar."
        );

        cell.colSpan = 6;

        row.append(cell);
        body.append(row);

        return;
    }

    for (const movement of movements) {
        const row = createNode("tr");

        if (movement.note) {
            row.title = movement.note;
        }

        row.append(
            createNode(
                "td",
                displayDate(movement.date)
            ),
            createNode(
                "td",
                movement.technician
            ),
            createNode(
                "td",
                movement.item
            )
        );

        const kindCell = createNode("td");

        const isReturn = (
            movement.kind === "devolucao"
        );

        kindCell.append(
            createNode(
                "span",
                isReturn ? "Devolução" : "Retirada",
                "badge" + (isReturn ? " return" : "")
            )
        );

        const valueCell = createNode(
            "td",
            money(movement.total)
        );

        if (movement.total < 0) {
            valueCell.classList.add("negative");
        }

        row.append(
            kindCell,
            createNode(
                "td",
                `${quantityText(movement.quantity)} ${movement.unit}`
            ),
            valueCell
        );

        body.append(row);
    }
}


/* ATUALIZAR A DASHBOARD */

async function refreshDashboard() {
    const requestNumber = ++state.requestNumber;

    if (!validPeriod()) {
        return;
    }

    try {
        const data = await api(
            "/api/dashboard?" + periodQuery()
        );

        if (requestNumber !== state.requestNumber) {
            return;
        }

        elements.message.textContent = "";

        for (const key of [
            "total",
            "materials",
            "equipment",
            "returns"
        ]) {
            $("#" + key).textContent = money(data[key]);
        }

        renderComparison(data);
        renderComposition(data);

        const technicians = Object.fromEntries(
            Object.entries(
                data.technicians
            ).sort(
                ([, first], [, second]) => second - first
            )
        );

        renderBars(
            "#technician-bars",
            technicians
        );

        renderBars(
            "#item-bars",
            data.items
        );

        renderTimeline(data.daily);

        $("#count").textContent =
            data.count === 1
                ? "1 movimentação"
                : `${data.count} movimentações`;

        renderMovements(data.movements);

        $("#csv").href =
            "/report.csv?" + periodQuery();

        $("#pdf").href =
            "/report.pdf?" + periodQuery();

        const time = new Date().toLocaleTimeString(
            "pt-BR",
            {
                hour: "2-digit",
                minute: "2-digit"
            }
        );

        elements.sync.textContent =
            "Atualizado " + time;

        elements.sync.title =
            "Consulta automática a cada 15 segundos " +
            "enquanto esta página estiver visível.";

    } catch (error) {
        if (requestNumber !== state.requestNumber) {
            return;
        }

        elements.message.textContent = error.message;

        elements.sync.textContent =
            "Sem sincronização";
    }
}


/* FORMULÁRIO MANUAL */

function updateSaveButton() {
    const isReturn = (
        elements.kind.value === "devolucao"
    );

    elements.save.disabled = (
        state.saving ||
        (
            isReturn &&
            (
                state.returnsLoading ||
                !elements.original.value
            )
        )
    );

    elements.save.textContent = state.saving
        ? "Salvando…"
        : "Salvar movimentação →";
}

function updateUnitHint() {
    const isReturn = (
        elements.kind.value === "devolucao"
    );

    elements.quantity.setCustomValidity("");

    if (isReturn) {
        const withdrawal = state.withdrawals.get(
            elements.original.value
        );

        if (!withdrawal) {
            elements.unitHint.textContent =
                "Selecione uma retirada com saldo.";

            elements.quantity.step = "0.001";
            elements.quantity.min = "0.001";
            elements.quantity.max = "1000000";

            elements.date.removeAttribute("min");

            return;
        }

        const isMeter = withdrawal.unit === "m";

        elements.quantity.step = isMeter ? "0.001" : "1";
        elements.quantity.min = isMeter ? "0.001" : "1";
        elements.quantity.max = String(withdrawal.remaining);

        elements.date.min = withdrawal.day;

        elements.unitHint.textContent =
            `(${withdrawal.unit}) · Saldo disponível: ` +
            `${quantityText(withdrawal.remaining)} ${withdrawal.unit}`;

        return;
    }

    const option = elements.item.selectedOptions[0];

    if (!option) {
        elements.unitHint.textContent = "";
        return;
    }

    const unit = option.dataset.unit;
    const isMeter = unit === "m";

    elements.quantity.step = isMeter ? "0.001" : "1";
    elements.quantity.min = isMeter ? "0.001" : "1";
    elements.quantity.max = "1000000";

    elements.date.removeAttribute("min");

    const cost = Number(option.dataset.cost);

    const detailedCost = new Intl.NumberFormat(
        "pt-BR",
        {
            style: "currency",
            currency: "BRL",
            minimumFractionDigits: 2,
            maximumFractionDigits: 6
        }
    ).format(cost);

    elements.unitHint.textContent =
        `(${unit}) · ${detailedCost} por ${unit}`;
}

async function changeKind() {
    const requestNumber = ++state.returnRequestNumber;

    const isReturn = (
        elements.kind.value === "devolucao"
    );

    elements.withdrawFields.hidden = isReturn;
    elements.returnFields.hidden = !isReturn;

    elements.technician.disabled = isReturn;
    elements.item.disabled = isReturn;
    elements.original.disabled = !isReturn;
    elements.original.required = isReturn;

    elements.error.textContent = "";

    state.returnsLoading = false;

    if (!isReturn) {
        updateUnitHint();
        updateSaveButton();

        return;
    }

    state.returnsLoading = true;

    state.withdrawals.clear();

    elements.original.replaceChildren();

    const placeholder = createNode(
        "option",
        "Carregando retiradas…"
    );

    placeholder.value = "";

    elements.original.append(placeholder);
    elements.original.disabled = true;

    updateUnitHint();
    updateSaveButton();

    try {
        const withdrawals = await api(
            "/api/withdrawals"
        );

        if (
            requestNumber !== state.returnRequestNumber ||
            elements.kind.value !== "devolucao"
        ) {
            return;
        }

        elements.original.replaceChildren();

        const firstOption = createNode(
            "option",
            withdrawals.length
                ? "Selecione a retirada original"
                : "Nenhuma retirada com saldo"
        );

        firstOption.value = "";

        elements.original.append(firstOption);

        for (const withdrawal of withdrawals) {
            state.withdrawals.set(
                String(withdrawal.id),
                withdrawal
            );

            const option = createNode(
                "option",
                `${displayDate(withdrawal.day)} · ` +
                `${withdrawal.technician} · ` +
                `${withdrawal.item} · ` +
                `saldo ${quantityText(withdrawal.remaining)} ` +
                withdrawal.unit
            );

            option.value = String(withdrawal.id);

            elements.original.append(option);
        }

        elements.original.disabled = (
            withdrawals.length === 0
        );

        if (!withdrawals.length) {
            elements.error.textContent =
                "Não há retiradas com saldo para devolver.";
        }

    } catch (error) {
        if (requestNumber !== state.returnRequestNumber) {
            return;
        }

        elements.original.replaceChildren();

        const option = createNode(
            "option",
            "Não foi possível carregar"
        );

        option.value = "";

        elements.original.append(option);

        elements.error.textContent = error.message;

    } finally {
        if (requestNumber === state.returnRequestNumber) {
            state.returnsLoading = false;

            updateUnitHint();
            updateSaveButton();
        }
    }
}

function openMovement() {
    if (state.saving) {
        return;
    }

    elements.form.reset();

    elements.quantity.setCustomValidity("");

    const today = saoPauloToday();

    elements.date.value = today;
    elements.date.max = today;

    elements.error.textContent = "";

    elements.dialog.showModal();

    changeKind();
}

window.openMovement = openMovement;


/* SALVAR MOVIMENTAÇÃO MANUAL */

elements.form.addEventListener(
    "submit",
    async (event) => {
        event.preventDefault();

        if (
            state.saving ||
            state.returnsLoading
        ) {
            return;
        }

        if (!elements.form.reportValidity()) {
            return;
        }

        const isReturn = (
            elements.kind.value === "devolucao"
        );

        if (
            isReturn &&
            !elements.original.value
        ) {
            elements.error.textContent =
                "Selecione a retirada original.";

            return;
        }

        const payload = Object.fromEntries(
            new FormData(elements.form)
        );

        state.saving = true;
        elements.error.textContent = "";

        updateSaveButton();

        try {
            await api(
                "/api/movements",
                {
                    method: "POST",

                    headers: {
                        "Content-Type": "application/json",

                        "X-CSRF-Token": $(
                            'meta[name="csrf-token"]'
                        ).content
                    },

                    body: JSON.stringify(payload)
                }
            );

            elements.dialog.close();

            await refreshDashboard();

        } catch (error) {
            elements.error.textContent =
                error.message +
                " Se houve falha de conexão, confira o histórico " +
                "antes de repetir o lançamento.";

        } finally {
            state.saving = false;

            updateSaveButton();
        }
    }
);


/* EVENTOS DA DASHBOARD */

elements.kind.addEventListener(
    "change",
    changeKind
);

elements.item.addEventListener(
    "change",
    updateUnitHint
);

elements.original.addEventListener(
    "change",
    updateUnitHint
);

elements.dialog.addEventListener(
    "cancel",
    (event) => {
        if (state.saving) {
            event.preventDefault();
        }
    }
);

$("#apply").addEventListener(
    "click",
    () => {
        document.querySelectorAll(
            "[data-period]"
        ).forEach((button) => {
            button.classList.remove("selected");

            button.setAttribute(
                "aria-pressed",
                "false"
            );
        });

        refreshDashboard();
    }
);

document.querySelectorAll(
    "[data-period]"
).forEach((button) => {
    button.addEventListener(
        "click",
        () => selectPeriod(
            button.dataset.period
        )
    );
});

for (const input of [
    elements.start,
    elements.end
]) {
    input.addEventListener(
        "keydown",
        (event) => {
            if (event.key === "Enter") {
                event.preventDefault();

                $("#apply").click();
            }
        }
    );
}

window.setInterval(() => {
    if (!document.hidden) {
        refreshDashboard();
    }
}, 15000);

document.addEventListener(
    "visibilitychange",
    () => {
        if (!document.hidden) {
            refreshDashboard();
        }
    }
);

window.addEventListener(
    "online",
    refreshDashboard
);

window.addEventListener(
    "offline",
    () => {
        elements.sync.textContent = "Sem conexão";

        elements.message.textContent =
            "Você está sem conexão. Os dados exibidos podem estar desatualizados.";
    }
);


/* INICIALIZAÇÃO DA DASHBOARD */

selectPeriod("month");


/* ==========================================
   ASSISTENTE DE RETIRADAS E TABELAS DO SGP
   ========================================== */

(() => {
    const root = $("#text-import");

    if (!root) {
        return;
    }

    const chat = {
        form: $("#text-import-form"),
        fields: $("#text-import-fields"),

        period: $("#text-period"),

        week: $("#text-week"),
        weekLabel: $("#text-week-label"),

        month: $("#text-month"),
        monthLabel: $("#text-month-label"),

        start: $("#text-start"),
        end: $("#text-end"),

        useDefault: $("#text-use-default"),
        defaultLabel: $("#text-default-label"),
        defaultDate: $("#text-default-date"),

        source: $("#text-source"),

        organize: $("#text-organize"),
        example: $("#text-example"),

        status: $("#text-status"),

        preview: $("#text-preview"),
        previewPeriod: $("#text-preview-period"),
        previewTotal: $("#text-preview-total"),

        warnings: $("#text-warnings"),

        issuesBox: $("#text-issues-box"),
        issues: $("#text-issues"),

        technicians: $("#text-technician-totals"),
        rows: $("#text-preview-rows"),

        duplicateLabel: $("#text-duplicate-label"),
        duplicateAck: $("#text-duplicate-ack"),

        confirm: $("#text-confirm"),

        result: $("#text-result"),
        link: $("#text-report-link"),
        open: $("#text-open"),
        copy: $("#text-copy")
    };

    const csrf = $(
        'meta[name="csrf-token"]'
    ).content;

    const currentDay = saoPauloToday();

    let busy = false;
    let token = null;
    let confirmed = false;
    let previewDates = null;

    const technicianMapping = new Map();


    /* AJUSTES DA TELA PARA O SGP */

    chat.source.maxLength = 200000;

    chat.source.placeholder =
        "Cole aqui a tabela completa do SGP, incluindo o cabeçalho.\n" +
        "Pode colar uma tabela com vários técnicos ou importar um técnico por vez.";

    chat.example.textContent =
        "Exemplo de texto manual";

    const help = $("#text-help");

    if (help) {
        help.textContent =
            "SGP: cole a tabela com ID, Data, Local de Origem, " +
            "Local de Destino, Status e Itens. " +
            "As datas vêm da própria tabela. " +
            "Você também pode digitar retiradas com a quantidade " +
            "antes do item. Devoluções continuam no formulário próprio.";
    }

    const intro = root.querySelector(
        ".share-intro"
    );

    if (intro) {
        intro.textContent =
            "Cole as movimentações do SGP de um ou vários técnicos. " +
            "Vou separar os itens novos, identificar os técnicos " +
            "e calcular os custos do catálogo. " +
            "Nada é lançado até você conferir e confirmar.";
    }

    const previewHeading = chat.preview.querySelector(
        ".eyebrow"
    );

    if (previewHeading) {
        previewHeading.textContent =
            "PRÉVIA — SOMENTE RETIRADAS NOVAS";
    }

    const totalCaption = (
        chat.previewTotal.previousElementSibling
    );

    if (totalCaption) {
        totalCaption.textContent =
            "Total das novas retiradas reconhecidas";
    }


    /* ASSOCIAÇÃO DOS NOMES DO SGP */

    const mappingBox = createNode(
        "div",
        undefined,
        "text-import-issues"
    );

    mappingBox.id = "text-sgp-mapping";
    mappingBox.hidden = true;

    chat.fields.append(mappingBox);

    function clearMappings() {
        technicianMapping.clear();

        mappingBox.replaceChildren();
        mappingBox.hidden = true;
    }

    function renderMappings(destinations) {
        mappingBox.replaceChildren();

        mappingBox.hidden = (
            !destinations.length
        );

        if (!destinations.length) {
            return;
        }

        mappingBox.append(
            createNode(
                "h4",
                "Quem são estes técnicos no SGP?"
            ),

            createNode(
                "p",
                "Escolha o técnico de cada destino e clique em " +
                "Organizar retiradas novamente. A associação será " +
                "guardada quando você confirmar a importação."
            )
        );

        destinations.forEach((destination, index) => {
            const label = createNode(
                "label",
                destination
            );

            const select = createNode("select");

            select.id =
                "text-sgp-technician-" + index;

            label.htmlFor = select.id;

            select.required = true;
            select.style.width = "100%";

            const first = createNode(
                "option",
                "Selecione o técnico correspondente"
            );

            first.value = "";

            select.append(first);

            Array.from(
                elements.technician.options
            ).forEach((option) => {
                if (!option.value) {
                    return;
                }

                const choice = createNode(
                    "option",
                    option.textContent.trim()
                );

                choice.value = option.value;

                select.append(choice);
            });

            select.value = (
                technicianMapping.get(destination)
                || ""
            );

            select.addEventListener(
                "change",
                () => {
                    if (select.value) {
                        technicianMapping.set(
                            destination,
                            select.value
                        );

                    } else {
                        technicianMapping.delete(
                            destination
                        );
                    }

                    invalidate();

                    say(
                        "Associação atualizada. Clique em " +
                        "Organizar retiradas novamente para " +
                        "conferir os itens deste técnico."
                    );
                }
            );

            label.append(select);

            mappingBox.append(label);
        });
    }


    /* MENSAGENS */

    function say(message, error = false) {
        chat.status.textContent = message;

        chat.status.classList.toggle(
            "is-error",
            error
        );
    }


    /* DATAS DO ASSISTENTE */

    function shiftDay(value, days) {
        const day = new Date(
            value + "T12:00:00Z"
        );

        day.setUTCDate(
            day.getUTCDate() + days
        );

        return day.toISOString().slice(0, 10);
    }

    function monthBounds(value) {
        const [year, month] = value.split("-").map(
            Number
        );

        if (
            !year ||
            !month ||
            month < 1 ||
            month > 12
        ) {
            return null;
        }

        const next = new Date(
            Date.UTC(
                year,
                month,
                1,
                12
            )
        );

        next.setUTCDate(
            next.getUTCDate() - 1
        );

        return [
            value + "-01",
            next.toISOString().slice(0, 10)
        ];
    }

    const previousMonth = shiftDay(
        currentDay.slice(0, 7) + "-01",
        -1
    ).slice(0, 7);

    chat.month.value = previousMonth;
    chat.month.max = previousMonth;

    chat.week.value = currentDay;

    [
        chat.week,
        chat.start,
        chat.end,
        chat.defaultDate
    ].forEach((input) => {
        input.max = currentDay;
    });


    /* ESTADO DOS BOTÕES */

    function updateConfirm() {
        chat.confirm.disabled = (
            busy ||
            !token ||
            confirmed ||
            (
                !chat.duplicateLabel.hidden &&
                !chat.duplicateAck.checked
            )
        );
    }

    function setBusy(value, action = "") {
        busy = value;

        chat.fields.disabled = value;

        root.setAttribute(
            "aria-busy",
            String(value)
        );

        chat.organize.textContent = (
            value && action === "preview"
        )
            ? "Organizando…"
            : "Organizar retiradas →";

        chat.confirm.textContent = (
            value && action === "confirm"
        )
            ? "Salvando e gerando link…"
            : confirmed
                ? "Retiradas já confirmadas ✓"
                : "Conferi: salvar retiradas e gerar link →";

        updateConfirm();
    }


    /* INVALIDAÇÃO DA PRÉVIA */

    function invalidate() {
        if (busy) {
            return;
        }

        token = null;
        confirmed = false;
        previewDates = null;

        chat.preview.hidden = true;
        chat.result.hidden = true;

        chat.link.value = "";

        chat.open.removeAttribute("href");

        chat.duplicateAck.checked = false;

        chat.confirm.textContent =
            "Conferi: salvar retiradas e gerar link →";

        updateConfirm();

        say(
            "Texto ou período atualizado. Clique em " +
            "Organizar retiradas para preparar a prévia."
        );
    }


    /* DATA PADRÃO PARA TEXTO MANUAL */

    function updateDefault() {
        chat.defaultLabel.hidden = (
            !chat.useDefault.checked
        );

        chat.defaultDate.disabled = (
            !chat.useDefault.checked
        );

        chat.defaultDate.required = (
            chat.useDefault.checked
        );

        chat.defaultDate.min = chat.start.value;

        chat.defaultDate.max = (
            chat.end.value ||
            currentDay
        );
    }


    /* PERÍODOS */

    function showPeriodControls() {
        const isWeek = (
            chat.period.value === "week"
        );

        const isMonth = (
            chat.period.value === "month"
        );

        chat.weekLabel.hidden = !isWeek;
        chat.monthLabel.hidden = !isMonth;

        chat.week.disabled = !isWeek;
        chat.month.disabled = !isMonth;

        chat.week.required = isWeek;
        chat.month.required = isMonth;
    }

    function applyPeriod() {
        showPeriodControls();

        if (
            chat.period.value === "week" &&
            chat.week.value
        ) {
            const day = new Date(
                chat.week.value + "T12:00:00Z"
            );

            const monday = shiftDay(
                chat.week.value,
                -((day.getUTCDay() + 6) % 7)
            );

            chat.start.value = monday;

            const friday = shiftDay(
                monday,
                4
            );

            chat.end.value = (
                friday < currentDay
                    ? friday
                    : currentDay
            );

        } else if (chat.period.value === "last30") {
            chat.start.value = shiftDay(
                currentDay,
                -29
            );

            chat.end.value = currentDay;

        } else if (chat.period.value === "month") {
            const bounds = monthBounds(
                chat.month.value
            );

            if (bounds) {
                [
                    chat.start.value,
                    chat.end.value
                ] = bounds;
            }
        }

        chat.end.min = chat.start.value;

        updateDefault();
        invalidate();
    }


    /* VALIDAÇÃO DO FORMULÁRIO */

    function validDates() {
        if (!chat.form.reportValidity()) {
            return false;
        }

        const start = chat.start.value;
        const end = chat.end.value;

        if (
            !start ||
            !end ||
            end < start ||
            end > currentDay
        ) {
            say(
                "Confira o período: a data final deve ser igual " +
                "ou posterior à inicial e não pode estar no futuro.",
                true
            );

            return false;
        }

        const days = (
            Date.parse(end) - Date.parse(start)
        ) / 86400000;

        if (days > 366) {
            say(
                "Escolha um período de até 367 dias.",
                true
            );

            return false;
        }

        if (
            chat.useDefault.checked &&
            (
                !chat.defaultDate.value ||
                chat.defaultDate.value < start ||
                chat.defaultDate.value > end
            )
        ) {
            say(
                "Escolha uma data padrão dentro do período.",
                true
            );

            return false;
        }

        return true;
    }


    /* REQUISIÇÕES DO ASSISTENTE */

    async function post(url, payload) {
        return api(
            url,
            {
                method: "POST",

                headers: {
                    "Content-Type": "application/json",
                    "X-CSRF-Token": csrf
                },

                body: JSON.stringify(payload)
            }
        );
    }


    /* EXIBIR UM RELATÓRIO */

    function showReport(report) {
        if (
            !report ||
            !report.active ||
            !report.url
        ) {
            chat.result.hidden = true;

            return false;
        }

        const url = new URL(
            report.url,
            window.location.href
        );

        if (
            url.origin !== window.location.origin ||
            !url.pathname.startsWith("/r/")
        ) {
            throw new Error(
                "O endereço retornado não corresponde " +
                "a um relatório deste sistema."
            );
        }

        chat.link.value = url.href;
        chat.open.href = url.href;

        chat.result.hidden = false;

        return true;
    }


    /* EXIBIR A PRÉVIA */

    function renderPreview(data) {
        if (
            !Array.isArray(data.rows) ||
            !Array.isArray(data.issues)
        ) {
            throw new Error(
                "O servidor retornou uma prévia inválida. " +
                "Atualize a página."
            );
        }

        chat.preview.hidden = false;

        chat.previewPeriod.textContent =
            displayDate(data.start) +
            " a " +
            displayDate(data.end);

        chat.previewTotal.textContent = money(
            Number(data.total)
        );

        chat.rows.replaceChildren();
        chat.technicians.replaceChildren();
        chat.issues.replaceChildren();
        chat.warnings.replaceChildren();

        chat.duplicateAck.checked = false;

        chat.duplicateLabel.hidden = (
            !data.requires_duplicate_ack
        );

        chat.issuesBox.hidden = (
            data.issues.length === 0
        );

        renderMappings(
            data.unknown_technicians || []
        );

        for (const row of data.rows) {
            const tr = createNode("tr");

            const itemCell = createNode("td");

            itemCell.append(
                createNode(
                    "span",
                    row.item
                )
            );

            if (row.sgp_id) {
                const origin = createNode(
                    "small",

                    "SGP #" +
                    row.sgp_id +
                    (
                        row.sgp_serial
                            ? " · Série/MAC: " + row.sgp_serial
                            : ""
                    )
                );

                origin.style.display = "block";
                origin.style.marginTop = "5px";
                origin.style.color = "var(--muted)";

                itemCell.append(origin);

                itemCell.title = (
                    row.sgp_description ||
                    row.item
                );
            }

            tr.append(
                createNode(
                    "td",
                    displayDate(row.date)
                ),

                createNode(
                    "td",
                    row.technician
                ),

                itemCell,

                createNode(
                    "td",
                    quantityText(
                        Number(row.quantity)
                    ) + " " + row.unit
                ),

                createNode(
                    "td",
                    money(Number(row.total))
                )
            );

            chat.rows.append(tr);
        }

        if (!data.rows.length) {
            const tr = createNode("tr");

            const td = createNode(
                "td",

                data.all_imported
                    ? "Todas estas retiradas já foram importadas. " +
                      "Nenhum lançamento novo."
                    : "Nenhuma retirada nova reconhecida neste período. " +
                      "Confira os avisos e as pendências."
            );

            td.colSpan = 5;

            tr.append(td);

            chat.rows.append(tr);
        }

        for (
            const [name, value]
            of Object.entries(data.technicians || {})
        ) {
            chat.technicians.append(
                createNode(
                    "span",
                    name + " · " + money(Number(value))
                )
            );
        }

        for (const issue of data.issues) {
            const li = createNode("li");

            li.append(
                createNode(
                    "span",
                    issue.message
                )
            );

            if (issue.excerpt) {
                li.append(
                    createNode("br"),

                    createNode(
                        "code",
                        'Trecho: "' + issue.excerpt + '"'
                    )
                );
            }

            chat.issues.append(li);
        }

        const warnings = [
            ...(data.warnings || [])
        ];

        if (data.used_default_date) {
            warnings.push(
                "A data " +
                displayDate(data.used_default_date) +
                " foi escolhida como padrão. " +
                "Confira todas as datas na tabela."
            );
        }

        chat.warnings.hidden = (
            warnings.length === 0
        );

        warnings.forEach((message) => {
            chat.warnings.append(
                createNode(
                    "li",
                    message
                )
            );
        });

        token = (
            data.can_confirm && data.token
                ? data.token
                : null
        );

        previewDates = {
            start: data.start,
            end: data.end
        };

        if (data.issues.length) {
            say(
                "Encontrei pendências. Confira os trechos " +
                "indicados e, se houver nomes desconhecidos, " +
                "selecione o técnico correspondente. " +
                "Depois clique em Organizar novamente. " +
                "Nada foi salvo.",
                true
            );

        } else if (data.all_imported) {
            const hasLink = (
                data.existing_report
                    ? showReport(data.existing_report)
                    : false
            );

            say(
                "Estas retiradas já foram importadas. " +
                "Nada foi lançado novamente." +

                (
                    hasLink
                        ? " O link abaixo é do fechamento anterior, de " +
                          displayDate(data.existing_report.start) +
                          " a " +
                          displayDate(data.existing_report.end) +
                          "."
                        : ""
                ) +

                " Para um fechamento geral atualizado, " +
                "use Gerar link de relatório."
            );

        } else if (token) {
            const events = (
                data.sgp_events || []
            ).length;

            say(
                "Beleza! Organizei " +
                data.rows.length +
                " itens novos" +

                (
                    events
                        ? " de " + events + " movimentações do SGP"
                        : ""
                ) +

                ". Confira os técnicos, as datas, " +
                "as quantidades e os valores. " +
                "Nada foi salvo ainda."
            );

        } else {
            say(
                "Não há retiradas novas para confirmar neste período. " +
                "Confira os avisos: registros fora do período, " +
                "sem aprovação ou com outra origem " +
                "não entram na importação."
            );
        }
    }


    /* ENVIAR A TABELA OU TEXTO */

    chat.form.addEventListener(
        "submit",
        async (event) => {
            event.preventDefault();

            if (busy || !validDates()) {
                return;
            }

            if (!chat.source.value.trim()) {
                say(
                    "Escreva o que cada técnico retirou.",
                    true
                );

                return;
            }

            invalidate();

            const payload = {
                text: chat.source.value,

                start: chat.start.value,
                end: chat.end.value,

                default_date: (
                    chat.useDefault.checked
                        ? chat.defaultDate.value
                        : null
                ),

                technician_mapping: Object.fromEntries(
                    technicianMapping
                )
            };

            setBusy(
                true,
                "preview"
            );

            say(
                "Beleza, vou conferir os técnicos, " +
                "os itens e os IDs já importados. " +
                "Já te mostro a prévia…"
            );

            try {
                const data = await post(
                    "/api/text-import/preview",
                    payload
                );

                renderPreview(data);

            } catch (error) {
                token = null;

                chat.preview.hidden = true;

                say(
                    error.message,
                    true
                );

            } finally {
                setBusy(false);
            }
        }
    );


    /* CONFIRMAR E GERAR O LINK */

    chat.confirm.addEventListener(
        "click",
        async () => {
            if (
                busy ||
                !token ||
                confirmed
            ) {
                return;
            }

            if (
                !chat.duplicateLabel.hidden &&
                !chat.duplicateAck.checked
            ) {
                say(
                    "Confira as possíveis duplicidades " +
                    "e marque a confirmação.",
                    true
                );

                return;
            }

            setBusy(
                true,
                "confirm"
            );

            say(
                "Estou salvando as retiradas e preparando " +
                "o relatório com todas as movimentações do período…"
            );

            try {
                const report = await post(
                    "/api/text-import/confirm",
                    {
                        token,
                        confirm: true,
                        ack_duplicates: chat.duplicateAck.checked
                    }
                );

                confirmed = true;
                token = null;

                chat.preview.hidden = true;

                clearMappings();

                const hasLink = showReport(report);

                say(
                    hasLink
                        ? (
                            report.reused
                                ? "Esta importação já estava confirmada. " +
                                  "Aqui está o mesmo relatório, " +
                                  "sem duplicar as retiradas."
                                : "Pronto! Retiradas salvas e relatório gerado. " +
                                  "Agora é só copiar o link e mandar ao seu chefe."
                        )
                        : "A importação já foi confirmada, " +
                          "mas o link está desativado. " +
                          "Gere outro fechamento em Gerar link de relatório."
                );

                if (previewDates) {
                    elements.start.value = (
                        previewDates.start
                    );

                    elements.end.value = (
                        previewDates.end
                    );

                    document.querySelectorAll(
                        "[data-period]"
                    ).forEach((button) => {
                        button.classList.remove(
                            "selected"
                        );

                        button.setAttribute(
                            "aria-pressed",
                            "false"
                        );
                    });
                }

                refreshDashboard();

                const reload = $("#share-reload");

                if (reload && !reload.disabled) {
                    reload.click();
                }

            } catch (error) {
                say(
                    error.message +

                    (
                        confirmed
                            ? " A gravação foi concluída. " +
                              "Confira a lista de relatórios gerados " +
                              "para abrir o link."
                            : " Se a conexão caiu, você pode tentar " +
                              "Confirmar novamente: a mesma prévia " +
                              "não é gravada duas vezes."
                    ),

                    true
                );

            } finally {
                setBusy(false);
            }
        }
    );


    /* COPIAR LINK */

    chat.copy.addEventListener(
        "click",
        async () => {
            if (!chat.link.value) {
                return;
            }

            try {
                await navigator.clipboard.writeText(
                    chat.link.value
                );

                say(
                    "Link copiado! Pode colar " +
                    "na conversa com seu chefe."
                );

            } catch {
                chat.link.focus();
                chat.link.select();

                chat.link.setSelectionRange(
                    0,
                    chat.link.value.length
                );

                say(
                    "O link está selecionado. " +
                    "Pressione Ctrl + C ou use Copiar no celular."
                );
            }
        }
    );


    /* EVENTOS DO ASSISTENTE */

    chat.period.addEventListener(
        "change",
        applyPeriod
    );

    chat.week.addEventListener(
        "change",
        applyPeriod
    );

    chat.month.addEventListener(
        "change",
        applyPeriod
    );

    [
        chat.start,
        chat.end
    ].forEach((input) => {
        input.addEventListener(
            "change",
            () => {
                chat.period.value = "custom";

                showPeriodControls();

                chat.end.min = chat.start.value;

                updateDefault();
                invalidate();
            }
        );
    });

    chat.useDefault.addEventListener(
        "change",
        () => {
            updateDefault();
            invalidate();
        }
    );

    chat.source.addEventListener(
        "input",
        () => {
            clearMappings();
            invalidate();
        }
    );

    chat.defaultDate.addEventListener(
        "input",
        invalidate
    );

    chat.duplicateAck.addEventListener(
        "change",
        updateConfirm
    );


    /* EXEMPLO DE TEXTO MANUAL */

    chat.example.addEventListener(
        "click",
        () => {
            if (busy) {
                return;
            }

            if (chat.source.value.trim()) {
                say(
                    "O campo já tem um texto. " +
                    "Apague-o primeiro se quiser preencher o exemplo."
                );

                return;
            }

            if (!chat.start.value) {
                applyPeriod();
            }

            clearMappings();

            chat.source.value =
                displayDate(chat.start.value) + "\n" +
                "Rogério pegou 3 APC e 4 cunhas.\n" +
                "Magno retirou 1 XC220.\n" +
                "Wildiney pegou 100 metros de cabo miniflatdrop.";

            invalidate();

            say(
                "Exemplo preenchido. Troque pelos dados reais " +
                "antes de confirmar: confirmar este exemplo " +
                "gravaria essas retiradas."
            );

            chat.source.focus();
        }
    );


    /* INICIALIZAÇÃO */

    applyPeriod();

    say(
        "Olá! Cole a tabela do SGP de um ou vários técnicos. " +
        "Vou organizar as retiradas novas para você conferir " +
        "e gerar o relatório."
    );
})();
