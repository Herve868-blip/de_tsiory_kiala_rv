inscriptions = env['de_inscae.etudiant_session_fc'].search([
    ('etudiant_fc_id.est_migre', '=', True),
])
print(f"Nombre d'inscriptions à recalculer : {len(inscriptions)}")
inscriptions = inscriptions.sorted(
    key=lambda i: i.session_calendrier_fc_id.session_calendrier_id.date_debut
)
print(f"Nombre d'inscriptions à recalculer : {len(inscriptions)}")
for inscription in inscriptions:
    try:
        inscription._recalculer_resultat_session()
    except Exception as e:
        print(f"Erreur sur inscription {inscription.id} : {e}")
        env.cr.rollback()

env.cr.commit()