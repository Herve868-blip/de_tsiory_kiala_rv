from odoo import models, fields, api

class WizardInscriptionPrecedenteFC(models.TransientModel):
    _name = 'de_inscae.wizard_inscription_precedente_fc'
    _description = "Wizard Inscription depuis Session FC Précédente"

    session_calendrier_fc_id = fields.Many2one(
        'de_inscae.session_calendrier_fc',
        string="Session", required=True, ondelete='cascade'
    )
    etudiant_session_ids = fields.Many2many(
        'de_inscae.etudiant_session_fc',
        'wizard_inscription_precedente_fc_rel',
        'wizard_id', 'etudiant_session_id',
        string="Étudiants à inscrire",
    )

    @api.onchange('session_calendrier_fc_id')
    def _onchange_session(self):
        if not self.session_calendrier_fc_id:
            self.etudiant_session_ids = False
            return

        session_prec = self.session_calendrier_fc_id.session_calendrier_fc_prec_id
        if not session_prec:
            self.etudiant_session_ids = False
            return

        deja_inscrits = self.env['de_inscae.etudiant_session_fc'].search([
            ('session_calendrier_fc_id', '=', self.session_calendrier_fc_id.id)
        ]).mapped('etudiant_fc_id')

        eligibles = self.env['de_inscae.etudiant_session_fc'].search([
            ('session_calendrier_fc_id', '=', session_prec.id),
            ('resultat_session', 'in', ('admis', 'admis_ap_deliberation')),
            ('etudiant_fc_id', 'not in', deja_inscrits.ids),
        ])
        return {'domain': {'etudiant_session_ids': [('id', 'in', eligibles.ids)]}}

    def action_confirmer(self):
        self.ensure_one()
        for inscription_prec in self.etudiant_session_ids:
            etudiant_fc = inscription_prec.etudiant_fc_id
            already = self.env['de_inscae.etudiant_session_fc'].search([
                ('etudiant_fc_id', '=', etudiant_fc.id),
                ('session_calendrier_fc_id', '=', self.session_calendrier_fc_id.id),
            ], limit=1)
            if not already:
                self.env['de_inscae.etudiant_session_fc'].create({
                    'etudiant_fc_id': etudiant_fc.id,
                    'session_calendrier_fc_id': self.session_calendrier_fc_id.id,
                })
        return {'type': 'ir.actions.act_window_close'}