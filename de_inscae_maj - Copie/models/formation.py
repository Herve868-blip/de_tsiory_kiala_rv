import re
from odoo import models, fields, api
from odoo.exceptions import ValidationError

class Formation(models.Model):
    _name = 'de_inscae.formation'
    _description = "Formations à l'INSCAE"
    _rec_name = 'intitule'

    _sql_constraints = [
        ('sigle_unique', 'UNIQUE(sigle)', 'Ce sigle est déjà utilisé.'),
    ]

    sigle = fields.Char(string="Sigle de la Formation", required=True)
    intitule = fields.Char(string="Intitulé de la Formation", required=True)
    parcours_academique_id = fields.Many2one('de_inscae.parcours_academique', string="Parcours Académique", required=True)

    @api.onchange('sigle')
    def _onchange_normalize_sigle(self):
        if self.sigle:
            self.sigle = self.sigle.upper().replace(' ', '')

    @api.onchange('intitule')
    def _onchange_strip_intitule(self):
        if self.intitule :
            self.intitule = ' '.join(self.intitule.split())