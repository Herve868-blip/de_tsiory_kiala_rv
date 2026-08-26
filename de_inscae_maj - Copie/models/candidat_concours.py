import re
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class CandidatConcours(models.Model):
    _name = 'de_inscae.candidat_concours'
    _description = "Candidats aux Concours à l'INSCAE"
    _rec_name = 'nom_candidat'

    _sql_constraints = [
        ('individu_concours_unique', 'UNIQUE(individu_id, concours_id)',
         'Cet individu est déjà inscrit à ce concours.'),
    ]

    individu_id = fields.Many2one('de_inscae.individu', string="Individu", required=True, ondelete='cascade')
    concours_id = fields.Many2one('de_inscae.concours', string="Concours", required=True, ondelete='cascade')
    nom_candidat = fields.Char(compute="_compute_nom_complet", string="Nom Complet du Candidat")
    resultat = fields.Selection([
        ('Admis', 'Admis'),
        ('Liste_attente', "Sur la liste d'Attente"),
        ('Refusé', 'Non Admis')
    ], string="Résultat du Concours", default="Admis")

    etudiant_id = fields.Many2one('de_inscae.etudiant', string="Étudiant", copy=False, readonly=True, ondelete="cascade")

    @api.depends('individu_id', 'concours_id')
    def _compute_nom_complet(self):
        for rec in self:
            rec.nom_candidat = f"{rec.individu_id.nom} {rec.individu_id.prenoms}"

    def action_transformer_en_etudiant(self):
        self.ensure_one()

        if self.resultat != 'Admis':
            raise ValidationError("Seul un candidat Admis peut être transformé en étudiant.")
        if self.etudiant_id:
            raise ValidationError("Ce candidat a déjà été transformé en étudiant.")

        formation = self.concours_id.formation_id

        if formation.sigle == 'FI':
            return self._transformer_en_etudiant_fi()
        elif formation.sigle == 'FC':
            return self._transformer_en_etudiant_fc()
        else:
            raise ValidationError(f"Sigle de formation non géré : '{formation.sigle}'.")


    def _transformer_en_etudiant_fi(self):
        self.env['de_inscae.etudiant']._verifier_pas_double_inscription(self.individu_id.id)
        session_calendrier_fi = self.env['de_inscae.session_calendrier_fi'].search([
            ('session_calendrier_id', '=', self.concours_id.session_calendrier_id.id)
        ], limit=1)

        if not session_calendrier_fi:
            raise ValidationError(
                "Aucune session calendrier FI ne correspond à la session de ce concours."
            )

        session_niveau = session_calendrier_fi.session_parente_fi_id.session_niveau_id

        matricule = self.env['de_inscae.etudiant_fi']._generer_matricule()

        etudiant_fi = self.env['de_inscae.etudiant_fi'].create({
            'individu_id': self.individu_id.id,
            'formation_id': self.concours_id.formation_id.id,
            'matricule': matricule,
            'session_niveau_actuelle': session_niveau.id,
        })

        self.env['de_inscae.etudiant_session_fi'].create({
            'etudiant_fi_id': etudiant_fi.id,
            'session_calendrier_fi_id': session_calendrier_fi.id,
        })

        self.etudiant_id = etudiant_fi.etudiant_id.id

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'de_inscae.etudiant_fi',
            'view_mode': 'form',
            'res_id': etudiant_fi.id,
            'target': 'current',
        }


    def _transformer_en_etudiant_fc(self):
        self.ensure_one()
        self.env['de_inscae.etudiant']._verifier_pas_double_inscription(self.individu_id.id)

        session_calendrier_fc = self.env['de_inscae.session_calendrier_fc'].search([
            ('session_calendrier_id', '=', self.concours_id.session_calendrier_id.id)
        ], limit=1)
        if not session_calendrier_fc:
            raise ValidationError(
                "Aucune session calendrier FC ne correspond à la session de ce concours."
            )

        # Vérifier si déjà etudiant_fc
        etudiant_fc = self.env['de_inscae.etudiant_fc'].search([
            ('etudiant_id.individu_id', '=', self.individu_id.id)
        ], limit=1)

        if etudiant_fc:
            # Réintégration — remettre actif
            etudiant_fc.etudiant_id.state = 'actif'
        else:
            # Vérifier si vient du FI
            etudiant_fi = self.env['de_inscae.etudiant_fi'].search([
                ('etudiant_id.individu_id', '=', self.individu_id.id)
            ], limit=1)

            matricule = self.env['de_inscae.etudiant_fc']._generer_matricule()
            vals = {
                'individu_id': self.individu_id.id,
                'formation_id': self.concours_id.formation_id.id,
                'matricule': matricule,
            }
            if etudiant_fi:
                vals['ancien_id'] = etudiant_fi.etudiant_id.id

            etudiant_fc = self.env['de_inscae.etudiant_fc'].create(vals)

        # Inscription à la session
        self.env['de_inscae.etudiant_session_fc'].create({
            'etudiant_fc_id': etudiant_fc.id,
            'session_calendrier_fc_id': session_calendrier_fc.id,
        })

        etudiant_fc.session_calendrier_fc_actuelle_id = session_calendrier_fc.id
        self.etudiant_id = etudiant_fc.etudiant_id.id

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'de_inscae.etudiant_fc',
            'view_mode': 'form',
            'res_id': etudiant_fc.id,
            'target': 'current',
        }