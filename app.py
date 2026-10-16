import os
import secrets
import io
import csv

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps
from zoneinfo import ZoneInfo

from flask import (
    Flask,
    render_template,
    request,
    session,
    redirect,
    url_for,
    jsonify,
    abort,
    send_file,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select, func
from werkzeug.security import generate_password_hash, check_password_hash


# CONFIGURAÇÃO

app = Flask(__name__)

database_url = os.environ.get(
    "DATABASE_URL",
    "sqlite:///matriz.db",
).replace("postgres://", "postgresql://", 1)

app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    SQLALCHEMY_DATABASE_URI=database_url,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",
    MAX_CONTENT_LENGTH=1024 * 1024,
)

db = SQLAlchemy(app)


# BANCO DE DADOS

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(
        db.String(80),
        unique=True,
        nullable=False,
    )

    password = db.Column(
        db.String(256),
        nullable=False,
    )


class Technician(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(
        db.String(80),
        unique=True,
        nullable=False,
    )


class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(
        db.String(100),
        unique=True,
        nullable=False,
    )

    category = db.Column(
        db.String(20),
        nullable=False,
    )

    unit = db.Column(
        db.String(20),
        nullable=False,
    )

    cost = db.Column(
        db.Numeric(18, 9),
        nullable=False,
    )


class Movement(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    day = db.Column(
        db.Date,
        nullable=False,
        index=True,
    )

    technician_id = db.Column(
        db.Integer,
        db.ForeignKey("technician.id"),
        nullable=False,
    )

    item_id = db.Column(
        db.Integer,
        db.ForeignKey("item.id"),
        nullable=False,
    )

    quantity = db.Column(
        db.Numeric(16, 3),
        nullable=False,
    )

    # Guarda o preço utilizado na data do lançamento.
    cost = db.Column(
        db.Numeric(18, 9),
        nullable=False,
    )

    kind = db.Column(
        db.String(12),
        nullable=False,
    )

    # Nas devoluções, identifica a retirada original.
    original_id = db.Column(
        db.Integer,
        db.ForeignKey("movement.id"),
    )

    note = db.Column(
        db.String(300),
        nullable=False,
        default="",
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    technician = db.relationship(Technician)
    item = db.relationship(Item)


# TÉCNICOS E PREÇOS INICIAIS

TECHNICIANS = [
    "Rogério",
    "Magno",
    "George",
    "Danilo",
    "Jilvan",
    "Josenildo",
    "Mateus",
    "Wildiney",
    "Vagner",
]

MATERIALS = [
    ("APC", "un", "6.10"),
    ("Abraçadeira", "un", str(Decimal("20.80") / 100)),
    ("UPC", "un", "6.10"),
    ("Cunha", "un", "2.94"),
    ("Bucha de acabamento", "un", "1.50"),
    ("Fita isolante", "rolo", "5.57"),
    ("Pino Jack RJ45", "un", "0.24"),
    ("Miguelão", "un", "0.31"),
    ("Cabo de rede", "m", str(Decimal("175.30") / 305)),
    ("Cabo Miniflatdrop", "m", "0.3909"),
]

EQUIPMENT = [
    ("XC220", "300"),
    ("XX530", "400"),
    ("XX535", "300"),
    ("XX230", "400"),
    ("121AC", "489"),
    ("1200R", "300"),
    ("EX141", "200"),
    ("TP-LINK BRANCO", "150"),
    ("HALOS12", "155"),
    ("MR60X", "300"),
    ("ONU TP-LINK", "150"),
    ("ONU 1010", "150"),
    ("FIRESTICK", "300"),
]


# FUNÇÕES AUXILIARES

def today():
    return datetime.now(
        ZoneInfo("America/Sao_Paulo")
    ).date()


def money(value):
    formatted = f"R$ {Decimal(str(value)):,.2f}"

    return (
        formatted
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


app.jinja_env.filters["money"] = money


def init_db():
    db.create_all()

    for name in TECHNICIANS:
        existing = db.session.scalar(
            select(Technician).where(
                Technician.name == name
            )
        )

        if not existing:
            db.session.add(
                Technician(name=name)
            )

    for name, unit, cost in MATERIALS:
        existing = db.session.scalar(
            select(Item).where(
                Item.name == name
            )
        )

        if not existing:
            db.session.add(
                Item(
                    name=name,
                    unit=unit,
                    cost=Decimal(cost),
                    category="material",
                )
            )

    for name, cost in EQUIPMENT:
        existing = db.session.scalar(
            select(Item).where(
                Item.name == name
            )
        )

        if not existing:
            db.session.add(
                Item(
                    name=name,
                    unit="un",
                    cost=Decimal(cost),
                    category="equipamento",
                )
            )

    if not db.session.scalar(select(User)):
        password = os.environ.get(
            "ADMIN_PASSWORD",
            "",
        )

        if len(password) < 10:
            raise RuntimeError(
                "Configure ADMIN_PASSWORD com pelo "
                "menos 10 caracteres antes de iniciar."
            )

        db.session.add(
            User(
                username=os.environ.get(
                    "ADMIN_USERNAME",
                    "admin",
                ),
                password=generate_password_hash(password),
            )
        )

    db.session.commit()


@app.cli.command("init-db")
def init_command():
    init_db()

    print(
        "Banco inicializado. Cadastros prontos, "
        "sem movimentações fictícias."
    )


def protected(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            if request.path.startswith("/api/"):
                return jsonify(
                    error="Sessão encerrada. Entre novamente."
                ), 401

            return redirect(url_for("login"))

        return function(*args, **kwargs)

    return wrapper


# PROTEÇÕES DAS REQUISIÇÕES

@app.before_request
def csrf_guard():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(32)

    if request.method == "POST":
        token = (
            request.headers.get("X-CSRF-Token")
            or request.form.get("csrf", "")
        )

        if not secrets.compare_digest(
            token,
            session["csrf"],
        ):
            abort(
                400,
                "Atualize a página e tente novamente.",
            )


@app.after_request
def headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store"

    return response


# LOGIN

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        user = db.session.scalar(
            select(User).where(
                User.username
                == request.form.get("username", "")
            )
        )

        if user and check_password_hash(
            user.password,
            request.form.get("password", ""),
        ):
            session.clear()
            session["user"] = user.id
            session["csrf"] = secrets.token_hex(32)

            return redirect(url_for("index"))

        error = "Usuário ou senha incorretos."

    return render_template(
        "login.html",
        error=error,
    )


@app.post("/logout")
def logout():
    session.clear()

    return redirect(url_for("login"))


# PÁGINA PRINCIPAL

@app.get("/")
@protected
def index():
    technicians = db.session.scalars(
        select(Technician).order_by(
            Technician.name
        )
    ).all()

    items = db.session.scalars(
        select(Item).order_by(
            Item.category,
            Item.name,
        )
    ).all()

    return render_template(
        "index.html",
        technicians=technicians,
        items=items,
        today=today().isoformat(),
    )


# PERÍODOS E CÁLCULOS

def interval():
    try:
        start = date.fromisoformat(
            request.args.get(
                "start",
                today().replace(day=1).isoformat(),
            )
        )

        end = date.fromisoformat(
            request.args.get(
                "end",
                today().isoformat(),
            )
        )

        if end < start or (end - start).days > 366:
            raise ValueError()

        return start, end

    except ValueError:
        abort(
            400,
            "Período inválido. Selecione até 367 dias.",
        )


def records(start, end):
    return db.session.scalars(
        select(Movement)
        .where(
            Movement.day.between(start, end)
        )
        .order_by(
            Movement.day,
            Movement.id,
        )
    ).all()


def amount(movement):
    return (
        movement.quantity * movement.cost
    ).quantize(
        Decimal(".01"),
        rounding=ROUND_HALF_UP,
    )


def signed(movement):
    multiplier = (
        -1
        if movement.kind == "devolucao"
        else 1
    )

    return amount(movement) * multiplier


def movement_dict(movement):
    return {
        "id": movement.id,
        "date": movement.day.isoformat(),
        "technician": movement.technician.name,
        "item": movement.item.name,
        "category": movement.item.category,
        "unit": movement.item.unit,
        "quantity": float(movement.quantity),
        "total": float(signed(movement)),
        "kind": movement.kind,
        "note": movement.note,
    }


def summary(start, end):
    rows = records(start, end)

    previous_end = start - timedelta(days=1)

    previous_start = (
        previous_end - (end - start)
    )

    previous = records(
        previous_start,
        previous_end,
    )

    total = sum(
        (signed(m) for m in rows),
        Decimal(0),
    )

    prior = sum(
        (signed(m) for m in previous),
        Decimal(0),
    )

    technicians = {
        technician.name: Decimal(0)
        for technician in db.session.scalars(
            select(Technician).order_by(
                Technician.name
            )
        )
    }

    daily = {}
    items = {}

    for movement in rows:
        value = signed(movement)

        technicians[
            movement.technician.name
        ] += value

        day_key = movement.day.isoformat()

        daily[day_key] = (
            daily.get(day_key, Decimal(0))
            + value
        )

        item_name = movement.item.name

        items[item_name] = (
            items.get(item_name, Decimal(0))
            + value
        )

    withdrawals_total = sum(
        (
            amount(m)
            for m in rows
            if m.kind == "retirada"
        ),
        Decimal(0),
    )

    returns_total = sum(
        (
            amount(m)
            for m in rows
            if m.kind == "devolucao"
        ),
        Decimal(0),
    )

    materials_total = sum(
        (
            signed(m)
            for m in rows
            if m.item.category == "material"
        ),
        Decimal(0),
    )

    equipment_total = sum(
        (
            signed(m)
            for m in rows
            if m.item.category == "equipamento"
        ),
        Decimal(0),
    )

    top_items = sorted(
        items.items(),
        key=lambda item: item[1],
        reverse=True,
    )[:8]

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "previous_start": previous_start.isoformat(),
        "previous_end": previous_end.isoformat(),
        "total": float(total),
        "previous": float(prior),
        "difference": float(prior - total),
        "percent": (
            float((prior - total) / prior * 100)
            if prior > 0
            else None
        ),
        "has_previous": bool(previous),
        "withdrawals": float(withdrawals_total),
        "returns": float(returns_total),
        "materials": float(materials_total),
        "equipment": float(equipment_total),
        "count": len(rows),
        "technicians": {
            name: float(value)
            for name, value in technicians.items()
        },
        "daily": {
            day: float(value)
            for day, value in sorted(daily.items())
        },
        "items": {
            name: float(value)
            for name, value in top_items
        },
        "movements": [
            movement_dict(m)
            for m in reversed(rows)
        ],
    }


# DADOS DA DASHBOARD

@app.get("/api/dashboard")
@protected
def dashboard():
    return jsonify(
        summary(*interval())
    )


# RETIRADAS COM SALDO PARA DEVOLUÇÃO

@app.get("/api/withdrawals")
@protected
def withdrawals():
    result = []

    movements = db.session.scalars(
        select(Movement)
        .where(
            Movement.kind == "retirada"
        )
        .order_by(
            Movement.day.desc()
        )
    )

    for movement in movements:
        returned = db.session.scalar(
            select(
                func.coalesce(
                    func.sum(Movement.quantity),
                    0,
                )
            ).where(
                Movement.original_id == movement.id
            )
        )

        remaining = (
            movement.quantity - returned
        )

        if remaining > 0:
            result.append({
                "id": movement.id,
                "technician": movement.technician.name,
                "item": movement.item.name,
                "day": movement.day.isoformat(),
                "remaining": float(remaining),
                "unit": movement.item.unit,
            })

    return jsonify(result)


# REGISTRAR RETIRADA OU DEVOLUÇÃO

@app.post("/api/movements")
@protected
def create_movement():
    data = request.get_json(silent=True) or {}

    try:
        day = date.fromisoformat(
            data.get("date", "")
        )

        if day > today():
            raise ValueError(
                "A data não pode estar no futuro."
            )

        quantity = Decimal(
            str(
                data.get("quantity", "")
            ).replace(",", ".")
        )

        if (
            not quantity.is_finite()
            or quantity <= 0
            or quantity > 1000000
            or quantity.as_tuple().exponent < -3
        ):
            raise ValueError(
                "Informe uma quantidade positiva "
                "com até 3 casas decimais."
            )

        kind = data.get("kind")

        if kind not in [
            "retirada",
            "devolucao",
        ]:
            raise ValueError("Tipo inválido.")

        original = None

        if kind == "devolucao":
            original = db.session.scalar(
                select(Movement)
                .where(
                    Movement.id
                    == int(
                        data.get("original_id", 0)
                    )
                )
                .with_for_update()
            )

            if (
                not original
                or original.kind != "retirada"
            ):
                raise ValueError(
                    "Selecione a retirada original."
                )

            if day < original.day:
                raise ValueError(
                    "A devolução deve ocorrer "
                    "a partir da retirada."
                )

            returned = db.session.scalar(
                select(
                    func.coalesce(
                        func.sum(Movement.quantity),
                        0,
                    )
                ).where(
                    Movement.original_id == original.id
                )
            )

            remaining = (
                original.quantity - returned
            )

            if quantity > remaining:
                raise ValueError(
                    "A quantidade supera "
                    "o saldo da retirada."
                )

            technician = original.technician
            item = original.item
            cost = original.cost

        else:
            technician = db.session.get(
                Technician,
                int(
                    data.get("technician_id", 0)
                ),
            )

            item = db.session.get(
                Item,
                int(
                    data.get("item_id", 0)
                ),
            )

            if not technician or not item:
                raise ValueError(
                    "Selecione o técnico e o item."
                )

            cost = item.cost

        if (
            item.unit != "m"
            and quantity
            != quantity.to_integral_value()
        ):
            raise ValueError(
                "Este item deve ser lançado "
                "em unidades inteiras."
            )

        note = str(
            data.get("note", "")
        ).strip()

        if len(note) > 300:
            raise ValueError(
                "Observação: máximo de 300 caracteres."
            )

        movement = Movement(
            day=day,
            technician=technician,
            item=item,
            quantity=quantity,
            cost=cost,
            kind=kind,
            original_id=(
                original.id
                if original
                else None
            ),
            note=note,
        )

        db.session.add(movement)
        db.session.commit()

        return jsonify(
            ok=True,
            id=movement.id,
        ), 201

    except (
        ValueError,
        InvalidOperation,
        TypeError,
    ) as error:
        db.session.rollback()

        return jsonify(
            error=str(error) or "Dados inválidos."
        ), 400


# EXPORTAÇÃO CSV

@app.get("/report.csv")
@protected
def csv_report():
    start, end = interval()

    output = io.StringIO()

    writer = csv.writer(
        output,
        delimiter=";",
    )

    writer.writerow([
        "Data",
        "Técnico",
        "Item",
        "Categoria",
        "Tipo",
        "Quantidade",
        "Unidade",
        "Valor líquido (R$)",
        "Observação",
    ])

    def safe(text):
        if text.startswith(
            ("=", "+", "-", "@", "\t", "\r")
        ):
            return "'" + text

        return text

    for movement in records(start, end):
        writer.writerow([
            movement.day.isoformat(),
            safe(movement.technician.name),
            safe(movement.item.name),
            movement.item.category,
            movement.kind,
            str(
                movement.quantity
            ).replace(".", ","),
            movement.item.unit,
            str(
                signed(movement)
            ).replace(".", ","),
            safe(movement.note),
        ])

    content = (
        "\ufeff" + output.getvalue()
    ).encode("utf-8")

    return send_file(
        io.BytesIO(content),
        mimetype="text/csv",
        as_attachment=True,
        download_name=(
            f"matriz_{start}_{end}.csv"
        ),
    )


# EXPORTAÇÃO PDF COM GRÁFICO

@app.get("/report.pdf")
@protected
def pdf_report():
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import HexColor

    start, end = interval()
    data = summary(start, end)

    output = io.BytesIO()

    pdf = canvas.Canvas(
        output,
        pagesize=(842, 595),
    )

    y = 0

    def page():
        nonlocal y

        pdf.setFillColor(
            HexColor("#102a26")
        )

        pdf.rect(
            0, 525, 842, 70,
            fill=1,
            stroke=0,
        )

        pdf.setFillColor(
            HexColor("#edc777")
        )

        pdf.setFont(
            "Helvetica-Bold",
            16,
        )

        pdf.drawString(
            30,
            562,
            "RELATÓRIO DE GASTOS ALMOXARIFADO MATRIZ",
        )

        pdf.setFont(
            "Helvetica",
            10,
        )

        pdf.setFillColor(
            HexColor("#ffffff")
        )

        pdf.drawString(
            30,
            540,
            (
                f"{start:%d/%m/%Y} a {end:%d/%m/%Y}"
                f" | Emissão: {today():%d/%m/%Y}"
            ),
        )

        pdf.setFillColor(
            HexColor("#182724")
        )

        y = 495

    def line(text, bold=False):
        nonlocal y

        if y < 35:
            pdf.showPage()
            page()

        pdf.setFont(
            "Helvetica-Bold"
            if bold
            else "Helvetica",
            10,
        )

        pdf.drawString(30, y, text)

        y -= 18

    page()

    line(
        (
            f"Retiradas: {money(data['withdrawals'])}"
            f" | Devoluções: {money(data['returns'])}"
            f" | Líquido: {money(data['total'])}"
        ),
        True,
    )

    line(
        (
            f"Materiais: {money(data['materials'])}"
            f" | Equipamentos: {money(data['equipment'])}"
        )
    )

    line(
        (
            f"Comparativo: {data['previous_start']}"
            f" a {data['previous_end']}"
            f" | {money(data['previous'])}"
        )
    )

    if data["has_previous"]:
        line(
            "Variação favorável: "
            + money(data["difference"])
        )
    else:
        line(
            "Sem base anterior para comparação."
        )

    line(
        "Redução de gasto não comprova redução de "
        "desperdício. Retirada não confirma consumo final."
    )

    line(
        "CUSTO LÍQUIDO POR TÉCNICO",
        True,
    )

    for name, value in data["technicians"].items():
        line(
            f"{name}: {money(value)}"
        )

    line(
        "MOVIMENTAÇÕES",
        True,
    )

    for movement in records(start, end):
        line(
            f"{movement.day:%d/%m}"
            f" | {movement.technician.name}"
            f" | {movement.item.name}"
            f" | {movement.kind}"
            f" | {movement.quantity.normalize()}"
            f" {movement.item.unit}"
            f" | {money(signed(movement))}"
        )

    pdf.showPage()
    page()

    line(
        "GRÁFICO • CUSTO LÍQUIDO POR TÉCNICO",
        True,
    )

    maximum = max(
        [
            abs(value)
            for value in data["technicians"].values()
        ] + [1]
    )

    y -= 10

    for name, value in data["technicians"].items():
        pdf.setFillColor(
            HexColor("#182724")
        )

        pdf.setFont(
            "Helvetica",
            10,
        )

        pdf.drawString(
            30,
            y,
            name,
        )

        pdf.setFillColor(
            HexColor(
                "#13a880"
                if value >= 0
                else "#db705b"
            )
        )

        pdf.rect(
            150,
            y - 3,
            abs(value) / maximum * 480,
            13,
            fill=1,
            stroke=0,
        )

        pdf.setFillColor(
            HexColor("#182724")
        )

        pdf.drawString(
            650,
            y,
            money(value),
        )

        y -= 32

    pdf.save()
    output.seek(0)

    return send_file(
        output,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=(
            f"relatorio_matriz_{start}_{end}.pdf"
        ),
    )


# VERIFICAÇÃO DO SERVIÇO

@app.get("/health")
def health():
    db.session.execute(
        select(1)
    )

    return {
        "status": "ok",
    }


if __name__ == "__main__":
    app.run(debug=False)
