from odoo import models, fields, api


class WizardAjoutMembreGroupeFI(models.TransientModel):
    _name = 'de_inscae.wizard_ajout_membre_groupe_fi'
    _description = "Wizard Ajout Membre Groupe FI"

    groupe_fi_id = fields.Many2one('de_inscae.groupe_fi', string="Groupe", required=True, ondelete='cascade')
    session_calendrier_fi_id = fields.Many2one('de_inscae.session_calendrier_fi', string="Session", required=True, ondelete='cascade')
    etudiant_session_ids = fields.Many2many(
        'de_inscae.etudiant_session_fi',
        'wizard_ajout_membre_groupe_fi',
        'wizard_id',
        'etudiant_session_id',
        string="Étudiants à ajouter",
        domain="[('session_calendrier_fi_id', '=', session_calendrier_fi_id), ('groupe_fi_id', '=', False)]"
    )

    def action_confirmer(self):
        for inscription in self.etudiant_session_ids:
            inscription.groupe_fi_id = self.groupe_fi_id.id
            inscription._synchroniser_notes()
        return {'type': 'ir.actions.act_window_close'}