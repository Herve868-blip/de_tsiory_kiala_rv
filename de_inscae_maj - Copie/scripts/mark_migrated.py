etudiants = env['de_inscae.etudiant_fc'].search([])
for e in etudiants:
    a_des_groupes = any(s.groupe_fc_ids for s in e.session_fc_ids)
    a_des_tentatives = bool(e.etudiant_id.tentative_matiere_ids)
    if a_des_tentatives and not a_des_groupes:
        e.est_migre = True
env.cr.commit()