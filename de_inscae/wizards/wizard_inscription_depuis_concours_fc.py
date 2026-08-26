from odoo import models, fields, api

class WizardInscriptionConcoursFC(models.TransientModel):
    _name = 'de_inscae.wizard_inscription_concours_fc'
    _description = "Wizard Inscription depuis Concours FC"

    session_calendrier_fc_id = fields.Many2one(
        'de_inscae.session_calendrier_fc',
        string="Session", required=True, ondelete='cascade'
    )
    candidat_ids = fields.Many2many(
        'de_inscae.candidat_concours',
        'wizard_inscription_concours_fc_candidat_rel',
        'wizard_id', 'candidat_id',
        string="Candidats à inscrire",
    )

    @api.onchange('session_calendrier_fc_id')
    def _onchange_session(self):
        if not self.session_calendrier_fc_id:
            self.candidat_ids = False
            return {'domain': {'candidat_ids': [('id', '=', False)]}}

        session_cal = self.session_calendrier_fc_id.session_calendrier_id
        concours_ids = self.env['de_inscae.concours'].search([
            ('session_calendrier_id', '=', session_cal.id),
            ('formation_id.sigle', '=', 'FC'),
        ])
        if not concours_ids:
            self.candidat_ids = False
            return {'domain': {'candidat_ids': [('id', '=', False)]}}

        deja_inscrits_individu_ids = self.env['de_inscae.etudiant_session_fc'].search([
            ('session_calendrier_fc_id', '=', self.session_calendrier_fc_id.id)
        ]).mapped('etudiant_fc_id.etudiant_id.individu_id.id')

        candidats_eligibles = concours_ids.mapped('candidat_ids').filtered(
            lambda c: c.resultat == 'Admis'
            and c.individu_id.id not in deja_inscrits_individu_ids
        )
        return {'domain': {'candidat_ids': [('id', 'in', candidats_eligibles.ids)]}}

    def action_confirmer(self):
        self.ensure_one()
        session_cal = self.session_calendrier_fc_id.session_calendrier_id

        for candidat in self.candidat_ids:
            self.env['de_inscae.etudiant']._verifier_pas_double_inscription(candidat.individu_id.id)

            etudiant_fc = self.env['de_inscae.etudiant_fc'].search([
                ('etudiant_id.individu_id', '=', candidat.individu_id.id)
            ], limit=1)

            if etudiant_fc:
                etudiant_fc.etudiant_id.state = 'actif'
            else:
                etudiant_fi = self.env['de_inscae.etudiant_fi'].search([
                    ('etudiant_id.individu_id', '=', candidat.individu_id.id)
                ], limit=1)

                vals = {
                    'individu_id': candidat.individu_id.id,
                    'formation_id': candidat.concours_id.formation_id.id,
                    'matricule': self.env['de_inscae.etudiant_fc']._generer_matricule(),
                }
                if etudiant_fi:
                    vals['ancien_id'] = etudiant_fi.etudiant_id.id

                etudiant_fc = self.env['de_inscae.etudiant_fc'].create(vals)

            self.env['de_inscae.etudiant_session_fc'].create({
                'etudiant_fc_id': etudiant_fc.id,
                'session_calendrier_fc_id': self.session_calendrier_fc_id.id,
            })

            if not candidat.etudiant_id:
                candidat.etudiant_id = etudiant_fc.etudiant_id.id

        return {'type': 'ir.actions.act_window_close'}


