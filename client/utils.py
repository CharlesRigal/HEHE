import math
import random

from client.core.settings import WIDTH, HEIGHT


def get_random_location_away_from_screen_circle(center_x=None, center_y=None, min_radius=None):
    """
    Alternative: génère une position sur un cercle autour de l'écran

    Args:
        center_x, center_y: Centre du cercle (par défaut centre de l'écran)
        min_radius: Rayon minimum (par défaut diagonal de l'écran + marge)

    Returns:
        tuple: (x, y) position sur le cercle
    """
    if center_x is None:
        center_x = WIDTH / 2
    if center_y is None:
        center_y = HEIGHT / 2
    if min_radius is None:
        # Calcul du rayon minimum pour être sûr d'être hors écran
        diagonal = math.sqrt(WIDTH ** 2 + HEIGHT ** 2)
        min_radius = diagonal / 2 + 100

    # Angle aléatoire
    angle = random.uniform(0, 2 * math.pi)

    # Rayon aléatoire (entre min_radius et min_radius + 200)
    radius = random.uniform(min_radius, min_radius + 200)

    # Calcul des coordonnées
    x = center_x + radius * math.cos(angle)
    y = center_y + radius * math.sin(angle)

    return (x, y)