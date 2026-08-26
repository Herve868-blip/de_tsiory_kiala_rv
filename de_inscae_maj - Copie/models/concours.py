import re
from odoo import models, fields, api
from odoo.exceptions import ValidationError

class Concours(models.Model):
    _name = 'de_inscae.concours'
    _description = "Concours à l'INSCAE"
    _rec_name = 'libelle'

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Ce code est déjà utilisé.'),
    ]

    code = fields.Char(string="Code du Concours", required=True)
    libelle = fields.Char(string="Libellé du Concours", required=True)
    formation_id = fields.Many2one('de_inscae.formation', string="Formation", required=True)
    session_calendrier_id = fields.Many2one('de_inscae.session_calendrier', string="Calendrier de Session", required=True, domain="[('session_parente_id.formation_id', '=', formation_id)]", ondelete='cascade')

    candidat_ids = fields.One2many('de_inscae.candidat_concours', 'concours_id', string="Candidats")


    @api.onchange('code')
    def _onchange_normalize_code(self):
        if self.code:
            self.code = self.code.upper().replace(' ', '')

    @api.onchange('libelle')
    def _onchange_strip_libelle(self):
        if self.libelle:
            self.libelle = ' '.join(self.libelle.split())

    @api.constrains('formation_id', 'session_calendrier_id')
    def _check_formation_calendrier(self):
        for rec in self:
            if rec.session_calendrier_id.session_parente_id.formation_id != rec.formation_id:
                raise ValidationError("Le calendrier de session doit appartenir à la formation du concours.")