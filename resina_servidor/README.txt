=============================================
  RESINA PEDIDOS - SERVIDOR LOCAL
  Controle compartilhado de encomendas
=============================================

📦 O QUE ESTE PACOTE FAZ
--------------------------
Este servidor permite que voce e seu socio acessem
os MESMOS pedidos em tempo real pela rede WiFi/cabo.

Um computador fica como "servidor" (roda o programa)
e o outro (e voce tambem) acessa pelo navegador.


⚙️ REQUISITOS
-------------
1. Python 3 instalado no computador que sera o servidor
   (baixe em: https://www.python.org/downloads/)
   ⚠️ Na instalacao, MARQUE a opcao "Add Python to PATH"

2. Ambos os computadores na MESMA rede (mesmo WiFi)


🚀 COMO INSTALAR E RODAR
--------------------------

PASSO 1 - Instalar o Flask (apenas 1 vez)
-----------------------------------------
Abra o "Prompt de Comando" (CMD) ou "PowerShell" no Windows
e digite:

    pip install flask

Aguarde instalar. Pronto, nao precisa repetir.


PASSO 2 - Descompactar e colocar em local adequado
---------------------------------------------------
IMPORTANTE: Nao coloque em "C:\Program Files" nem em pastas
com espacos no nome (isso pode causar erros).

Recomendado: Crie uma pasta direto em C:\
Exemplo: C:\resina_servidor

Ou use: C:\Users\seu_nome\Documentos\resina_servidor


PASSO 3 - Rodar o servidor
----------------------------
1. Abra o CMD na pasta do projeto
2. Digite:

    python app.py

3. O servidor vai iniciar. Voce vera uma mensagem como:

    SERVIDOR RESINA PEDIDOS INICIADO!
    Acesse no seu navegador: http://localhost:5000

4. Deixe esta janela ABERTA. Minimize se quiser.
   Se fechar, o servidor para e ninguem acessa.


PASSO 4 - Acessar no navegador
-------------------------------

NO COMPUTADOR SERVIDOR:
    Abra o navegador e digite:  http://localhost:5000

NO COMPUTADOR DO SOCIO (ou celular na mesma rede):
    1. No computador servidor, descubra o IP local:
       - Abra o CMD e digite:  ipconfig
       - Procure "Endereco IPv4" (ex: 192.168.1.15)
    2. No computador do socio, abra o navegador e digite:
       http://192.168.1.15:5000
       (troque 192.168.1.15 pelo IP que apareceu no seu)

PRONTO! Ambos veem e editam os mesmos pedidos.


💾 BACKUP E RESTAURACAO
-------------------------
Dentro do app, clique em:
  "Exportar Backup"  -> salva um arquivo JSON com todos os pedidos
  "Importar Backup"  -> restaura pedidos de um arquivo JSON

O banco de dados fica no arquivo "pedidos.db" dentro da pasta.
Guarde este arquivo em seguranca (pendrive, nuvem) para backup.


❓ PROBLEMAS COMUNS
-------------------
Q: "pip nao e reconhecido"
R: Python nao foi adicionado ao PATH. Reinstale o Python marcando
   "Add Python to PATH" ou use:  py -m pip install flask

Q: "unable to open database file" ou erro de permissao
R: Mova a pasta para C:\resina_servidor (direto na raiz do C:).
   Nao use pastas dentro de OneDrive, Program Files ou com
   espacos/accentos no nome.

Q: "Endereco nao acessivel no outro PC"
R: Verifique se ambos estao na mesma rede WiFi.
   Verifique se o firewall do Windows esta bloqueando.
   Tente desativar temporariamente o firewall ou adicionar
   uma excecao para Python na porta 5000.

Q: "Quero acessar de fora de casa"
R: Para acesso pela internet e necessario configurar o roteador
   (redirecionamento de porta/port forwarding) ou usar um servico
   como ngrok. Recomendamos manter apenas na rede local por seguranca.


🎨 DICAS
--------
- O servidor pode rodar ate em um computador antigo ou notebook.
- Voce pode acessar pelo celular tambem, desde que esteja no mesmo WiFi.
- Para iniciar automaticamente com o Windows, crie um atalho do app.py
  na pasta "Inicializacao" do Windows.

=============================================
  Suporte: se tiver duvidas, e so perguntar!
=============================================
