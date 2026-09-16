import os
print("Testando permissao de escrita...")
path = os.path.dirname(os.path.abspath(__file__))
print("Pasta:", path)
try:
    with open(os.path.join(path, "teste.txt"), "w") as f:
        f.write("ok")
    print("✅ Permissao OK! Pode criar arquivos aqui.")
    os.remove(os.path.join(path, "teste.txt"))
except Exception as e:
    print("❌ ERRO:", e)
input("Pressione ENTER para sair...")
