import re
from odoo import models, fields, api
from odoo.exceptions import ValidationError

class Groupe(models.Model):
    _name = 'de_inscae.groupe'
    _description = "Groupe à l'INSCAE"
    _rec_name = 'nom'

    code = fields.Char(string="Code", required=True)
    nom = fields.Char(string="Nom du Groupe", required=True)
    session_calendrier_id = fields.Many2one('de_inscae.session_calendrier', string="Session du Calendrier", required=True, ondelete='cascade')
    capacite = fields.Integer(string="Capacité du Groupe", required=True)

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Ce code de groupe est déjà utilisé.'),
    ]

    @api.onchange('code')
    def _onchange_delete_spaces(self):
        if self.code:
            self.code = self.code.upper().replace(' ', '')

    @api.onchange('nom')
    def _onchange_strip_spaces(self):
        if self.nom:
            self.nom = ' '.join(self.nom.split())

    @api.constrains('capacite')
    def _check_capacite(self):
        for rec in self:
            if rec.capacite <= 0:
                raise ValidationError("La capacité du groupe doit être un entier positif.")

class GroupeFI(models.Model):
    _name = 'de_inscae.groupe_fi'
    _description = "Groupe FI à l'INSCAE"
    _inherits = {'de_inscae.groupe': 'groupe_id'}
    _rec_name = 'nom'

    groupe_id = fields.Many2one('de_inscae.groupe', string="Groupe", required=True, ondelete='cascade')
    session_calendrier_fi_id = fields.Many2one('de_inscae.session_calendrier_fi', string="Session du Calendrier FI", required=True, ondelete='cascade')
    effectif = fields.Integer(string="Effectif Actuel du Groupe", compute="_compute_effectif")
    matiere_prof_ids = fields.One2many('de_inscae.matiere_prof_groupe_fi', 'groupe_fi_id', string="Matières et Profs")
    membre_ids = fields.One2many('de_inscae.etudiant_session_fi', 'groupe_fi_id', string="Membres")
    notes_toutes_verrouillees = fields.Boolean(
        string="Toutes les notes verrouillées",
        compute="_compute_notes_toutes_verrouillees"
    )

    def _compute_notes_toutes_verrouillees(self):
        for rec in self:
            rec.notes_toutes_verrouillees = (
                bool(rec.matiere_prof_ids)
                and all(m.notes_verrouillees for m in rec.matiere_prof_ids)
            )

    _sql_constraints = [
        ('groupe_fi_unique', 'UNIQUE(groupe_id)', 'Ce groupe FI est déjà lié à un groupe.'),
    ]

    def _compute_effectif(self):
        Inscription = self.env['de_inscae.etudiant_session_fi']
        for rec in self:
            rec.effectif = Inscription.search_count([('groupe_fi_id', '=', rec.id)])

    @api.model
    def create(self, vals):
        if vals.get('session_calendrier_fi_id') and not vals.get('session_calendrier_id'):
            fi = self.env['de_inscae.session_calendrier_fi'].browse(vals['session_calendrier_fi_id'])
            vals['session_calendrier_id'] = fi.session_calendrier_id.id

        record = super().create(vals)
        record._synchroniser_matieres()
        return record

    def action_ajouter_membres(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'de_inscae.wizard_ajout_membre_groupe_fi',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_groupe_fi_id': self.id,
                'default_session_calendrier_fi_id': self.session_calendrier_fi_id.id,
            }
        }

    def _synchroniser_matieres(self):
        for rec in self:
            if not rec.session_calendrier_fi_id:
                continue
            lignes_selectionnees = rec.session_calendrier_fi_id.matiere_ids.filtered('est_selectionnee')
            deja_presentes = rec.matiere_prof_ids.mapped('session_calendrier_fi_matiere_id')
            for ligne in lignes_selectionnees:
                if ligne not in deja_presentes:
                    self.env['de_inscae.matiere_prof_groupe_fi'].create({
                        'groupe_fi_id': rec.id,
                        'ponderation_quizz': 20.0,
                        'ponderation_intra': 30.0,
                        'ponderation_examen_final': 50.0,
                        'session_calendrier_fi_matiere_id': ligne.id,
                    })

    def write(self, vals):
        if vals.get('session_calendrier_fi_id'):
            fi = self.env['de_inscae.session_calendrier_fi'].browse(vals['session_calendrier_fi_id'])
            vals['session_calendrier_id'] = fi.session_calendrier_id.id
        return super().write(vals)

    @api.constrains('session_calendrier_fi_id')
    def _check_formation_fi(self):
        for rec in self:
            if rec.session_calendrier_id.id != rec.session_calendrier_fi_id.session_calendrier_id.id:
                raise ValidationError("La session du calendrier FI doit correspondre à la session du calendrier du groupe.")
            if rec.session_calendrier_fi_id.session_calendrier_id.session_parente_id.formation_id.sigle != 'FI':
                raise ValidationError("La formation de la session du calendrier FI doit être FI.")

    def _get_regle_et_seuils(self):
        """Retourne (regle, admission_min, deliberation_min) pour ce groupe."""
        session_cal = self.session_calendrier_fi_id.session_calendrier_id
        regle = session_cal.regle_admission_id
        if not regle:
            raise ValidationError("La session n'a pas de règle d'admission configurée.")
        return regle, regle.moyenne_admission_min, regle.moyenne_deliberation_min


    def _calculer_moyenne_generale(self, inscription):
        """Calcule et retourne la moyenne générale pondérée d'une inscription."""
        notes = inscription.note_ids
        if not notes:
            return 0.0
        numerateur = sum(
            (n.moyenne or 0.0) * n.matiere_prof_groupe_fi_id.session_calendrier_fi_matiere_id.coefficient_id.coefficient
            for n in notes
        )
        denominateur = sum(
            n.matiere_prof_groupe_fi_id.session_calendrier_fi_matiere_id.coefficient_id.coefficient
            for n in notes
        )
        return numerateur / denominateur if denominateur else 0.0


    def _determiner_resultat_session(self, inscription, moyenne_generale, admission_min, deliberation_min):
        """Détermine le resultat_session selon la moyenne et l'état des notes."""
        notes = inscription.note_ids
        resultats = notes.filtered(lambda n: n.resultat).mapped('resultat')

        a_deliberation = 'deliberation' in resultats
        a_refuse = 'refuse' in resultats

        if moyenne_generale >= admission_min:
            if a_refuse:
                return 'transfere_fc'
            elif a_deliberation:
                return 'en_attente_deliberation'
            else:
                return 'admis'

        elif deliberation_min <= moyenne_generale < admission_min:
            if a_refuse:
                return 'exclu'
            else:
                return 'en_attente_deliberation'

        else:
            if a_refuse or a_deliberation:
                return 'exclu'
            else:
                return 'en_attente_deliberation'


    def _refuser_notes_en_deliberation(self, inscription):
        """Refuse les matières encore en délibération et crée les tentatives."""
        session_cal = self.session_calendrier_fi_id.session_calendrier_id
        for note in inscription.note_ids.filtered(lambda n: n.resultat == 'deliberation'):
            note.write({'resultat': 'refuse'})
            etudiant = inscription.etudiant_fi_id.etudiant_id
            matiere = note.matiere_prof_groupe_fi_id.matiere_id
            deja_existante = self.env['de_inscae.tentative_matiere_etudiant'].search([
                ('etudiant_id', '=', etudiant.id),
                ('matiere_id', '=', matiere.id),
                ('session_calendrier_id', '=', session_cal.id),
            ], limit=1)
            if not deja_existante:
                self.env['de_inscae.tentative_matiere_etudiant'].create({
                    'etudiant_id': etudiant.id,
                    'matiere_id': matiere.id,
                    'session_calendrier_id': session_cal.id,
                    'prof_id': note.matiere_prof_groupe_fi_id.prof_id.id if note.matiere_prof_groupe_fi_id.prof_id else False,
                    'note_finale': note.moyenne,
                    'est_reussie': False,
                })


    def _creer_tentative(self, inscription, note, est_reussie):
        """Crée une tentative_matiere_etudiant pour une note délibérée."""
        session_cal = self.session_calendrier_fi_id.session_calendrier_id
        etudiant = inscription.etudiant_fi_id.etudiant_id
        matiere = note.matiere_prof_groupe_fi_id.matiere_id
        deja_existante = self.env['de_inscae.tentative_matiere_etudiant'].search([
            ('etudiant_id', '=', etudiant.id),
            ('matiere_id', '=', matiere.id),
            ('session_calendrier_id', '=', session_cal.id),
        ], limit=1)
        if not deja_existante:
            self.env['de_inscae.tentative_matiere_etudiant'].create({
                'etudiant_id': etudiant.id,
                'matiere_id': matiere.id,
                'session_calendrier_id': session_cal.id,
                'prof_id': note.matiere_prof_groupe_fi_id.prof_id.id if note.matiere_prof_groupe_fi_id.prof_id else False,
                'note_finale': note.moyenne,
                'est_reussie': est_reussie,
            })


    def action_calculer_moyennes_generales(self):
        self.ensure_one()

        matieres_non_verrouillees = self.matiere_prof_ids.filtered(lambda m: not m.notes_verrouillees)
        if matieres_non_verrouillees:
            noms = ', '.join(matieres_non_verrouillees.mapped('matiere_id.intitule'))
            raise ValidationError(
                "Les notes des matières suivantes ne sont pas encore verrouillées : {}.".format(noms)
            )

        regle, admission_min, deliberation_min = self._get_regle_et_seuils()

        for inscription in self.membre_ids:
            if not inscription.note_ids:
                inscription.write({'moyenne_generale': 0.0, 'resultat_session': 'exclu'})
                continue

            moyenne_generale = self._calculer_moyenne_generale(inscription)
            resultat_session = self._determiner_resultat_session(
                inscription, moyenne_generale, admission_min, deliberation_min
            )

            if resultat_session in ('transfere_fc', 'exclu'):
                self._refuser_notes_en_deliberation(inscription)

            inscription.write({
                'moyenne_generale': moyenne_generale,
                'resultat_session': resultat_session,
            })
            inscription._mettre_a_jour_state_etudiant()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Moyennes calculées',
                'message': "Moyennes générales calculées pour {} étudiant(s).".format(len(self.membre_ids)),
                'type': 'success',
                'sticky': False,
            }
        }
    
class MatiereProfGroupeFI(models.Model):
    _name = 'de_inscae.matiere_prof_groupe_fi'
    _description = "Affectation Prof/Matière pour un Groupe FI"

    name = fields.Char(string="Intitulé", compute="_compute_name")
    groupe_fi_id = fields.Many2one('de_inscae.groupe_fi', string="Groupe FI", required=True, ondelete='cascade')
    session_calendrier_fi_matiere_id = fields.Many2one(
        'de_inscae.session_calendrier_fi_matiere',
        string="Matière de la Session",
        required=True,
        ondelete='cascade',
        domain="[('est_selectionnee', '=', True)]"
    )
    matiere_id = fields.Many2one(related='session_calendrier_fi_matiere_id.matiere_id', string="Matière", store=True, readonly=True)
    prof_id = fields.Many2one('de_inscae.prof', string="Professeur")
    ponderation_quizz = fields.Float(string="Pondération Quizz", default=20.0)
    ponderation_intra = fields.Float(string="Pondération Intra", default=30.0)
    ponderation_examen_final = fields.Float(string="Pondération Examen Final", default=50.0)
    note_ids = fields.One2many('de_inscae.note_fi', 'matiere_prof_groupe_fi_id', string="Notes")
    _sql_constraints = [
        ('groupe_matiere_unique', 'UNIQUE(groupe_fi_id, session_calendrier_fi_matiere_id)',
         'Cette matière est déjà affectée à ce groupe.'),
    ]
    notes_verrouillees = fields.Boolean(string="Notes Verrouillées", default=False)

    @api.depends('groupe_fi_id', 'session_calendrier_fi_matiere_id')
    def _compute_name(self):
        for rec in self:
            if rec.groupe_fi_id and rec.session_calendrier_fi_matiere_id:
                rec.name = "{} - {}".format(rec.groupe_fi_id.nom, rec.session_calendrier_fi_matiere_id.matiere_id.intitule)
            else:
                rec.name = "Affectation Incomplète"
    
    @api.constrains('session_calendrier_fi_matiere_id')
    def _check_matiere_selectionnee(self):
        for rec in self:
            if not rec.session_calendrier_fi_matiere_id.est_selectionnee:
                raise ValidationError(
                    "'{}' n'est pas une matière sélectionnée de la session. "
                    "Seules les matières sélectionnées peuvent être affectées à un groupe.".format(rec.session_calendrier_fi_matiere_id.matiere_id.intitule)
                )

    @api.constrains('groupe_fi_id', 'session_calendrier_fi_matiere_id')
    def _check_coherence_session(self):
        for rec in self:
            if rec.session_calendrier_fi_matiere_id.session_calendrier_fi_id != rec.groupe_fi_id.session_calendrier_fi_id:
                raise ValidationError(
                    "Cette matière n'appartient pas à la même session calendrier que le groupe."
                )

    def action_ouvrir_notes(self):
        self.ensure_one()
        view_id = self.env.ref('de_inscae.view_matiere_prof_groupe_fi_form').id
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'de_inscae.matiere_prof_groupe_fi',
            'view_mode': 'form',
            'res_id': self.id,
            'views': [(view_id, 'form')],
            'target': 'current',
            'context': {
                'default_groupe_fi_id': self.groupe_fi_id.id,
            }
        }

    @api.model
    def create(self, vals):
        record = super().create(vals)
        record._synchroniser_notes_membres()
        return record

    def _synchroniser_notes_membres(self):
        for rec in self:
            membres = self.env['de_inscae.etudiant_session_fi'].search([
                ('groupe_fi_id', '=', rec.groupe_fi_id.id)
            ])
            notes_existantes = self.env['de_inscae.note_fi'].search([
                ('matiere_prof_groupe_fi_id', '=', rec.id)
            ]).mapped('etudiant_session_fi_id')
            for membre in membres:
                if membre not in notes_existantes:
                    self.env['de_inscae.note_fi'].create({
                        'etudiant_session_fi_id': membre.id,
                        'matiere_prof_groupe_fi_id': rec.id,
                    })

    @api.constrains('ponderation_quizz', 'ponderation_intra', 'ponderation_examen_final')
    def _check_ponderation(self):
        for rec in self:
            total = rec.ponderation_quizz + rec.ponderation_intra + rec.ponderation_examen_final
            if abs(total - 100) > 0.01:
                raise ValidationError(
                    "La somme des pondérations pour '{}' doit être égale à 100. "
                    "Actuellement, elle est de {}.".format(rec.matiere_id.intitule, total)
                )

    def _get_detail_regle(self, regle, coeff_pour_regle):
        """Retourne le detail_regle_admission pour un coefficient donné."""
        detail = regle.detail_ids.filtered(lambda d: d.coefficient_id == coeff_pour_regle)
        if not detail:
            raise ValidationError(
                "Aucune règle d'admission trouvée pour le coefficient {}.".format(coeff_pour_regle.coefficient)
            )
        return detail[0]

    def _get_moitie_mpgfi(self):
        """Retourne le MatiereProfGroupeFI de la moitié compatible, avec validations."""
        matiere = self.session_calendrier_fi_matiere_id.matiere_id
        coefficient = self.session_calendrier_fi_matiere_id.coefficient_id

        moitie_mpgfi = self.env['de_inscae.matiere_prof_groupe_fi'].search([
            ('groupe_fi_id', '=', self.groupe_fi_id.id),
            ('matiere_id', 'in', matiere.moities_compatibles_ids.ids),
            ('id', '!=', self.id),
        ], limit=1)

        if not moitie_mpgfi:
            raise ValidationError(
                "Aucune matière moitié compatible trouvée pour '{}' dans ce groupe.".format(matiere.intitule)
            )
        if moitie_mpgfi.session_calendrier_fi_matiere_id.coefficient_id != coefficient:
            raise ValidationError(
                "Les deux moitiés '{}' et "
                "'{}' doivent avoir le même coefficient.".format(matiere.intitule, moitie_mpgfi.matiere_id.intitule)
            )

        coeff_combine = self.env['de_inscae.coefficient'].search([
            ('coefficient', '=', coefficient.coefficient * 2)
        ], limit=1)
        if not coeff_combine:
            raise ValidationError(
                "Le coefficient combiné {} "
                "(= {} + {}) "
                "n'existe pas dans la table des coefficients.".format(coefficient.coefficient * 2, coefficient.coefficient, coefficient.coefficient)
            )

        return moitie_mpgfi, coeff_combine

    def _get_coeff_et_moitie(self):
        matiere = self.session_calendrier_fi_matiere_id.matiere_id
        coefficient = self.session_calendrier_fi_matiere_id.coefficient_id

        if not matiere.est_demi_matiere:
            return coefficient, None

        moitie_mpgfi, coeff_combine = self._get_moitie_mpgfi()
        if moitie_mpgfi.notes_verrouillees:
            return coeff_combine, moitie_mpgfi
        return None, None  # moitié pas encore verrouillée

    def _calculer_moyenne_effective(self, note, moitie_mpgfi):
        """
        Retourne la moyenne effective d'une note.
        Pour une demi-matière verrouillée : moyenne combinée des deux moitiés.
        """
        if moitie_mpgfi:
            note_moitie = moitie_mpgfi.note_ids.filtered(
                lambda n: n.etudiant_session_fi_id == note.etudiant_session_fi_id
            )
            if not note_moitie:
                raise ValidationError(
                    "Note manquante pour la moitié compatible de "
                    "'{}'.".format(self.session_calendrier_fi_matiere_id.matiere_id.intitule)
                )
            return (note.moyenne + note_moitie[0].moyenne) / 2.0, note_moitie[0]
        return note.moyenne, None

    def _appliquer_resultat_note(self, note, resultat, moyenne_effective, session_cal, creer_tentative=True):
        """Écrit le résultat sur la note et crée la tentative si tranché."""
        matiere = self.session_calendrier_fi_matiere_id.matiere_id
        note.write({'resultat': resultat})
        if creer_tentative and resultat in ('admis', 'refuse'):
            etudiant = note.etudiant_session_fi_id.etudiant_fi_id.etudiant_id
            self._creer_ou_remplacer_tentative(
                etudiant, matiere, session_cal,
                self.prof_id, moyenne_effective, resultat == 'admis'
            )

    def _creer_ou_remplacer_tentative(self, etudiant, matiere, session_cal, prof, note_finale, est_reussie, remplacer=False):
        """Crée une tentative, avec option de suppression préalable."""
        existante = self.env['de_inscae.tentative_matiere_etudiant'].search([
            ('etudiant_id', '=', etudiant.id),
            ('matiere_id', '=', matiere.id),
            ('session_calendrier_id', '=', session_cal.id),
        ], limit=1)

        if existante:
            if remplacer:
                existante.unlink()
            else:
                raise ValidationError(
                    "Une tentative existe déjà pour '{}' "
                    "et l'étudiant '{}' dans cette session.".format(matiere.intitule, etudiant.name)
                )

        self.env['de_inscae.tentative_matiere_etudiant'].create({
            'etudiant_id': etudiant.id,
            'matiere_id': matiere.id,
            'session_calendrier_id': session_cal.id,
            'prof_id': prof.id if prof else False,
            'note_finale': note_finale,
            'est_reussie': est_reussie,
        })

    def _determiner_resultat_note(self, moyenne_effective, detail):
        """Retourne le résultat d'une note selon les seuils."""
        if moyenne_effective >= detail.note_admission:
            return 'admis'
        elif moyenne_effective >= detail.note_deliberation:
            return 'deliberation'
        return 'refuse'

    def _recalculer_notes(self, session_cal, regle, remplacer_tentatives=False):
        coeff_pour_regle, moitie_mpgfi = self._get_coeff_et_moitie()

        if self.matiere_id.est_demi_matiere and not moitie_mpgfi:
            return

        detail = self._get_detail_regle(regle, coeff_pour_regle)

        for note in self.note_ids:
            moyenne = (
                (note.note_quizz or 0.0) * self.ponderation_quizz
                + (note.note_intra or 0.0) * self.ponderation_intra
                + (note.note_examen_final or 0.0) * self.ponderation_examen_final
            ) / 100.0
            note.write({'moyenne': moyenne})

            moyenne_effective, note_moitie = self._calculer_moyenne_effective(note, moitie_mpgfi)
            etudiant = note.etudiant_session_fi_id.etudiant_fi_id.etudiant_id

            if remplacer_tentatives:
                self.env['de_inscae.tentative_matiere_etudiant'].search([
                    ('etudiant_id', '=', etudiant.id),
                    ('matiere_id', '=', self.matiere_id.id),
                    ('session_calendrier_id', '=', session_cal.id),
                ]).unlink()

            resultat = self._determiner_resultat_note(moyenne_effective, detail)

            if resultat != 'deliberation':
                self._creer_ou_remplacer_tentative(
                    etudiant, self.matiere_id, session_cal,
                    self.prof_id, moyenne_effective,
                    resultat == 'admis',
                    remplacer=remplacer_tentatives,
                )

            note.write({'resultat': resultat})

            if moitie_mpgfi and note_moitie:
                etudiant_moitie = note_moitie.etudiant_session_fi_id.etudiant_fi_id.etudiant_id

                if remplacer_tentatives:
                    self.env['de_inscae.tentative_matiere_etudiant'].search([
                        ('etudiant_id', '=', etudiant_moitie.id),
                        ('matiere_id', '=', moitie_mpgfi.matiere_id.id),
                        ('session_calendrier_id', '=', session_cal.id),
                    ]).unlink()

                resultat_moitie = resultat

                if resultat_moitie != 'deliberation':
                    moitie_mpgfi._creer_ou_remplacer_tentative(
                        etudiant_moitie, moitie_mpgfi.matiere_id, session_cal,
                        moitie_mpgfi.prof_id, moyenne_effective,
                        resultat == 'admis',
                        remplacer=remplacer_tentatives,
                    )

                note_moitie.write({'resultat': resultat_moitie})

    def action_verrouiller_notes(self):
        self.ensure_one()
        if self.notes_verrouillees:
            raise ValidationError("Les notes sont déjà verrouillées.")

        session_cal = self.groupe_fi_id.session_calendrier_fi_id.session_calendrier_id
        regle = session_cal.regle_admission_id
        if not regle or not self.session_calendrier_fi_matiere_id.coefficient_id:
            raise ValidationError("La session n'a pas de règle d'admission configurée.")

        self._recalculer_notes(session_cal, regle, remplacer_tentatives=False)
        self.notes_verrouillees = True

    def write(self, vals):
        ponderation_change = any(
            k in vals for k in ('ponderation_quizz', 'ponderation_intra', 'ponderation_examen_final')
        )
        result = super().write(vals)
        if ponderation_change and self.notes_verrouillees:
            self._recalculer_apres_ponderation()
        return result

    def _recalculer_apres_ponderation(self):
        self.ensure_one()
        session_cal = self.groupe_fi_id.session_calendrier_fi_id.session_calendrier_id
        regle = session_cal.regle_admission_id
        if not regle:
            raise ValidationError("La session n'a pas de règle d'admission configurée.")

        self._recalculer_notes(session_cal, regle, remplacer_tentatives=True)

        groupe = self.groupe_fi_id
        if groupe.notes_toutes_verrouillees:
            regle, admission_min, deliberation_min = groupe._get_regle_et_seuils()
            for inscription in groupe.membre_ids:
                moyenne_generale = groupe._calculer_moyenne_generale(inscription)
                resultat_session = groupe._determiner_resultat_session(
                    inscription, moyenne_generale, admission_min, deliberation_min
                )
                if resultat_session in ('transfere_fc', 'exclu'):
                    groupe._refuser_notes_en_deliberation(inscription)
                inscription.write({
                    'moyenne_generale': moyenne_generale,
                    'resultat_session': resultat_session,
                })
                inscription._mettre_a_jour_state_etudiant()




class GroupeFC(models.Model):
    _name = 'de_inscae.groupe_fc'
    _description = "Groupe FC à l'INSCAE"
    _inherits = {'de_inscae.groupe': 'groupe_id'}
    _rec_name = 'nom'

    groupe_id = fields.Many2one('de_inscae.groupe', string="Groupe", required=True, ondelete='cascade')
    session_calendrier_fc_id = fields.Many2one('de_inscae.session_calendrier_fc', string="Session Calendrier FC", required=True, ondelete='cascade')
    matiere_dispo_session_fc_id = fields.Many2one('de_inscae.matiere_dispo_session_fc', string="Matière de la Session", required=True, domain="[('session_calendrier_fc_id', '=', session_calendrier_fc_id)]")
    prof_id = fields.Many2one('de_inscae.prof', string="Professeur", required=True)
    ponderation_quizz = fields.Float(string="Pondération Quizz", default=20.0, required=True)
    ponderation_intra = fields.Float(string="Pondération Intra", default=30.0, required=True)
    ponderation_examen_final = fields.Float(string="Pondération Examen Final", default=50.0, required=True)
    effectif = fields.Integer(string="Effectif", compute="_compute_effectif")

    membre_ids = fields.One2many('de_inscae.etudiant_groupe_fc', 'groupe_fc_id', string="Membres")
    note_membre_ids = fields.One2many('de_inscae.etudiant_groupe_fc', 'groupe_fc_id', string="Notes")

    _sql_constraints = [
        ('groupe_fc_unique', 'UNIQUE(groupe_id)', 'Ce groupe FC est déjà lié à un groupe.'),
    ]

    def _compute_effectif(self):
        for rec in self:
            rec.effectif = self.env['de_inscae.etudiant_groupe_fc'].search_count([
                ('groupe_fc_id', '=', rec.id)
            ])

    @api.model
    def create(self, vals):
        if vals.get('session_calendrier_fc_id') and not vals.get('session_calendrier_id'):
            fc = self.env['de_inscae.session_calendrier_fc'].browse(vals['session_calendrier_fc_id'])
            vals['session_calendrier_id'] = fc.session_calendrier_id.id
        return super().create(vals)

    def write(self, vals):
        if vals.get('session_calendrier_fc_id'):
            fc = self.env['de_inscae.session_calendrier_fc'].browse(vals['session_calendrier_fc_id'])
            vals['session_calendrier_id'] = fc.session_calendrier_id.id
        return super().write(vals)

    @api.constrains('session_calendrier_fc_id', 'matiere_dispo_session_fc_id')
    def _check_coherence_session(self):
        for rec in self:
            if rec.matiere_dispo_session_fc_id.session_calendrier_fc_id != rec.session_calendrier_fc_id:
                raise ValidationError(
                    "La matière sélectionnée n'appartient pas à la session FC de ce groupe."
                )

    notes_verrouillees = fields.Boolean(string="Notes Verrouillées", default=False)

    def action_verrouiller_notes(self):
        self.ensure_one()

        if self.notes_verrouillees:
            raise ValidationError("Les notes sont déjà verrouillées.")

        session_cal = self.session_calendrier_fc_id.session_calendrier_id
        regle = session_cal.regle_admission_id
        coefficient = self.matiere_dispo_session_fc_id.coefficient_id
        matiere = self.matiere_dispo_session_fc_id.matiere_id

        if not regle or not coefficient:
            raise ValidationError("La session n'a pas de règle d'admission configurée.")

        detail = regle.detail_ids.filtered(lambda d: d.coefficient_id == coefficient)
        if not detail:
            raise ValidationError(
                "Aucune règle d'admission trouvée pour le coefficient {}.".format(coefficient.coefficient)
            )
        detail = detail[0]

        for membre in self.membre_ids:
            moyenne = membre.moyenne 

            if moyenne >= detail.note_admission:
                resultat = 'admis'
            elif moyenne >= detail.note_deliberation:
                resultat = 'deliberation'
            else:
                resultat = 'refuse'

            membre.write({'resultat': resultat})

            if resultat in ('admis', 'refuse'):
                etudiant = membre.etudiant_session_fc_id.etudiant_fc_id.etudiant_id
                deja_existante = self.env['de_inscae.tentative_matiere_etudiant'].search([
                    ('etudiant_id', '=', etudiant.id),
                    ('matiere_id', '=', matiere.id),
                    ('session_calendrier_id', '=', session_cal.id),
                ], limit=1)
                if deja_existante:
                    raise ValidationError(
                    "Une tentative existe déjà pour '{}' "
                    "et l'étudiant '{}' dans cette session.".format(matiere.intitule, etudiant.name)
                    )
                self.env['de_inscae.tentative_matiere_etudiant'].create({
                    'etudiant_id': etudiant.id,
                    'matiere_id': matiere.id,
                    'session_calendrier_id': session_cal.id,
                    'prof_id': self.prof_id.id if self.prof_id else False,
                    'note_finale': moyenne,
                    'est_reussie': resultat == 'admis',
                })

        self.notes_verrouillees = True

        for membre in self.membre_ids:
            membre.etudiant_session_fc_id._calculer_resultat_session()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Notes verrouillées',
                'message': "Notes verrouillées pour {} étudiant(s).".format(len(self.membre_ids)),
                'type': 'success',
                'sticky': False,
            }
        }