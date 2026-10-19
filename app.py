import os
import secrets
import io
import csv
import json
import hashlib

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
from sqlalchemy import select, func, MetaData, text
from sqlalchemy.exc import IntegrityError

from werkzeug.security import (
    generate_password_hash,
    check_password_hash,
)

from leitor_retiradas import organizar_retiradas


# ==========================================================
# CONFIGURAÇÃO
# ==========================================================

app = Flask(__name__)

database_url = os.environ.get(
    "DATABASE_URL",
    "sqlite:///matriz.db",
).replace(
    "postgres://",
    "postgresql://",
    1,
)

if database_url.startswith("postgresql://"):
    database_url = database_url.replace(
        "postgresql://",
        "postgresql+psycopg2://",
        1,
    )

app.config.update(
    SECRET_KEY=(
        os.environ.get("SECRET_KEY")
        or secrets.token_hex(32)
    ),
    SQLALCHEMY_DATABASE_URI=database_url,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=(
        os.environ.get("COOKIE_SECURE") == "1"
    ),
    MAX_CONTENT_LENGTH=1024 * 1024,
)

REPORT_SCHEMA = (
    "relatorio_matriz"
    if database_url.startswith("postgresql")
    else None
)

db = SQLAlchemy(
    app,
    metadata=MetaData(schema=REPORT_SCHEMA),
)


# ==========================================================
# BANCO DE DADOS
# ==========================================================

class User(db.Model):
    __tablename__ = "user"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

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
    __tablename__ = "technician"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    name = db.Column(
        db.String(80),
        unique=True,
        nullable=False,
    )


class Item(db.Model):
    __tablename__ = "item"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

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
    __tablename__ = "movement"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

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

    # Preço histórico utilizado no lançamento.
    cost = db.Column(
        db.Numeric(18, 9),
        nullable=False,
    )

    kind = db.Column(
        db.String(12),
        nullable=False,
    )

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


class SharedReport(db.Model):
    __tablename__ = "shared_report"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    token = db.Column(
        db.String(64),
        unique=True,
        nullable=False,
    )

    title = db.Column(
        db.String(160),
        nullable=False,
    )

    # Cópia dos dados no momento da geração.
    snapshot = db.Column(
        db.JSON,
        nullable=False,
    )

    active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )


class TextImport(db.Model):
    """
    Guarda as prévias das retiradas por texto.

    O relatório associado identifica que a importação
    já foi confirmada, evitando repetir a gravação.
    """

    __tablename__ = "text_import"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    token = db.Column(
        db.String(64),
        unique=True,
        nullable=False,
    )

    fingerprint = db.Column(
        db.String(64),
        unique=True,
        nullable=False,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )

    payload = db.Column(
        db.JSON,
        nullable=False,
    )

    expires_at = db.Column(
        db.DateTime,
        nullable=False,
    )

    report_id = db.Column(
        db.Integer,
        db.ForeignKey("shared_report.id"),
    )


# ==========================================================
# CADASTROS INICIAIS
# ==========================================================

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
    (
        "Abraçadeira",
        "un",
        str(Decimal("20.80") / 100),
    ),
    ("UPC", "un", "6.10"),
    ("Cunha", "un", "2.94"),
    ("Bucha de acabamento", "un", "1.50"),
    ("Fita isolante", "rolo", "5.57"),
    ("Pino Jack RJ45", "un", "0.24"),
    ("Miguelão", "un", "0.31"),
    (
        "Cabo de rede",
        "m",
        str(Decimal("175.30") / 305),
    ),
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


# ==========================================================
# FUNÇÕES AUXILIARES
# ==========================================================

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
    if REPORT_SCHEMA:
        with db.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE SCHEMA IF NOT EXISTS relatorio_matriz"
                )
            )

    # Cria também a tabela text_import.
    # Não apaga os registros existentes.
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
                password=generate_password_hash(
                    password
                ),
            )
        )

    db.session.commit()


@app.cli.command("init-db")
def init_command():
    init_db()

    print(
        "Banco do relatório inicializado. "
        "Cadastros prontos, sem movimentações fictícias."
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


# ==========================================================
# PROTEÇÕES
# ==========================================================

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
    response.headers["Referrer-Policy"] = "no-referrer"

    if request.path.startswith("/r/"):
        response.headers["X-Robots-Tag"] = (
            "noindex, nofollow, noarchive"
        )

    return response


# ==========================================================
# LOGIN
# ==========================================================

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


# ==========================================================
# PÁGINA PRINCIPAL
# ==========================================================

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


# ==========================================================
# PERÍODOS E CÁLCULOS
# ==========================================================

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


def summary(
    start,
    end,
    previous_start=None,
    previous_end=None,
):
    rows = records(start, end)

    if previous_end is None:
        previous_end = start - timedelta(days=1)

    if previous_start is None:
        previous_start = previous_end - (end - start)

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


# ==========================================================
# DADOS DA DASHBOARD
# ==========================================================

@app.get("/api/dashboard")
@protected
def dashboard():
    return jsonify(
        summary(*interval())
    )


# ==========================================================
# RETIRADAS COM SALDO PARA DEVOLUÇÃO
# ==========================================================

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

        remaining = movement.quantity - returned

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


# ==========================================================
# MOVIMENTAÇÃO MANUAL
# ==========================================================

@app.post("/api/movements")
@protected
def create_movement():
    data = request.get_json(silent=True) or {}

    if not isinstance(data, dict):
        return jsonify(
            error="Dados inválidos."
        ), 400

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
                    == int(data.get("original_id", 0))
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

            remaining = original.quantity - returned

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
                int(data.get("technician_id", 0)),
            )

            item = db.session.get(
                Item,
                int(data.get("item_id", 0)),
            )

            if not technician or not item:
                raise ValueError(
                    "Selecione o técnico e o item."
                )

            cost = item.cost

        if (
            item.unit != "m"
            and quantity != quantity.to_integral_value()
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


# ==========================================================
# EXPORTAÇÃO CSV
# ==========================================================

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

    def safe(value):
        if value.startswith(
            ("=", "+", "-", "@", "\t", "\r")
        ):
            return "'" + value

        return value

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
        download_name=f"matriz_{start}_{end}.csv",
    )


# ==========================================================
# PDF
# ==========================================================

def build_pdf(data, issued_at=None):
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import HexColor

    start = date.fromisoformat(data["start"])
    end = date.fromisoformat(data["end"])

    issued_at = (
        issued_at
        or today().strftime("%d/%m/%Y")
    )

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
            0,
            525,
            842,
            70,
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
                f" | Emissão: {issued_at}"
            ),
        )

        pdf.setFillColor(
            HexColor("#182724")
        )

        y = 495

    def line(value, bold=False):
        nonlocal y

        if y < 35:
            pdf.showPage()
            page()

        pdf.setFont(
            "Helvetica-Bold" if bold else "Helvetica",
            10,
        )

        pdf.drawString(
            30,
            y,
            value,
        )

        y -= 18

    page()

    if data.get("title"):
        line(
            data["title"],
            True,
        )

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

    if data.get("comparison_note"):
        line(data["comparison_note"])

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

    for movement in reversed(data["movements"]):
        day = date.fromisoformat(
            movement["date"]
        )

        line(
            f"{day:%d/%m}"
            f" | {movement['technician']}"
            f" | {movement['item']}"
            f" | {movement['kind']}"
            f" | {movement['quantity']:g}"
            f" {movement['unit']}"
            f" | {money(movement['total'])}"
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


@app.get("/report.pdf")
@protected
def pdf_report():
    return build_pdf(
        summary(*interval())
    )


# ==========================================================
# PERÍODOS DOS RELATÓRIOS COMPARTILHADOS
# ==========================================================

def shared_period(payload):
    current = today()

    mode = payload.get(
        "mode",
        "week",
    )

    previous_start = None
    previous_end = None
    partial = False

    if mode == "week":
        anchor = date.fromisoformat(
            payload.get("anchor")
            or current.isoformat()
        )

        start = anchor - timedelta(
            days=anchor.weekday()
        )

        friday = start + timedelta(days=4)

        if start > current:
            raise ValueError(
                "Selecione uma semana que já começou."
            )

        end = min(friday, current)
        partial = end < friday

        previous_start = start - timedelta(days=7)
        previous_end = end - timedelta(days=7)

        title = (
            "Relatório semanal — segunda a sexta"
        )

        if partial:
            title += " (parcial)"

    elif mode == "last30":
        end = current
        start = end - timedelta(days=29)

        title = (
            "Relatório dos últimos 30 dias"
        )

    elif mode == "month":
        default = (
            current.replace(day=1)
            - timedelta(days=1)
        )

        month = (
            payload.get("month")
            or default.strftime("%Y-%m")
        )

        start = date.fromisoformat(
            month + "-01"
        )

        if start >= current.replace(day=1):
            raise ValueError(
                "Selecione um mês anterior ao atual."
            )

        next_month = (
            start.replace(day=28)
            + timedelta(days=4)
        ).replace(day=1)

        end = next_month - timedelta(days=1)

        previous_end = (
            start - timedelta(days=1)
        )

        previous_start = (
            previous_end.replace(day=1)
        )

        title = (
            "Relatório mensal — "
            + start.strftime("%m/%Y")
        )

    else:
        raise ValueError(
            "Escolha week, last30 ou month."
        )

    return (
        title,
        start,
        end,
        previous_start,
        previous_end,
        partial,
    )


# ==========================================================
# LINKS DOS RELATÓRIOS
# ==========================================================

def report_url(report):
    path = url_for(
        "shared_report",
        token=report.token,
    )

    base = (
        os.environ.get("RENDER_EXTERNAL_URL")
        or request.url_root
    )

    return base.rstrip("/") + path


def report_info(report):
    return {
        "id": report.id,
        "title": report.title,
        "active": report.active,

        "created_at": report.snapshot["generated_at"],

        "start": report.snapshot["start"],
        "end": report.snapshot["end"],
        "total": report.snapshot["total"],

        "url": (
            report_url(report)
            if report.active
            else None
        ),
    }


@app.post("/api/reports")
@protected
def create_shared_report():
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify(
            error="Dados inválidos."
        ), 400

    try:
        (
            title,
            start,
            end,
            previous_start,
            previous_end,
            partial,
        ) = shared_period(payload)

        snapshot = summary(
            start,
            end,
            previous_start,
            previous_end,
        )

        generated = datetime.now(
            ZoneInfo("America/Sao_Paulo")
        )

        snapshot["generated_at"] = (
            generated.isoformat(timespec="seconds")
        )

        snapshot["issued_at"] = (
            generated.strftime("%d/%m/%Y %H:%M")
        )

        snapshot["partial"] = partial

        snapshot["mode"] = payload.get(
            "mode",
            "week",
        )

        snapshot["title"] = title

        if snapshot["mode"] == "week":
            snapshot["comparison_note"] = (
                "Mesmos dias úteis da semana anterior."
            )

        elif snapshot["mode"] == "month":
            snapshot["comparison_note"] = (
                "Mês calendário anterior; "
                "a quantidade de dias pode variar."
            )

        else:
            snapshot["comparison_note"] = (
                "30 dias imediatamente anteriores."
            )

        report = SharedReport(
            token=secrets.token_urlsafe(32),
            title=title,
            snapshot=snapshot,
        )

        db.session.add(report)
        db.session.commit()

        return jsonify(
            ok=True,
            **report_info(report),
        ), 201

    except (
        ValueError,
        TypeError,
        OverflowError,
    ):
        db.session.rollback()

        return jsonify(
            error=(
                "Período inválido. Escolha uma "
                "semana já iniciada ou um mês fechado."
            )
        ), 400


@app.get("/api/reports")
@protected
def list_shared_reports():
    reports = db.session.scalars(
        select(SharedReport).order_by(
            SharedReport.id.desc()
        )
    ).all()

    return jsonify([
        report_info(report)
        for report in reports
    ])


@app.post("/api/reports/<int:report_id>/revoke")
@protected
def revoke_shared_report(report_id):
    report = db.session.get(
        SharedReport,
        report_id,
    )

    if not report:
        return jsonify(
            error="Relatório não encontrado."
        ), 404

    report.active = False

    db.session.commit()

    return jsonify(ok=True)


def active_report(token):
    report = db.session.scalar(
        select(SharedReport).where(
            SharedReport.token == token,
            SharedReport.active.is_(True),
        )
    )

    if not report:
        abort(
            404,
            "Este relatório não existe "
            "ou o link foi desativado.",
        )

    return report


@app.get("/r/<token>")
def shared_report(token):
    report = active_report(token)

    return render_template(
        "relatorio_compartilhado.html",
        report=report,
        data=report.snapshot,
    )


@app.get("/r/<token>/pdf")
def shared_report_pdf(token):
    report = active_report(token)

    return build_pdf(
        report.snapshot,
        issued_at=report.snapshot["issued_at"],
    )


# ==========================================================
# IMPORTAÇÃO POR TEXTO — PRÉVIA
# ==========================================================

@app.post("/api/text-import/preview")
@protected
def text_import_preview():
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify(
            error="Dados inválidos."
        ), 400

    try:
        if not isinstance(
            payload.get("text"),
            str,
        ):
            raise ValueError(
                "Escreva as retiradas no campo de texto."
            )

        start = date.fromisoformat(
            payload.get("start", "")
        )

        end = date.fromisoformat(
            payload.get("end", "")
        )

        if (
            end < start
            or (end - start).days > 366
            or end > today()
        ):
            raise ValueError(
                "Escolha um período de até 367 dias, "
                "sem datas futuras."
            )

        technicians = [
            {
                "id": technician.id,
                "name": technician.name,
            }

            for technician in db.session.scalars(
                select(Technician)
            )
        ]

        items = [
            {
                "id": item.id,
                "name": item.name,
                "unit": item.unit,
                "category": item.category,
                "cost": str(item.cost),
            }

            for item in db.session.scalars(
                select(Item)
            )
        ]

        result = organizar_retiradas(
            payload["text"],
            technicians,
            items,
            start.isoformat(),
            end.isoformat(),

            data_padrao=(
                payload.get("default_date")
                or None
            ),

            hoje=today(),
        )

        total = Decimal(0)
        totals = {}

        for row in result["rows"]:
            value = (
                Decimal(row["quantity"])
                * Decimal(row["cost"])
            ).quantize(
                Decimal(".01"),
                rounding=ROUND_HALF_UP,
            )

            row["total"] = str(value)

            total += value

            name = row["technician"]

            totals[name] = (
                totals.get(name, Decimal(0))
                + value
            )

        result["total"] = str(total)

        result["technicians"] = {
            name: str(value)
            for name, value in totals.items()
        }

        result["start"] = start.isoformat()
        result["end"] = end.isoformat()

        result["token"] = None
        result["existing_report"] = None
        result["warnings"] = []

        # Itens reconhecidos podem aparecer na prévia,
        # mas nenhuma confirmação é liberada com pendências.
        if not result["can_confirm"]:
            return jsonify(result)

        # Identificação do conjunto de retiradas.
        # Detecta também o mesmo conteúdo em outra ordem.
        grouped = {}

        for row in result["rows"]:
            key = (
                row["date"],
                row["technician_id"],
                row["item_id"],
            )

            grouped[key] = (
                grouped.get(key, Decimal(0))
                + Decimal(row["quantity"])
            )

        canonical = [
            (
                list(key),
                format(
                    quantity.normalize(),
                    "f",
                ),
            )

            for key, quantity in sorted(
                grouped.items()
            )
        ]

        fingerprint = hashlib.sha256(
            json.dumps(
                canonical,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

        draft = db.session.scalar(
            select(TextImport)
            .where(
                TextImport.fingerprint == fingerprint
            )
            .with_for_update()
        )

        # Importação já confirmada:
        # devolve o relatório anterior e não lança novamente.
        if draft and draft.report_id:
            result["can_confirm"] = False

            result["warnings"].append(
                "Estas retiradas já foram importadas. "
                "Nenhuma foi lançada novamente."
            )

            report = db.session.get(
                SharedReport,
                draft.report_id,
            )

            if report:
                result["existing_report"] = (
                    report_info(report)
                )

            return jsonify(result)

        if (
            draft
            and draft.user_id != session["user"]
        ):
            result["can_confirm"] = False

            result["issues"].append({
                "message": (
                    "Estas retiradas já possuem uma prévia "
                    "em outra conta. Confira o histórico."
                ),
                "excerpt": "",
            })

            return jsonify(result)

        if not draft:
            draft = TextImport(
                token=secrets.token_urlsafe(32),
                fingerprint=fingerprint,
                user_id=session["user"],
            )

            db.session.add(draft)

        # Cada nova prévia invalida o token anterior.
        draft.token = secrets.token_urlsafe(32)

        # Dados de confirmação ficam no servidor.
        # O navegador não escolhe os preços ao confirmar.
        draft.payload = {
            "rows": result["rows"],
            "start": result["start"],
            "end": result["end"],
        }

        draft.expires_at = (
            datetime.utcnow()
            + timedelta(minutes=30)
        )

        # Verifica possíveis coincidências com o histórico.
        duplicate = False

        for row in result["rows"]:
            existing = db.session.scalar(
                select(Movement.id)
                .where(
                    Movement.day == date.fromisoformat(
                        row["date"]
                    ),

                    Movement.technician_id
                    == row["technician_id"],

                    Movement.item_id
                    == row["item_id"],

                    Movement.quantity
                    == Decimal(row["quantity"]),

                    Movement.kind == "retirada",
                )
                .limit(1)
            )

            if existing is not None:
                duplicate = True
                break

        draft.payload = {
            **draft.payload,
            "possible_duplicates": duplicate,
        }

        result["requires_duplicate_ack"] = duplicate

        if duplicate:
            result["warnings"].append(
                "Há retiradas iguais no histórico. "
                "Confira se são novas antes de confirmar."
            )

        db.session.commit()

        result["token"] = draft.token
        result["expires_in_minutes"] = 30

        return jsonify(result)

    except IntegrityError:
        db.session.rollback()

        return jsonify(
            error=(
                "Esta prévia foi criada em outra requisição. "
                "Clique em Organizar novamente."
            )
        ), 409

    except (
        ValueError,
        TypeError,
        InvalidOperation,
        OverflowError,
    ) as error:
        db.session.rollback()

        return jsonify(
            error=(
                str(error)
                or "Confira o texto e as datas."
            )
        ), 400


# ==========================================================
# IMPORTAÇÃO POR TEXTO — CONFIRMAR E GERAR LINK
# ==========================================================

@app.post("/api/text-import/confirm")
@protected
def text_import_confirm():
    payload = request.get_json(silent=True)

    if (
        not isinstance(payload, dict)
        or payload.get("confirm") is not True
    ):
        return jsonify(
            error=(
                "Confira a prévia e confirme "
                "antes de salvar."
            )
        ), 400

    token = payload.get("token")

    if (
        not isinstance(token, str)
        or not token
        or len(token) > 64
    ):
        return jsonify(
            error=(
                "Prévia inválida. "
                "Organize o texto novamente."
            )
        ), 400

    try:
        # No PostgreSQL, bloqueia a prévia durante a gravação
        # para evitar duas confirmações simultâneas.
        draft = db.session.scalar(
            select(TextImport)
            .where(
                TextImport.token == token,
                TextImport.user_id == session["user"],
            )
            .with_for_update()
        )

        if not draft:
            return jsonify(
                error=(
                    "Prévia não encontrada nesta conta."
                )
            ), 404

        # Repetir a confirmação retorna o mesmo relatório.
        if draft.report_id:
            report = db.session.get(
                SharedReport,
                draft.report_id,
            )

            return jsonify(
                ok=True,
                reused=True,
                **report_info(report),
            )

        if draft.expires_at < datetime.utcnow():
            return jsonify(
                error=(
                    "A prévia expirou. "
                    "Organize o texto novamente."
                )
            ), 409

        if (
            draft.payload.get("possible_duplicates")
            and payload.get("ack_duplicates") is not True
        ):
            return jsonify(
                error=(
                    "Confira as possíveis duplicidades "
                    "e marque a confirmação."
                )
            ), 409

        rows = draft.payload["rows"]

        if not rows or len(rows) > 500:
            raise ValueError(
                "Prévia inválida. "
                "Organize o texto novamente."
            )

        for row in rows:
            item = db.session.get(
                Item,
                row["item_id"],
            )

            technician = db.session.get(
                Technician,
                row["technician_id"],
            )

            if not item or not technician:
                raise ValueError(
                    "O catálogo mudou. "
                    "Organize o texto novamente."
                )

            if (
                Decimal(str(item.cost))
                != Decimal(row["cost"])
                or item.unit != row["unit"]
            ):
                raise ValueError(
                    "Um custo ou unidade mudou. "
                    "Organize o texto novamente "
                    "para conferir os valores."
                )

            day = date.fromisoformat(
                row["date"]
            )

            quantity = Decimal(
                row["quantity"]
            )

            if (
                day > today()
                or not quantity.is_finite()
                or quantity <= 0
                or quantity > 1000000
            ):
                raise ValueError(
                    "Data ou quantidade inválida na prévia."
                )

            if (
                item.unit != "m"
                and quantity
                != quantity.to_integral_value()
            ):
                raise ValueError(
                    "Este item exige unidades inteiras."
                )

            db.session.add(
                Movement(
                    day=day,
                    technician=technician,
                    item=item,
                    quantity=quantity,
                    cost=item.cost,
                    kind="retirada",

                    note=(
                        "Retirada importada por texto e "
                        "conferida antes da confirmação."
                    ),
                )
            )

        # Disponibiliza as novas retiradas para o cálculo,
        # ainda sem confirmar a transação.
        db.session.flush()

        start = date.fromisoformat(
            draft.payload["start"]
        )

        end = date.fromisoformat(
            draft.payload["end"]
        )

        # O fechamento reúne todas as movimentações do período,
        # incluindo as que já existiam e as recém-importadas.
        snapshot = summary(
            start,
            end,
        )

        generated = datetime.now(
            ZoneInfo("America/Sao_Paulo")
        )

        title = (
            f"Relatório de retiradas — "
            f"{start:%d/%m/%Y} a {end:%d/%m/%Y}"
        )

        snapshot.update(
            title=title,
            mode="text",
            partial=False,

            generated_at=generated.isoformat(
                timespec="seconds"
            ),

            issued_at=generated.strftime(
                "%d/%m/%Y %H:%M"
            ),

            comparison_note=(
                "Período imediatamente anterior "
                "de igual duração."
            ),

            imported_count=len(rows),
        )

        report = SharedReport(
            token=secrets.token_urlsafe(32),
            title=title,
            snapshot=snapshot,
        )

        db.session.add(report)
        db.session.flush()

        draft.report_id = report.id

        # Movimentações e relatório são gravados juntos.
        # Se houver erro antes do commit, tudo é revertido.
        db.session.commit()

        return jsonify(
            ok=True,
            reused=False,
            imported_count=len(rows),
            **report_info(report),
        ), 201

    except (
        ValueError,
        TypeError,
        InvalidOperation,
        OverflowError,
    ) as error:
        db.session.rollback()

        return jsonify(
            error=(
                str(error)
                or "Não foi possível confirmar a prévia."
            )
        ), 400


# ==========================================================
# VERIFICAÇÃO DO SERVIÇO
# ==========================================================

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
