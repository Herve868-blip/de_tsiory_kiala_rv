from odoo import models, fields, api

class WizardInscriptionPrecedenteFI(models.TransientModel):
    _name = 'de_inscae.wizard_inscription_precedente_fi'
    _description = "Wizard Inscription depuis Session Précédente FI"

    session_calendrier_fi_id = fields.Many2one(
        'de_inscae.session_calendrier_fi',
        string="Session", required=True, ondelete='cascade'
    )
    etudiant_session_ids = fields.Many2many(
        'de_inscae.etudiant_session_fi',
        'wizard_inscription_precedente_fi',
        'wizard_id',
        'etudiant_session_id',
        string="Étudiants à inscrire",
    )

    @api.onchange('session_calendrier_fi_id')
    def _onchange_session(self):
        if not self.session_calendrier_fi_id:
            self.etudiant_session_ids = False
            return

        session_prec = self.session_calendrier_fi_id.session_calendrier_fi_prec_id
        if not session_prec:
            self.etudiant_session_ids = False
            return

        # Admis de la session précédente pas encore inscrits à la session courante
        deja_inscrits = self.env['de_inscae.etudiant_session_fi'].search([
            ('session_calendrier_fi_id', '=', self.session_calendrier_fi_id.id)
        ]).mapped('etudiant_fi_id')

        eligibles = self.env['de_inscae.etudiant_session_fi'].search([
            ('session_calendrier_fi_id', '=', session_prec.id),
            ('resultat_session', 'in', ('admis', 'admis_ap_deliberation')),
            ('etudiant_fi_id.etudiant_id.state', '=', 'actif'),
            ('etudiant_fi_id', 'not in', deja_inscrits.ids),
        ])

        return {'domain': {'etudiant_session_ids': [('id', 'in', eligibles.ids)]}}

    def action_confirmer(self):
        self.ensure_one()
        session_niveau = self.session_calendrier_fi_id.session_parente_fi_id.session_niveau_id

        for inscription_prec in self.etudiant_session_ids:
            etudiant_fi = inscription_prec.etudiant_fi_id

            # Mettre à jour session_niveau_actuelle
            etudiant_fi.session_niveau_actuelle = session_niveau.id

            # Inscrire à la nouvelle session
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