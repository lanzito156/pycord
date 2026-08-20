# PyCord

Um protótipo de plataforma estilo Discord feito com Python + Flask + Socket.IO + WebRTC.

## Recursos
- Cadastro e login locais, sem Google.
- Senhas armazenadas com hash.
- Criação de grupos.
- Adição de amigos por nome de usuário.
- Chat em tempo real.
- Compartilhamento de tela via WebRTC no navegador.

## Rodar no Windows
1. Instale Python 3.11+.
2. Abra o terminal nesta pasta.
3. Crie um ambiente virtual:
   `python -m venv .venv`
4. Ative:
   `.venv\Scripts\activate`
5. Instale:
   `pip install -r requirements.txt`
6. Execute:
   `python app.py`
7. Abra `http://127.0.0.1:5000`.

## Importante para publicar na internet
Para produção, troque SECRET_KEY, use HTTPS/WSS, banco PostgreSQL, autenticação mais robusta, controle de permissões, rate limiting e um servidor TURN para WebRTC. O compartilhamento de tela usa a permissão nativa do navegador e funciona melhor em HTTPS (localhost é exceção).
