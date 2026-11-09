"""Formules pures du chiffrage (sans base de données) : testées seules dans tests/test_formules.py."""

from lsi_inspection.constants import MOINS_ELEVE, MOYENNE


def taux(marge, prix):
	"""Marge en % du prix ; 0 si le prix est nul."""
	return marge / prix * 100 if prix else 0


def prix_conseille(cout_unitaire, marge_cible):
	"""Prix pour atteindre la marge cible (% du prix) : coût ÷ (1 − marge) ; 0 sans marge cible exploitable ou sans coût."""
	if not marge_cible or marge_cible >= 100 or not cout_unitaire:
		return 0
	return cout_unitaire / (1 - marge_cible / 100)


def appliquer_regle(valeurs, regle):
	"""Plus élevé (défaut), moins élevé ou moyenne d'une liste de coûts ; None si la liste est vide."""
	if not valeurs:
		return None
	if regle == MOINS_ELEVE:
		return min(valeurs)
	if regle == MOYENNE:
		return sum(valeurs) / len(valeurs)
	return max(valeurs)


def cle_numero(numero):
	"""« 1.17.1 » → ((0, 1), (0, 17), (0, 1)) : ordre naturel ; une ligne sans numéro (en cours de saisie) va à la fin."""
	texte = str(numero or "").replace(" ", "")
	if not texte:
		return ((2, ""),)
	return tuple((0, int(x)) if x.isdigit() else (1, x) for x in texte.split("."))


def libelle_parts(parts, libelles):
	"""« RT (50 %), DMOS (50 %) » : prestations d'une ligne avec leur part quand il y en a plusieurs."""
	return ", ".join(f"{libelles.get(e, e)}" + (f" ({round(f * 100)} %)" if len(parts) > 1 else "") for e, f in parts) or None
