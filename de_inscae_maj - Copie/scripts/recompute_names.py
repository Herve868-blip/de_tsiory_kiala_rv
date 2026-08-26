records = env['de_inscae.etudiant'].search([])
for r in records:
    r.etudiant_id._compute_name()
env.cr.commit()