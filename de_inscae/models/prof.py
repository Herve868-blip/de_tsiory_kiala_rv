import re
from odoo import models, fields, api
from odoo.exceptions import ValidationError

class Prof(models.Model):
    _name = 'de_inscae.prof'
    _description = "Professeur à l'INSCAE"

    nomcomplet = fields.Char(string='Nom Complet', required=True)
    email = fields.Char(string='Email', required=True)
    genre = fields.Selection([
        ('M', "Masculin"),
        ('F', 'Féminin')
    ], string='Genre', required=True)
    telephone = fields.Char(string="Numéro de Téléphone", required=True)
    appellation = fields.Selection([
        ('Mr', "Monsieur"),
        ('Mme', 'Madame'),
        ('Mlle', 'Mademoiselle'),
        ('Pr', 'Professeur'),
        ('Dr', 'Docteur')
    ], string='Appellation', required=True)
    type_prof = fields.Selection([
        ('permanent', "Enseignant Permanent"),
        ('vacataire', "Enseignant Vacataire")
    ], string='Type de Professeur', required=True)

    name = fields.Char(compute='_compute_name', string="Nom Complet avec Appellation", readonly=True)

    @api.depends('appellation', 'nomcomplet')
    def _compute_name(self):
        for rec in self:
            rec.name = "{} {}".format(rec.appellation, rec.nomcomplet) if rec.appellation and rec.nomcomplet else rec.nomcomplet

    @api.constrains('email')
    def _check_email_format(self):
        for rec in self:
            if rec.email and not re.fullmatch(r'[\w.+-]+@[\w-]+\.[\w.-]+', rec.email):
                raise ValidationError("L'email est invalide.")
    
    @api.onchange('nomcomplet')
    def _onchange_strip_spaces(self):
        if self.nomcomplet:
            self.nomcomplet = ' '.join(self.nomcomplet.split())

    @api.onchange('telephone')
    def _onchange_remove_spaces_and_normalize(self):
        for field in ['telephone']:
            if self[field]:
                value = self[field].replace(' ', '')
                if value.startswith('+261'):
                    value = '0' + value[4:]
                self[field] = value

    @api.constrains('telephone')
    def _check_telephones(self):
        for rec in self:
            if rec.telephone and not re.fullmatch(r'(\+261|0)(32|33|34|37|38)\d{7}', rec.telephone):
                raise ValidationError("Le numéro de téléphone est invalide.")

