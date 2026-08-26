from odoo import models, fields, api

class WizardInscriptionConcoursFI(models.TransientModel):
    _name = 'de_inscae.wizard_inscription_concours_fi'
    _description = "Wizard Inscription depuis Concours FI"

    session_calendrier_fi_id = fields.Many2one(
        'de_inscae.session_calendrier_fi',
        string="Session", required=True, ondelete='cascade'
    )
    candidat_ids = fields.Many2many(
        'de_inscae.candidat_concours',
        'wizard_inscription_concours_fi_candidat_rel',
        'wizard_id',
        'candidat_id',
        string="Candidats à inscrire",
    )

    @api.onchange('session_calendrier_fi_id')
    def _onchange_session(self):
        if not self.session_calendrier_fi_id:
            self.candidat_ids = False
            return {'domain': {'candidat_ids': [('id', '=', False)]}}

        session_cal = self.session_calendrier_fi_id.session_calendrier_id
        concours_ids = self.env['de_inscae.concours'].search([
            ('session_calendrier_id', '=', session_cal.id),
            ('formation_id.sigle', '=', 'FI'),
        ])
        if not concours_ids:
            self.candidat_ids = False
            return {'domain': {'candidat_ids': [('id', '=', False)]}}

        deja_inscrits_individu_ids = self.env['de_inscae.etudiant_session_fi'].search([
            ('session_calendrier_fi_id', '=', self.session_calendrier_fi_id.id)
        ]).mapped('etudiant_fi_id.etudiant_id.individu_id.id')

        candidats_eligibles = concours_ids.mapped('candidat_ids').filtered(
            lambda c: c.resultat == 'Admis'
            and c.individu_id.id not in deja_inscrits_individu_ids
        )
        return {'domain': {'candidat_ids': [('id', 'in', candidats_eligibles.ids)]}}

    def action_confirmer(self):
        self.ensure_one()
        session_cal = self.session_calendrier_fi_id.session_calendrier_id
        session_niveau = self.session_calendrier_fi_id.session_parente_fi_id.session_niveau_id

        for candidat in self.candidat_ids:
            self.env['de_inscae.etudiant']._verifier_pas_double_inscription(candidat.individu_id.id)
            if not candidat.etudiant_id:
                matricule = self.env['de_inscae.etudiant_fi']._generer_matricule()
                etudiant_fi = self.env['de_inscae.etudiant_fi'].create({
                    'individu_id': candidat.individu_id.id,
                    'formation_id': candidat.concours_id.formation_id.id,
                    'matricule': matricule,
                    'session_niveau_actuelle': session_niveau.id,
                })
                candidat.etudiant_id = etudiant_fi.etudiant_id.id
            else:
                etudiant_fi = self.env['de_inscae.etudiant_fi'].search([
                    ('etudiant_id', '=', candidat.etudiant_id.id)
                ], limit=1)

            # Inscrire à la session
            already = self.env['de_inscae.etudiant_session_fi'].search([
                ('etudiant_fi_id', '=', etudiant_fi.id),
                ('session_calendrier_fi_id', '=', self.session_calendrier_fi_id.id),
            ], limit=1)
            if not already:
                self.env['de_inscae.etudiant_session_fi'].create({
                    'etudiant_fi_id': etudiant_fi.id,
                    'session_calendrier_fi_id': self.session_calendrier_fi_id.id,
                })

        return {'type': 'ir.actions.act_window_close'}