from tools.llm_client import ask_llm

prompt = """
Tu es un assistant spécialisé en tests logiciels Python.

Écris une fonction Python appelée calculate_total(items)
qui calcule le prix total d'un panier.

Génère ensuite deux tests unitaires avec pytest.

Retourne uniquement le code Python.
"""

print("Connexion au modèle Qwen2.5-Coder...")

response = ask_llm(prompt)

print("\nRéponse du modèle :\n")
print(response)