from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
import requests, re, unicodedata
from bs4 import BeautifulSoup
import validators

app = Flask(__name__)
app.secret_key = 'chave-secreta'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///focusia.db'

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# MODELOS
class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    senha = db.Column(db.String(200), nullable=False)
    idioma = db.Column(db.String(50), nullable=True)
    explicacoes = db.relationship('Explicacao', backref='usuario', lazy=True)

class Explicacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    tema = db.Column(db.String(100))
    texto_ia = db.Column(db.Text)
    imagem_url = db.Column(db.String(300))
    curtidas = db.Column(db.Integer, default=0)
    descurtidas = db.Column(db.Integer, default=0)
    salvo = db.Column(db.Boolean, default=False)

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

@app.before_request
def criar_tabelas():
    db.create_all()

# Funções IA
COHERE_API_KEY = "KHlNULhkZLyr8RcAYxZJSDIChGXxylRy076Ii6wu"

def limpar_texto(texto):
    texto = re.sub(r'\[[^\]]*\d+[^\]]*\]', '', texto)
    texto = ''.join(c for c in texto if unicodedata.category(c)[0] != 'C' and c.isprintable())
    texto = re.sub(r"[^a-zA-ZÀ-ÿçÇ,.\s]", "", texto)
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto

def gerar_com_cohere(texto, idiomauser):
    headers = {'Authorization': f'Bearer {COHERE_API_KEY}', 'Content-Type': 'application/json'}
    prompt = f"Explique com clareza e objetividade como se fosse para alunos de Harvard. Traduza o conteúdo a seguir para o idioma: {idiomauser}.\n\n{texto}"
    payload = {'model': 'command-r-plus', 'prompt': prompt, 'max_tokens': 4000, 'temperature': 0.4}
    r = requests.post("https://api.cohere.ai/v1/generate", headers=headers, json=payload)
    return r.json()['generations'][0]['text'].strip() if r.status_code == 200 else "Erro na IA"

def gerar_tema_com_cohere(texto):
    headers = {'Authorization': f'Bearer {COHERE_API_KEY}', 'Content-Type': 'application/json'}
    prompt = "Diga apenas uma palavra que defina o tema central:\n\n" + texto
    payload = {'model': 'command-r-plus', 'prompt': prompt, 'max_tokens': 5, 'temperature': 0}
    r = requests.post("https://api.cohere.ai/v1/generate", headers=headers, json=payload)
    return re.sub(r'[^a-zA-ZÀ-ÿçÇ\s]', '', r.json()['generations'][0]['text']).strip() if r.status_code == 200 else ""

def buscar_imagem_tema(tema):
    headers = {'Authorization': f'Bearer {COHERE_API_KEY}', 'Content-Type': 'application/json'}
    prompt = f"Retorne apenas um link de imagem relacionada ao tema '{tema}'."
    payload = {'model': 'command-r-plus', 'prompt': prompt, 'max_tokens': 50, 'temperature': 0.3}
    r = requests.post("https://api.cohere.ai/v1/generate", headers=headers, json=payload)
    links = re.findall(r'(https?://\S+\.(?:png|jpg|jpeg))', r.text) if r.status_code == 200 else []
    return links[0] if links else None

# ROTAS
@app.route('/')
def home():
    return redirect(url_for('index'))

@app.route('/index', methods=['GET', 'POST'])
@login_required
def index():
    texto_extraido = ""
    explicacao_ia = ""
    tema = ""
    imagem_tema = None

    idiomauser = current_user.idioma or "pt-BR"

    if request.method == "POST":
        entrada = request.form.get("url")
        tipo = request.form.get("tipo")

        try:
            if tipo == "link":
                if entrada and validators.url(entrada):
                    resposta = requests.get(entrada, headers={"User-Agent": "Mozilla/5.0"})
                    if resposta.status_code == 200:
                        html = resposta.text
                        soup = BeautifulSoup(html, "html.parser")
                        for tag in soup(["script", "style", "header", "footer", "nav", "aside"]):
                            tag.decompose()
                        paragrafos = soup.find_all("p")
                        texto = "\n\n".join(p.get_text(strip=True) for p in paragrafos)

                        texto_limpo = limpar_texto(texto)
                        if texto_limpo:
                            explicacao_ia = gerar_com_cohere(texto_limpo, idiomauser)
                            tema = gerar_tema_com_cohere(texto_limpo)
                            imagem_tema = buscar_imagem_tema(tema) if tema else None
                else:
                    texto_extraido = "URL inválida ou não informada."
            elif tipo == "tema":
                tema = entrada
                if tema:
                    prompt_tema = f"Explique claramente e objetivamente sobre o tema '{tema}' no idioma {idiomauser}."
                    explicacao_ia = gerar_com_cohere(prompt_tema, idiomauser)
                    imagem_tema = buscar_imagem_tema(tema)
            else:
                texto_extraido = "Por favor, selecione se o conteúdo é Link ou Tema."
        except Exception as e:
            texto_extraido = f"Erro: {str(e)}"

    return render_template("index.html", resultado=texto_extraido, ia=explicacao_ia, tema=tema, imagem_tema=imagem_tema)

@app.route("/salvar_explicacao", methods=["POST"])
@login_required
def salvar_explicacao():
    tema = request.form.get("tema")
    texto = request.form.get("ia")
    imagem = request.form.get("imagem")
    nova = Explicacao(usuario_id=current_user.id, tema=tema, texto_ia=texto, imagem_url=imagem, salvo=True)
    db.session.add(nova)
    db.session.commit()
    flash("Explicação salva com sucesso!")
    return redirect(url_for("index"))

@app.route("/curtir/<int:explicacao_id>", methods=["POST"])
@login_required
def curtir(explicacao_id):
    explicacao = Explicacao.query.get_or_404(explicacao_id)
    explicacao.curtidas += 1
    db.session.commit()
    return redirect(url_for("perfil"))

@app.route("/descurtir/<int:explicacao_id>", methods=["POST"])
@login_required
def descurtir(explicacao_id):
    explicacao = Explicacao.query.get_or_404(explicacao_id)
    explicacao.descurtidas += 1
    db.session.commit()
    return redirect(url_for("perfil"))

@app.route('/perfil', methods=["GET", "POST"])
@login_required
def perfil():
    if request.method == "POST":
        novo_idioma = request.form.get("idioma")
        if novo_idioma:
            current_user.idioma = novo_idioma
            db.session.commit()
            flash("Idioma atualizado com sucesso.")
    return render_template('perfil.html')

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form['email']
        senha = request.form['senha']
        user = Usuario.query.filter_by(email=email).first()
        if user and check_password_hash(user.senha, senha):
            login_user(user)
            return redirect(url_for('index'))
        flash("Credenciais inválidas")
    return render_template("login.html")
@app.route('/inicio')
def inicio():
    return render_template('inicio.html')
@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        nome = request.form['nome']
        email = request.form['email']
        senha = request.form['senha']
        senha_hash = generate_password_hash(senha)
        novo = Usuario(nome=nome, email=email, senha=senha_hash)
        db.session.add(novo)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template("registro.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

if __name__ == '__main__':
    app.run(debug=True)
