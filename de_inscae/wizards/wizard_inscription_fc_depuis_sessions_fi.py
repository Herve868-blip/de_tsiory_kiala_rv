from odoo import models, fields, api

class WizardInscriptionTransfereFI(models.TransientModel):
    _name = 'de_inscae.wizard_inscription_transfere_fi'
    _description = "Wizard Inscription Transférés FI vers FC"

    session_calendrier_fc_id = fields.Many2one(
        'de_inscae.session_calendrier_fc',
        string="Session FC", required=True, ondelete='cascade'
    )
    etudiant_session_fi_ids = fields.Many2many(
        'de_inscae.etudiant_session_fi',
        'wizard_inscription_transfere_fi_rel',
        'wizard_id', 'etudiant_session_fi_id',
        string="Étudiants FI transférés à inscrire",
    )

    @api.onchange('session_calendrier_fc_id')
    def _onchange_session(self):
        if not self.session_calendrier_fc_id:
            self.etudiant_session_fi_ids = False
            return

        sessions_fi_prec = self.session_calendrier_fc_id.session_calendrier_fi_prec_ids
        if not sessions_fi_prec:
            self.etudiant_session_fi_ids = False
            return

        deja_inscrits_individu_ids = self.env['de_inscae.etudiant_session_fc'].search([
            ('session_calendrier_fc_id', '=', self.session_calendrier_fc_id.id)
        ]).mapped('etudiant_fc_id.etudiant_id.individu_id.id')

        eligibles = self.env['de_inscae.etudiant_session_fi'].search([
            ('session_calendrier_fi_id', 'in', sessions_fi_prec.ids),
            ('resultat_session', '=', 'transfere_fc'),
            ('etudiant_fi_id.etudiant_id.individu_id', 'not in', deja_inscrits_individu_ids),
        ])
        return {'domain': {'etudiant_session_fi_ids': [('id', 'in', eligibles.ids)]}}

    def action_confirmer(self):
        self.ensure_one()
        for inscription_fi in self.etudiant_session_fi_ids:
            etudiant_fi = inscription_fi.etudiant_fi_id
            individu = etudiant_fi.etudiant_id.individu_id

            self.env['de_inscae.etudiant']._verifier_pas_double_inscription(individu.id)

            # Créer etudiant_fc avec ancien_id
            matricule = self.env['de_inscae.etudiant_fc']._generer_matricule()
            etudiant_fc = self.env['de_inscae.etudiant_fc'].create({
                'individu_id': individu.id,
                'formation_id': self.session_calendrier_fc_id.session_parente_fc_id.session_parente_id.formation_id.id,
                'matricule': matricule,
                'ancien_id': etudiant_fi.etudiant_id.id,
            })

            self.env['de_inscae.etudiant_session_fc'].create({
                'etudiant_fc_id': etudiant_fc.id,
                'session_calendrier_fc_id': self.session_calendrier_fc_id.id,
            })

        return {'type': 'ir.actions.act_window_close'}