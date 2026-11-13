// Calendrier des ressources : liste Ordre de Mission › vue Calendrier.
// UN événement par ressource affectée (pas un par OM) ; couleur : bleu inspecteur, orange véhicule / équipement, vert consommable.
// Événements calculés côté serveur : lsi_inspection/logistique/calendrier.py (evenements).
// Filtres : barre de filtres de la liste (Projet ; « Type », « Pool », « Ressource » de la table Ressources de l'OM).
frappe.views.calendar["Ordre de Mission"] = {
	field_map: {
		start: "start",
		end: "end",
		id: "name",
		title: "title",
		allDay: "all_day",
		convertToUserTz: "convert_to_user_tz",
	},
	get_events_method: "lsi_inspection.logistique.calendrier.evenements",
	options: { editable: false }, // pas de glisser-déposer : les dates se modifient dans le besoin logistique
};
