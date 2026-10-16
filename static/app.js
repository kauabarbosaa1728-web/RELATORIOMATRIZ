"use strict";

/* ==========================================
   ALMOXARIFADO MATRIZ
   Dashboard e movimentações
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


/* ELEMENTOS */

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

    const days = (end - start) / 86400000;

    if (days > 366) {
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

        button.classList.toggle("selected", selected);

        button.setAttribute(
            "aria-pressed",
            String(selected)
        );
    });

    refreshDashboard();
}


/* CRIAÇÃO SEGURA DE ELEMENTOS */

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


/* ATUALIZAÇÃO DA DASHBOARD */

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


/* FORMULÁRIO DE MOVIMENTAÇÃO */

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

// Permite o uso nos botões onclick do HTML.
window.openMovement = openMovement;


/* SALVAR MOVIMENTAÇÃO */

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


/* EVENTOS */

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

// Atualização periódica enquanto a página estiver visível.
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


/* INICIALIZAÇÃO */

selectPeriod("month");
