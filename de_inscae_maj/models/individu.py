import re
from odoo import models, fields, api
from odoo.exceptions import ValidationError

class Individu(models.Model):
    _name = 'de_inscae.individu'
    _description = "Individus INSCAE"
    _rec_name = 'nom_complet'

    _sql_constraints = [
        ('email_unique', 'UNIQUE(email)', 'Cet email est déjà utilisé.'),
    ]

    nom = fields.Char(string="Nom de Famille", required=True)
    prenoms = fields.Char(string="Prénoms")
    nom_complet = fields.Char(compute="_compute_nom_complet")
    est_malagasy = fields.Boolean(string="Est Malagasy", required=True)
    cin = fields.Char(string="Numéro CIN")
    date_naissance = fields.Date(string="Date de Naissance", required=True)
    lieu_naissance = fields.Char(string="Lieu de Naissance", required=True)
    genre = fields.Selection([
        ('M', "Masculin"),
        ('F', 'Féminin')
    ], string='Genre', required=True)
    email = fields.Char(string="Email", required=True)
    adresse = fields.Char(string="Adresse", required=True)
    telephone = fields.Char(string="Numéro de Téléphone", required=True)
    serie_bac = fields.Char(string="Série BAC", required=True)
    mention_bac = fields.Char(string="Mention Obtenue au BAC")
    annee_bac = fields.Integer(string="Année d'Obtention du BAC", required=True)
    centre_bac = fields.Char(string="Centre du BAC", required=True)
    etablissement_origine = fields.Char(string="Établissement d'Obtention du BAC", required=True)
    nom_complet_garant = fields.Char(string="Nom Complet du Garant", required=True)
    telephone_garant = fields.Char(string="Numéro de Téléphone du Garant", required=True)
    adresse_garant = fields.Char(string="Adresse du Garant", required=True)
    etudiant_ids = fields.One2many('de_inscae.etudiant', 'individu_id', string="Parcours en tant qu'Étudiant")

    @api.depends('nom', 'prenoms')
    def _compute_nom_complet(self):
        for rec in self:
            rec.nom_complet = f"{rec.nom} {rec.prenoms if rec.prenoms else ''}"


    @api.onchange('nom', 'prenoms', 'adresse', 'lieu_naissance', 'etablissement_origine',
                  'nom_complet_garant', 'adresse_garant', 'serie_bac', 'mention_bac')
    def _onchange_strip_spaces(self):
        for field in ['nom', 'prenoms', 'adresse', 'lieu_naissance', 'etablissement_origine',
                      'nom_complet_garant', 'adresse_garant', 'serie_bac', 'mention_bac']:
            if self[field]:
                self[field] = ' '.join(self[field].split())


    @api.onchange('telephone', 'telephone_garant')
    def _onchange_remove_spaces_and_normalize(self):
        for field in ['telephone', 'telephone_garant']:
            if self[field]:
                value = self[field].replace(' ', '')
                if value.startswith('+261'):
                    value = '0' + value[4:]
                self[field] = value

    @api.onchange('cin')
    def _onchange_normalize_cin(self):
        if self.cin:
            self.cin = self.cin.replace(' ', '')


    @api.constrains('email')
    def _check_email(self):
        for rec in self:
            if rec.email and not re.fullmatch(r'[\w.+-]+@[\w-]+\.[\w.-]+', rec.email):
                raise ValidationError("L'email est invalide.")

    @api.constrains('telephone', 'telephone_garant')
    def _check_telephones(self):
        for rec in self:
            if rec.telephone and not re.fullmatch(r'(\+261|0)(32|33|34|37|38)\d{7}', rec.telephone):
                raise ValidationError(f"Le numéro de téléphone est invalide.")
            if rec.telephone_garant and not re.fullmatch(r'(\+261|0)(32|33|34|37|38)\d{7}', rec.telephone_garant):
                raise ValidationError(f"Le numéro de téléphone du garant est invalide.")

    @api.constrains('date_naissance')
    def _check_date_naissance(self):
        for rec in self:
            if rec.date_naissance:
                today = fields.Date.today()
                age = (today - rec.date_naissance).days // 365
                if age < 10:
                    raise ValidationError("L'individu doit avoir au moins 10 ans.")

    @api.constrains('annee_bac')
    def _check_annee_bac(self):
        for rec in self:
            if rec.annee_bac and rec.date_naissance:
                if rec.annee_bac < rec.date_naissance.year or rec.annee_bac > fields.Date.today().year:
                    raise ValidationError("L'année d'obtention du BAC ne peut pas être antérieure à l'année de naissance ou postérieure à l'année en cours.")