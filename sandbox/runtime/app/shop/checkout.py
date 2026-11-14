
def calculate_subtotal(items):
    """Calcule le montant total des produits."""

    if not items:
        raise ValueError("La commande est vide")

    subtotal = 0

    for item in items:
        price = item["price"]
        quantity = item["quantity"]

        if price < 0 or quantity <= 0:
            raise ValueError("Produit invalide")

        subtotal += price * quantity

    return subtotal


def apply_discount(total, discount_percent):
    """Applique une réduction en pourcentage."""

    if total < 0:
        raise ValueError("Montant invalide")

    if not 0 <= discount_percent <= 100:
        raise ValueError("Réduction invalide")

    return total * (1 - discount_percent / 100)


def calculate_shipping(total):
    """Calcule les frais de livraison."""

    if total < 0:
        raise ValueError("Montant invalide")

    if total >= 500:
        return 0

    return 30


def validate_customer(name, email):
    """Vérifie les informations du client."""

    if not name or not name.strip():
        return False

    if "@" not in email:
        return False

    return True


def create_order(items, discount_percent, customer):
    """Crée une commande complète."""

    if not validate_customer(
        customer["name"],
        customer["email"]
    ):
        raise ValueError("Client invalide")

    subtotal = calculate_subtotal(items)

    discounted_total = apply_discount(
        subtotal,
        discount_percent
    )

    shipping = calculate_shipping(discounted_total)

    final_total = discounted_total + shipping

    return {
        "subtotal": subtotal,
        "discounted_total": discounted_total,
        "shipping": shipping,
        "final_total": final_total
    }
