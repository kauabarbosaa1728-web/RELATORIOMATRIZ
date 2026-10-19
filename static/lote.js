(() => {
    "use strict";

    const form = document.getElementById("text-import-form");
    const source = document.getElementById("text-source");
    const organize = document.getElementById("text-organize");

    if (
        !form ||
        !source ||
        !organize ||
        document.getElementById("sgp-lote")
    ) {
        return;
    }

    let tables = [];
    let writing = false;

    const box = document.createElement("div");
    box.id = "sgp-lote";

    const editor = document.createElement("textarea");
    editor.id = "sgp-tabela-atual";
    editor.rows = 9;
    editor.maxLength = 200000;
    editor.placeholder =
        "Cole aqui a tabela do primeiro técnico, incluindo " +
        "o cabeçalho do SGP. Depois clique em Adicionar tabela à lista.";

    editor.style.cssText =
        "width:100%;" +
        "box-sizing:border-box;" +
        "margin:10px 0;";

    const label = document.createElement("label");
    label.htmlFor = editor.id;
    label.textContent = "Tabelas dos técnicos";

    const add = document.createElement("button");
    add.type = "button";
    add.className = "primary";
    add.textContent = "＋ Adicionar tabela à lista";

    const notice = document.createElement("p");
    notice.className = "muted";
    notice.setAttribute("role", "status");
    notice.setAttribute("aria-live", "polite");

    const list = document.createElement("div");

    box.append(label, editor, add, notice, list);
    source.before(box);

    source.hidden = true;
    source.required = false;

    const oldLabel = form.querySelector('label[for="text-source"]');

    if (oldLabel) {
        oldLabel.hidden = true;
    }

    const example = document.getElementById("text-example");

    if (example) {
        example.hidden = true;
    }

    const help = document.getElementById("text-help");

    if (help) {
        help.textContent =
            "Adicione as tabelas dos técnicos à lista. " +
            "Escolha um único período, organize tudo, confira a prévia " +
            "e confirme para gerar um link com todos. " +
            "Você pode adicionar mais de uma tabela do mesmo técnico.";
    }

    organize.textContent = "Organizar todas as tabelas";

    function format(text) {
        if (text.includes("\t")) {
            return "tsv";
        }

        if (/^\s*\|/m.test(text)) {
            return "markdown";
        }

        return "texto";
    }

    function synchronize() {
        writing = true;

        source.value = tables.join("\n\n");

        source.dispatchEvent(
            new Event("input", { bubbles: true })
        );

        writing = false;

        render();
    }

    function render() {
        list.replaceChildren();

        notice.textContent = tables.length
            ? tables.length +
              " tabela(s) na lista. Adicione as restantes " +
              "ou organize tudo abaixo."
            : "Lista vazia. Adicione as tabelas dos 9 técnicos " +
              "antes de organizar.";

        tables.forEach((text, index) => {
            const row = document.createElement("div");
            row.className = "saved-report";

            const title = document.createElement("strong");
            title.textContent = "Tabela " + (index + 1);

            const details = document.createElement("details");

            const summary = document.createElement("summary");
            summary.textContent = "Conferir texto adicionado";

            const pre = document.createElement("pre");
            pre.textContent = text;

            pre.style.cssText =
                "white-space:pre-wrap;" +
                "overflow-wrap:anywhere;" +
                "max-height:180px;" +
                "overflow:auto;" +
                "font-size:12px;";

            details.append(summary, pre);

            const remove = document.createElement("button");
            remove.type = "button";
            remove.textContent = "Remover da lista";

            remove.addEventListener("click", () => {
                tables.splice(index, 1);
                synchronize();
            });

            row.append(title, details, remove);
            list.append(row);
        });
    }

    function addCurrent() {
        const text = editor.value.trim();

        if (!text) {
            return true;
        }

        if (tables.includes(text)) {
            notice.textContent =
                "Esta tabela já está na lista. Cole a próxima tabela.";

            editor.value = "";

            return true;
        }

        if (
            tables.length &&
            format(text) !== format(tables[0])
        ) {
            notice.textContent =
                "Copie todas as tabelas do mesmo modo no SGP, " +
                "incluindo o cabeçalho. Esta tabela veio em outro " +
                "formato e ainda não foi adicionada.";

            return false;
        }

        const combined = [...tables, text].join("\n\n");

        if (combined.length > 200000) {
            notice.textContent =
                "O conjunto ultrapassou 200 mil caracteres. " +
                "Reduza o período antes de organizar.";

            return false;
        }

        tables.push(text);
        editor.value = "";

        synchronize();

        return true;
    }

    add.addEventListener("click", () => {
        addCurrent();
        editor.focus();
    });

    editor.addEventListener("input", () => {
        // Qualquer alteração exige conferir uma nova prévia.
        writing = true;

        source.dispatchEvent(
            new Event("input", { bubbles: true })
        );

        writing = false;
    });

    form.addEventListener(
        "submit",
        event => {
            // Inclui também a última tabela, caso ainda esteja no campo.
            if (!addCurrent() || !tables.length) {
                event.preventDefault();
                event.stopImmediatePropagation();

                if (!tables.length) {
                    notice.textContent =
                        "Cole pelo menos uma tabela do SGP para organizar.";
                }
            }
        },
        true
    );

    source.addEventListener("input", () => {
        // Integra com o botão Limpar / começar outro.
        if (!writing && !source.value.trim()) {
            tables = [];
            editor.value = "";

            render();
        }
    });

    if (source.value.trim()) {
        tables.push(source.value.trim());
    }

    render();
})();
