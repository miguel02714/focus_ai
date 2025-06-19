from flask import Flask, request, render_template
import requests
from bs4 import BeautifulSoup
import re
import unicodedata

app = Flask(__name__)

COHERE_API_KEY = "KHlNULhkZLyr8RcAYxZJSDIChGXxylRy076Ii6wu"  # Substitua pela sua chave

def limpar_texto(texto):
    """Remove emojis, símbolos, letras estranhas e deixa o texto menor, mantendo apenas letras, acentos, vírgulas, pontos e espaços. Também remove [1] até [999] e qualquer conjunto dentro de colchetes com número."""
    texto = re.sub(r'\[[^\]]*\d+[^\]]*\]', '', texto)  # Remove [n] ou qualquer [123 texto]
    texto = ''.join(c for c in texto if unicodedata.category(c)[0] != 'C' and c.isprintable())
    texto = re.sub(r"[^a-zA-ZÀ-ÿçÇ,.\s]", "", texto)
    texto = re.sub(r'\s+', ' ', texto)
    return texto

def gerar_com_cohere(texto):
    """Gera explicação detalhada do conteúdo via Cohere."""
    headers = {
        'Authorization': f'Bearer {COHERE_API_KEY}',
        'Content-Type': 'application/json',
    }

    prompt = (
        "Explique o conteúdo a seguir com a máxima clareza, profundidade e linguagem formal. "
        "Corrija espaçamentos faltantes nas palavras (exemplo: 'Alagoasé' virar 'Alagoas é'). "
        "Seja direto e conciso, como uma explicação acadêmica para alunos da Universidade de Harvard. "
        "Texto:\n\n" + texto
    )

    payload = {
        'model': 'command-r-plus',
        'prompt': prompt,
        'max_tokens': 300,
        'temperature': 0.4
    }

    response = requests.post("https://api.cohere.ai/v1/generate", headers=headers, json=payload)

    if response.status_code == 200:
        return response.json()['generations'][0]['text']
    else:
        return f"Erro ao chamar Cohere (Explicação): {response.status_code} - {response.text}"

def gerar_tema_com_cohere(texto):
    """Pede ao Cohere um tema único (uma palavra) para o texto."""
    headers = {
        'Authorization': f'Bearer {COHERE_API_KEY}',
        'Content-Type': 'application/json',
    }

    prompt = (
        "Analise o conteúdo a seguir e responda com apenas UMA PALAVRA clara e objetiva que defina o tema central do texto. "
        "Não inclua frases. Apenas uma palavra, exemplo: 'Alagoas', 'História', 'Biologia', 'Tecnologia'. "
        "Texto:\n\n" + texto
    )

    payload = {
        'model': 'command-r-plus',
        'prompt': prompt,
        'max_tokens': 5,
        'temperature': 0
    }

    response = requests.post("https://api.cohere.ai/v1/generate", headers=headers, json=payload)

    if response.status_code == 200:
        tema = response.json()['generations'][0]['text']
        # Limpar possíveis espaços ou pontuações extras
        tema = re.sub(r'[^a-zA-ZÀ-ÿçÇ\s]', '', tema)
        return tema
    else:
        return f"Erro ao chamar Cohere (Tema): {response.status_code} - {response.text}"

@app.route("/", methods=["GET", "POST"])
def index():
    texto_extraido = ""
    explicacao_ia = ""
    tema = ""

    if request.method == "POST":
        url = request.form.get("url")

        try:
            resposta = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
            if resposta.status_code == 200:
                html = resposta.text
                soup = BeautifulSoup(html, "html.parser")

                for tag in soup(["script", "style", "header", "footer", "nav", "aside"]):
                    tag.decompose()

                paragrafos = soup.find_all("p")
                texto_extraido = "\n\n".join(p.get_text(strip=True) for p in paragrafos)
                texto_limpo = limpar_texto(texto_extraido)

                if texto_limpo:
                    explicacao_ia = gerar_com_cohere(texto_limpo)
                    tema = gerar_tema_com_cohere(texto_limpo)
                else:
                    explicacao_ia = "Nenhum texto válido encontrado para explicar."

            else:
                texto_extraido = f"Erro ao acessar a página. Código: {resposta.status_code}"

        except Exception as e:
            texto_extraido = f"Erro: {str(e)}"

    return render_template("index.html", resultado=texto_extraido, ia=explicacao_ia, tema=tema)

if __name__ == "__main__":
    app.run(debug=True)
