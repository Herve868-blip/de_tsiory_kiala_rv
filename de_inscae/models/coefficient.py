import re
from odoo import models, fields, api
from odoo.exceptions import ValidationError

class Coefficient(models.Model):
    _name = 'de_inscae.coefficient'
    _description = "Coefficient à l'INSCAE"
    _rec_name = "coefficient"

    coefficient = fields.Float(string='Coefficient', required=True)


class RegleAdmission(models.Model):
    _name = 'de_inscae.regle_admission'
    _description = "Règle d'Admission"
    _rec_name = 'name'

    name = fields.Char(string="Nom de la Règle", required=True)
    moyenne_admission_min = fields.Float(string="Moyenne Générale Minimale", required=True)
    moyenne_deliberation_min = fields.Float(string="Moyenne de Délibération Minimale", required=True)
    detail_ids = fields.One2many('de_inscae.detail_regle_admission', 'regle_admission_id', string="Détails")
    est_verrouillee = fields.Boolean(string="Verrouillée", compute='_compute_est_verrouillee')

    def _compute_est_verrouillee(self):
        for rec in self:
            rec.est_verrouillee = self.env['de_inscae.session_calendrier'].search_count([
                ('regle_admission_id', '=', rec.id)
            ]) > 0

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        coefficients = self.env['de_inscae.coefficient'].search([])
        defaults['detail_ids'] = [(0, 0, {
            'coefficient_id': coeff.id,
            'note_admission': 12.0,
            'note_deliberation': 11.5,
        }) for coeff in coefficients]
        return defaults

    @api.model
    def create(self, vals):
        record = super().create(vals)
        tous_les_coeffs = self.env['de_inscae.coefficient'].search([])
        coeffs_couverts = record.detail_ids.mapped('coefficient_id')
        coeffs_manquants = tous_les_coeffs - coeffs_couverts
        if coeffs_manquants:
            manquants_str = ', '.join(str(c.coefficient) for c in coeffs_manquants)
            raise ValidationError(
                f"La règle doit couvrir tous les coefficients existants. "
                f"Coefficients manquants : {manquants_str}."
            )
        return record

    @api.constrains('moyenne_admission_min', 'moyenne_deliberation_min')
    def _check_moyenne_admission_min(self):
        for rec in self:
            if rec.moyenne_admission_min < 0 or rec.moyenne_admission_min > 20:
                raise ValidationError("La moyenne générale minimale doit être comprise entre 0 et 20.")
            if rec.moyenne_deliberation_min < 0 or rec.moyenne_deliberation_min > 20:
                raise ValidationError("La moyenne de délibération minimale doit être comprise entre 0 et 20.")
            if rec.moyenne_deliberation_min > rec.moyenne_admission_min:
                raise ValidationError(
                    "La moyenne de délibération minimale doit être inférieure ou égale à la moyenne générale minimale."
                )

    def write(self, vals):
        for rec in self:
            if rec.est_verrouillee:
                raise ValidationError(
                    "Cette règle est utilisée par une ou plusieurs sessions "
                    "et ne peut plus être modifiée. Créez une nouvelle règle."
                )
        coeffs_avant = {rec.id: set(rec.detail_ids.mapped('coefficient_id.id')) for rec in self}
        result = super().write(vals)
        if 'detail_ids' in vals:
            for rec in self:
                coeffs_apres = set(rec.detail_ids.mapped('coefficient_id.id'))
                if coeffs_apres != coeffs_avant[rec.id]:
                    raise ValidationError(
                        "Les coefficients de la règle ne peuvent pas être modifiés après création. "
                        "Vous pouvez uniquement modifier les notes d'admission et de délibération."
                    )
        return result

    def unlink(self):
        for rec in self:
            if rec.est_verrouillee:
                raise ValidationError(
                    "Cette règle est utilisée par une ou plusieurs sessions "
                    "et ne peut pas être supprimée."
                )
        return super().unlink()

class DetailRegleAdmission(models.Model):
    _name = 'de_inscae.detail_regle_admission'
    _description = "Détail d'une Règle d'Admission par Coefficient"

    regle_admission_id = fields.Many2one('de_inscae.regle_admission', string="Règle", required=True, ondelete='cascade')
    coefficient_id = fields.Many2one('de_inscae.coefficient', string="Coefficient", required=True)
    note_admission = fields.Float(string="Note d'Admission", required=True)
    note_deliberation = fields.Float(string="Note de Délibération", required=True)

    _sql_constraints = [
        ('coeff_regle_unique', 'UNIQUE(regle_admission_id, coefficient_id)',
         'Ce coefficient est déjà configuré dans cette règle.'),
    ]

    @api.constrains('note_admission', 'note_deliberation')
    def _check_notes(self):
        for rec in self:
            if rec.note_deliberation > rec.note_admission:
                raise ValidationError(
                    "La note de délibération doit être inférieure ou égale à la note d'admission."
                )
            if rec.note_admission < 0 or rec.note_admission > 20:
                raise ValidationError("La note d'admission doit être comprise entre 0 et 20.")
            if rec.note_deliberation < 0 or rec.note_deliberation > 20:
                raise ValidationError("La note de délibération doit être comprise entre 0 et 20.")

    def write(self, vals):
        for rec in self:
            if rec.regle_admission_id.est_verrouillee:
                raise ValidationError(
                    "Cette règle est utilisée par une ou plusieurs sessions "
                    "et ne peut plus être modifiée."
                )
        return super().write(vals)

    def unlink(self):
        for rec in self:
            if rec.regle_admission_id.est_verrouillee:
                raise ValidationError(
                    "Cette règle est utilisée par une ou plusieurs sessions "
                    "et ne peut pas être modifiée."
                )
        return super().unlink()