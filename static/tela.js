"use strict";

/* ==========================================
   ALMOXARIFADO MATRIZ
   Limpeza visual e modo de apresentação

   Não apaga movimentações.
   Não altera valores no banco.
   Não desativa links.
   ========================================== */

(() => {
    const get = (selector) => document.querySelector(selector);

    const main = get("main#overview");

    if (!main) {
        return;
    }

    function node(tag, text, className) {
        const result = document.createElement(tag);

        if (text !== undefined) {
            result.textContent = text;
        }

        if (className) {
            result.className = className;
        }

        return result;
    }


    /* CONTROLES DA DASHBOARD */

    let blank = false;

    const originals = new Map();
    const copies = [];

    const toolbar = get(".toolbar");

    const actions = node(
        "div",
        undefined,
        "actions"
    );

    const clear = node(
        "button",
        "Limpar tela"
    );

    const show = node(
        "button",
        "Mostrar dados"
    );

    const indicator = node(
        "p",
        "Tela limpa para apresentação. Os registros continuam salvos.",
        "muted footnote"
    );

    clear.type = "button";
    show.type = "button";

    show.hidden = true;
    indicator.hidden = true;

    indicator.setAttribute(
        "role",
        "status"
    );

    actions.append(
        clear,
        show
    );

    if (toolbar) {
        toolbar.append(actions);
        toolbar.after(indicator);
    }


    /* VERIFICAR OPERAÇÕES EM ANDAMENTO */

    function isBusy() {
        const importing = get(
            '#text-import[aria-busy="true"]'
        ) !== null;

        const generating = Array.from(
            document.querySelectorAll(
                "button[data-generate]"
            )
        ).some((button) => button.disabled);

        return importing || generating;
    }


    /* LIMPAR CAMPO, PRÉVIA E LINK EXIBIDO */

    function clearAssistant() {
        if (isBusy()) {
            window.alert(
                "Aguarde a operação terminar antes de limpar a tela."
            );

            return false;
        }

        const source = get("#text-source");

        if (source) {
            source.value = "";

            // O app.js também descarta o token da prévia.
            source.dispatchEvent(
                new Event(
                    "input",
                    {
                        bubbles: true
                    }
                )
            );
        }

        [
            "#text-preview",
            "#text-result",
            "#share-result"
        ].forEach((selector) => {
            const element = get(selector);

            if (element) {
                element.hidden = true;
            }
        });

        [
            "#text-report-link",
            "#share-link"
        ].forEach((selector) => {
            const input = get(selector);

            if (input) {
                input.value = "";
            }
        });

        [
            "#text-open",
            "#share-open"
        ].forEach((selector) => {
            const link = get(selector);

            if (link) {
                link.removeAttribute("href");
            }
        });

        const shareStatus = get("#share-status");

        if (shareStatus) {
            shareStatus.textContent = "";
        }

        const chatStatus = get("#text-status");

        if (chatStatus) {
            chatStatus.classList.remove(
                "is-error"
            );

            chatStatus.textContent =
                "Campo limpo. Cole outra tabela para preparar " +
                "um novo relatório. Os lançamentos anteriores " +
                "continuam salvos.";
        }

        return true;
    }


    /* CRIAR UMA CÓPIA VISUAL ZERADA */

    function zeroCopy(original) {
        const copy = original.cloneNode(true);

        copy.hidden = false;

        const local = (id) => {
            return copy.querySelector(
                "#" + id
            );
        };

        [
            "total",
            "materials",
            "equipment",
            "returns",
            "donut-value"
        ].forEach((id) => {
            const element = local(id);

            if (element) {
                element.textContent = "R$ 0,00";
            }
        });

        [
            "difference",
            "mat-share",
            "eq-share"
        ].forEach((id) => {
            const element = local(id);

            if (element) {
                element.textContent = "—";
            }
        });

        const comparison = local("comparison");

        if (comparison) {
            comparison.textContent =
                "Tela limpa para apresentação";

            comparison.removeAttribute("title");
        }

        const count = local("count");

        if (count) {
            count.textContent =
                "0 movimentações exibidas";
        }

        const donut = local("donut");

        if (donut) {
            donut.style.background = "#293832";
            donut.removeAttribute("title");
        }

        copy.querySelectorAll(
            ".timeline, .bars"
        ).forEach((chart) => {
            chart.replaceChildren(
                node(
                    "div",
                    "Tela limpa. Clique em Mostrar dados " +
                    "para voltar ao histórico salvo.",
                    "empty"
                )
            );
        });

        const rows = local("rows");

        if (rows) {
            const tr = node("tr");

            const td = node(
                "td",
                "Nenhuma movimentação exibida " +
                "no modo de apresentação."
            );

            td.colSpan = 6;

            tr.append(td);
            rows.replaceChildren(tr);

            // A exportação continua usando os dados reais.
            // Não apresenta botões de exportação na cópia zerada.
            const exports = copy.querySelector(
                ".actions"
            );

            if (exports) {
                exports.remove();
            }
        }

        copy.querySelectorAll(
            ".negative"
        ).forEach((element) => {
            element.classList.remove(
                "negative"
            );
        });

        // As cópias não reutilizam os IDs da dashboard real.
        [
            copy,
            ...copy.querySelectorAll("[id]")
        ].forEach((element) => {
            element.removeAttribute("id");
        });

        copy.querySelectorAll(
            "[title]"
        ).forEach((element) => {
            element.removeAttribute("title");
        });

        copy.dataset.presentationCopy = "true";

        copy.querySelectorAll(
            "a, button, input, select, textarea"
        ).forEach((control) => {
            if (control.tagName === "A") {
                control.removeAttribute("href");

                control.setAttribute(
                    "aria-disabled",
                    "true"
                );

            } else {
                control.disabled = true;
            }
        });

        return copy;
    }


    /* LIMPAR SOMENTE A VISUALIZAÇÃO */

    function clearDashboard() {
        if (!clearAssistant()) {
            return;
        }

        if (!blank) {
            const panels = Array.from(
                main.children
            ).filter((element) => {
                return element.matches(
                    ".kpis, .chart-grid, #history"
                );
            });

            panels.forEach((original) => {
                const copy = zeroCopy(original);

                originals.set(
                    original,
                    original.hidden
                );

                original.hidden = true;

                original.before(copy);

                copies.push(copy);
            });

            blank = true;
        }

        show.hidden = false;
        indicator.hidden = false;

        clear.textContent =
            "Limpar tela novamente";
    }


    /* VOLTAR A MOSTRAR OS DADOS REAIS */

    function showDashboard() {
        copies.splice(0).forEach((copy) => {
            copy.remove();
        });

        originals.forEach(
            (wasHidden, original) => {
                original.hidden = wasHidden;
            }
        );

        originals.clear();

        blank = false;

        show.hidden = true;
        indicator.hidden = true;

        clear.textContent = "Limpar tela";

        if (
            typeof window.refreshDashboard === "function"
        ) {
            window.refreshDashboard();
        }
    }

    clear.addEventListener(
        "click",
        clearDashboard
    );

    show.addEventListener(
        "click",
        showDashboard
    );


    /* VOLTAR AOS DADOS AO INICIAR UM LANÇAMENTO */

    [
        "#text-confirm",
        "#movement-form"
    ].forEach((selector) => {
        const element = get(selector);

        if (!element) {
            return;
        }

        const eventName = (
            selector === "#movement-form"
                ? "submit"
                : "click"
        );

        element.addEventListener(
            eventName,
            () => {
                const disabledConfirmation = (
                    selector === "#text-confirm"
                    && element.disabled
                );

                if (
                    blank
                    && !disabledConfirmation
                ) {
                    showDashboard();
                }
            },
            true
        );
    });


    /* BOTÃO DO ASSISTENTE */

    const assistantActions = get(
        ".text-import-actions"
    );

    if (assistantActions) {
        const reset = node(
            "button",
            "Limpar / começar outro"
        );

        reset.type = "button";

        reset.addEventListener(
            "click",
            () => {
                if (clearAssistant()) {
                    get("#text-source")?.focus();
                }
            }
        );

        assistantActions.append(reset);
    }


    /* MENU DO HISTÓRICO NO MODO DE APRESENTAÇÃO */

    document.querySelectorAll(
        'nav a[href="#history"]'
    ).forEach((link) => {
        link.addEventListener(
            "click",
            (event) => {
                if (!blank) {
                    return;
                }

                const historyCopy = copies.find(
                    (copy) => copy.querySelector("table")
                );

                if (historyCopy) {
                    event.preventDefault();

                    historyCopy.scrollIntoView({
                        behavior: "smooth",
                        block: "start"
                    });
                }
            }
        );
    });


    /* ==========================================
       OCULTAR RELATÓRIOS DA LISTA

       A escolha fica neste navegador.
       Os relatórios podem ser restaurados.
       ========================================== */

    const list = get("#share-list");

    const heading = get(
        ".share-history-heading"
    );

    if (!list || !heading) {
        return;
    }

    const storageKey = (
        "matriz-hidden-reports-"
        + String(
            window.MATRIZ_SCREEN_USER || "local"
        )
    );

    let hiddenReports = new Set();

    try {
        const saved = JSON.parse(
            localStorage.getItem(storageKey)
            || "[]"
        );

        if (Array.isArray(saved)) {
            hiddenReports = new Set(
                saved.filter(
                    (value) => typeof value === "string"
                )
            );
        }

    } catch {
        // Continua funcionando durante esta visita.
    }

    const restore = node(
        "button",
        "Restaurar relatórios ocultos"
    );

    restore.type = "button";

    heading.append(restore);

    const notice = node(
        "p",
        "",
        "muted footnote"
    );

    notice.hidden = true;

    list.after(notice);


    /* IDENTIFICAR O CARTÃO EXIBIDO */

    function reportKey(card) {
        const title = card.querySelector(
            ".saved-report-info strong"
        )?.textContent || "";

        const period = card.querySelector(
            ".saved-report-info p"
        )?.textContent || "";

        const generated = card.querySelector(
            ".saved-report-info small"
        )?.textContent || "";

        return [
            title,
            period,
            generated
        ].map((value) => {
            return value.replace(
                /\s+/g,
                " "
            ).trim();
        }).join(" | ");
    }


    /* GUARDAR A ESCOLHA LOCAL */

    function saveHidden() {
        try {
            localStorage.setItem(
                storageKey,
                JSON.stringify(
                    [...hiddenReports]
                )
            );

        } catch {
            // Sem armazenamento, mantém só nesta visita.
        }
    }


    /* ATUALIZAR BOTÕES E VISIBILIDADE */

    function updateReports() {
        let hiddenCount = 0;

        list.querySelectorAll(
            ".saved-report"
        ).forEach((card) => {
            const key = reportKey(card);

            if (!card.dataset.screenControls) {
                const controls = card.querySelector(
                    ".share-actions"
                );

                if (controls) {
                    const hide = node(
                        "button",
                        "Ocultar da lista"
                    );

                    hide.type = "button";

                    hide.title =
                        "Oculta neste navegador. Não apaga " +
                        "movimentações e não desativa o link.";

                    hide.addEventListener(
                        "click",
                        () => {
                            hiddenReports.add(key);

                            saveHidden();
                            updateReports();
                        }
                    );

                    controls.append(hide);

                    card.dataset.screenControls = "true";
                }
            }

            card.hidden = hiddenReports.has(key);

            if (card.hidden) {
                hiddenCount++;
            }
        });

        restore.disabled = (
            hiddenReports.size === 0
        );

        notice.hidden = (
            hiddenCount === 0
        );

        const message = (
            hiddenCount
            + " relatório(s) oculto(s) neste navegador. "
            + "Os links e as movimentações continuam salvos."
        );

        if (notice.textContent !== message) {
            notice.textContent = message;
        }
    }


    /* RESTAURAR OS CARTÕES OCULTOS */

    restore.addEventListener(
        "click",
        () => {
            hiddenReports.clear();

            saveHidden();
            updateReports();
        }
    );


    /* ACOMPANHAR A ATUALIZAÇÃO DA LISTA */

    new MutationObserver(
        updateReports
    ).observe(
        list,
        {
            childList: true,
            subtree: true
        }
    );

    updateReports();
})();
