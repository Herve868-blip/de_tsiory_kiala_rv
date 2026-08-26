import re
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class SessionCalendrier(models.Model):
    _name = 'de_inscae.session_calendrier'
    _description = "Calendrier des Sessions à l'INSCAE"
    _rec_name = 'libelle'

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Ce code est déjà utilisé.'),
        ('session_parente_annee_unique', 'UNIQUE(session_parente_id, annee)', 'Un calendrier pour cette session parente et cette année existe déjà.'),
        ('date_range_check', 'CHECK(date_debut < date_fin)', 'La date de début ne peut pas être postérieure ou égale à la date de fin.'),
    ]

    code = fields.Char(string="Code du Calendrier", required=True)
    libelle = fields.Char(string="Libellé du Calendrier", required=True)
    session_parente_id = fields.Many2one('de_inscae.session_parente', string="Session Parente", required=True)
    annee = fields.Integer(string="Année", required=True)
    date_debut = fields.Date(string="Date de Début", required=True)
    date_fin = fields.Date(string="Date de Fin", required=True)
    regle_admission_id = fields.Many2one('de_inscae.regle_admission', string="Règle d'Admission", required=True)
    state = fields.Selection([
        ('planification', 'Planification'),
        ('inscriptions', 'Inscriptions Ouvertes'),
        ('en_cours', 'En Cours'),
        ('deliberation', 'Délibération'),
        ('cloturee', 'Clôturée'),
    ], string="État", default='planification', required=True)
    
    @api.constrains('regle_admission_id')
    def _check_regle_complete(self):
        for rec in self:
            if not rec.regle_admission_id:
                continue
            tous_les_coeffs = self.env['de_inscae.coefficient'].search([])
            coeffs_couverts = rec.regle_admission_id.detail_ids.mapped('coefficient_id')
            coeffs_manquants = tous_les_coeffs - coeffs_couverts
            if coeffs_manquants:
                manquants_str = ', '.join(str(c.coefficient) for c in coeffs_manquants)
                raise ValidationError(
                    "La règle '{}' ne couvre pas tous les coefficients "
                    "existants : {}. Créez une nouvelle règle complète.".format(
                        rec.regle_admission_id.name, manquants_str)
                )
    
    @api.constrains('date_debut', 'date_fin')
    def _check_date_range(self):
        for record in self:
            if record.date_debut >= record.date_fin:
                raise ValidationError("La date de début ne peut pas être postérieure ou égale à la date de fin.")

    @api.onchange('code')
    def _onchange_normalize_code(self):
        if self.code:
            self.code = self.code.upper().replace(' ', '')

    @api.onchange('libelle')
    def _onchange_strip_libelle(self):
        if self.libelle:
            self.libelle = ' '.join(self.libelle.split())

    def action_ouvrir_inscriptions(self):
        self.ensure_one()
        if self.state != 'planification':
            raise ValidationError("La session doit être en Planification pour ouvrir les inscriptions.")
        self.state = 'inscriptions'

    def action_demarrer(self):
        self.ensure_one()
        if self.state != 'inscriptions':
            raise ValidationError("La session doit être en Inscriptions Ouvertes pour démarrer.")
        self.state = 'en_cours'

    def action_deliberer(self):
        self.ensure_one()
        if self.state != 'en_cours':
            raise ValidationError("La session doit être En Cours pour passer en Délibération.")
        self.state = 'deliberation'

    def action_cloturer(self):
        self.ensure_one()
        if self.state != 'deliberation':
            raise ValidationError("La session doit être en Délibération pour être clôturée.")
        self.state = 'cloturee'

    def write(self, vals):
        regle_change = 'regle_admission_id' in vals
        ancienne_regle = {rec.id: rec.regle_admission_id.id for rec in self} if regle_change else {}

        result = super().write(vals)

        if regle_change:
            for rec in self:
                if rec.regle_admission_id.id != ancienne_regle[rec.id]:
                    session_fi = self.env['de_inscae.session_calendrier_fi'].search([
                        ('session_calendrier_id', '=', rec.id)
                    ], limit=1)
                    if session_fi:
                        session_fi._recalculer_tout()

                    session_fc = self.env['de_inscae.session_calendrier_fc'].search([
                        ('session_calendrier_id', '=', rec.id)
                    ], limit=1)
                    if session_fc:
                        session_fc._recalculer_tout()

        return result

class SessionCalendrierFI(models.Model):
    _name = 'de_inscae.session_calendrier_fi'
    _description = "Calendrier des Sessions FI à l'INSCAE"
    _inherits = {'de_inscae.session_calendrier': 'session_calendrier_id'}
    _rec_name = 'libelle'

    session_calendrier_id = fields.Many2one(
        'de_inscae.session_calendrier',
        required=True,
        ondelete='cascade'
    )
    session_parente_fi_id = fields.Many2one(
        'de_inscae.session_parente_fi',
        string="Session Parente FI",
        required=True
    )
    matiere_ids = fields.One2many(
        'de_inscae.session_calendrier_fi_matiere',
        'session_calendrier_fi_id',
        string="Matières"
    )
    groupe_ids = fields.One2many(
        'de_inscae.groupe_fi',
        'session_calendrier_fi_id',
        string="Groupes"
    )
    etudiant_ids = fields.One2many(
        'de_inscae.etudiant_session_fi',
        'session_calendrier_fi_id',
        string="Étudiants Inscrits"
    )
    session_calendrier_fi_prec_id = fields.Many2one(
        'de_inscae.session_calendrier_fi',
        string="Session Précédente",
    )
    session_niveau_precedente_id = fields.Many2one(
        related='session_parente_fi_id.session_niveau_id.session_niveau_precedente_id',
        readonly=True
    )

    _sql_constraints = [
        ('session_calendrier_unique_fi', 'UNIQUE(session_calendrier_id)',
         'Ce calendrier est déjà lié à une session FI.'),
    ]

    def _get_lignes_matieres_pour_session_niveau(self, session_niveau):
        niveau = session_niveau.niveau_id

        # Lignes session_niveau_matiere de la session courante (matière -> coefficient)
        lignes_courantes = session_niveau.matiere_ids
        matieres_courantes = lignes_courantes.mapped('matiere_id')

        autres_sessions = self.env['de_inscae.session_niveau'].search([
            ('niveau_id', '=', niveau.id),
            ('id', '!=', session_niveau.id)
        ])
        # Toutes les lignes session_niveau_matiere des autres sessions du même niveau
        lignes_autres = autres_sessions.mapped('matiere_ids')

        lignes = []

        for ligne in lignes_courantes:
            lignes.append((0, 0, {
                'matiere_id': ligne.matiere_id.id,
                'coefficient_id': ligne.coefficient_id.id,
                'est_selectionnee': True,
            }))

        matieres_deja_ajoutees = matieres_courantes
        for ligne in lignes_autres:
            if ligne.matiere_id not in matieres_deja_ajoutees:
                lignes.append((0, 0, {
                    'matiere_id': ligne.matiere_id.id,
                    'coefficient_id': ligne.coefficient_id.id,
                    'est_selectionnee': False,
                }))
                matieres_deja_ajoutees |= ligne.matiere_id

        return lignes

    @api.onchange('session_parente_fi_id')
    def _onchange_session_parente_fi_id(self):
        if self.session_parente_fi_id:
            self.session_parente_id = self.session_parente_fi_id.session_parente_id
            session_niveau = self.session_parente_fi_id.session_niveau_id

            self.matiere_ids = [(5, 0, 0)] + self._get_lignes_matieres_pour_session_niveau(session_niveau)

            if self.annee:
                self.code = "{}-{}".format(self.session_parente_fi_id.code, self.annee)
                self.libelle = "{} {}".format(self.session_parente_fi_id.libelle, self.annee)

    @api.onchange('annee')
    def _onchange_annee_generate_code(self):
        if self.session_parente_fi_id and self.annee:
            self.code = "{}-{}".format(self.session_parente_fi_id.code, self.annee)
            self.libelle = "{} {}".format(self.session_parente_fi_id.libelle, self.annee)

    @api.model
    def create(self, vals):
        if vals.get('session_parente_fi_id') and not vals.get('session_parente_id'):
            fi = self.env['de_inscae.session_parente_fi'].browse(vals['session_parente_fi_id'])
            vals['session_parente_id'] = fi.session_parente_id.id
        return super().create(vals)

    def write(self, vals):
        if vals.get('session_parente_fi_id'):
            fi = self.env['de_inscae.session_parente_fi'].browse(vals['session_parente_fi_id'])
            vals['session_parente_id'] = fi.session_parente_id.id
        return super().write(vals)

    def unlink(self):
        calendriers = self.mapped('session_calendrier_id')
        result = super().unlink()
        calendriers.unlink()
        return result

    def action_creer_session_suivante(self):
        session_niveau = self.session_parente_fi_id.session_niveau_id

        sessions_niveau_suivantes = self.env['de_inscae.session_niveau'].search([
            ('session_niveau_precedente_id', '=', session_niveau.id)
        ])

        if not sessions_niveau_suivantes:
            raise ValidationError("Aucune session de niveau suivante trouvée.")

        nouveaux_calendriers = self.env['de_inscae.session_calendrier_fi']

        for session_niveau_suivante in sessions_niveau_suivantes:
            session_parente_fi_suivante = self.env['de_inscae.session_parente_fi'].search([
                ('session_niveau_id', '=', session_niveau_suivante.id)
            ], limit=1)

            if not session_parente_fi_suivante:
                continue

            existe = self.env['de_inscae.session_calendrier_fi'].search([
                ('session_parente_fi_id', '=', session_parente_fi_suivante.id),
                ('annee', '=', self.annee)
            ], limit=1)
            if existe:
                continue

            if session_niveau_suivante.niveau_id != session_niveau.niveau_id:
                nouvelle_annee = self.annee + 1
            else:
                nouvelle_annee = self.annee

            mois_debut = int(session_parente_fi_suivante.session_parente_id.mois_debut)
            mois_fin = int(session_parente_fi_suivante.session_parente_id.mois_fin)
            annee_fin = nouvelle_annee + 1 if mois_fin < mois_debut else nouvelle_annee

            date_debut = fields.Date.to_date("{:04d}-{:02d}-01".format(nouvelle_annee, mois_debut))
            date_fin = fields.Date.to_date("{:04d}-{:02d}-01".format(annee_fin, mois_fin))

            if session_niveau_suivante.niveau_id == session_niveau.niveau_id:
                matieres_non_selectionnees = self.matiere_ids.filtered(lambda l: not l.est_selectionnee)
                lignes_matieres = [(0, 0, {
                    'matiere_id': ligne.matiere_id.id,
                    'coefficient_id': ligne.coefficient_id.id,
                    'est_selectionnee': True,
                }) for ligne in matieres_non_selectionnees]
            else:
                lignes_matieres = self._get_lignes_matieres_pour_session_niveau(session_niveau_suivante)

            nouveau = self.env['de_inscae.session_calendrier_fi'].create({
                'session_parente_fi_id': session_parente_fi_suivante.id,
                'annee': nouvelle_annee,
                'code': "{}-{}".format(session_parente_fi_suivante.code, nouvelle_annee),
                'libelle': "{} {}".format(session_parente_fi_suivante.libelle, nouvelle_annee),
                'date_debut': date_debut,
                'date_fin': date_fin,
                'matiere_ids': lignes_matieres,
                'regle_admission_id': self.regle_admission_id.id,
                'session_calendrier_fi_prec_id': self.id
            })
            nouveaux_calendriers |= nouveau

        if not nouveaux_calendriers:
            raise ValidationError("Aucun nouveau calendrier n'a pu être créé (déjà existants ou introuvables).")

        if len(nouveaux_calendriers) == 1:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'de_inscae.session_calendrier_fi',
                'view_mode': 'form',
                'res_id': nouveaux_calendriers.id,
                'target': 'current',
            }
        else:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'de_inscae.session_calendrier_fi',
                'view_mode': 'tree,form',
                'domain': [('id', 'in', nouveaux_calendriers.ids)],
                'target': 'current',
            }

    @api.constrains('session_calendrier_fi_prec_id')
    def _check_session_precedente(self):
        for rec in self:
            if not rec.session_calendrier_fi_prec_id:
                continue

            session_niveau_actuel = rec.session_parente_fi_id.session_niveau_id
            session_niveau_precedent_attendu = session_niveau_actuel.session_niveau_precedente_id

            if not session_niveau_precedent_attendu:
                raise ValidationError(
                    "Cette session de niveau n'a pas de session précédente définie."
                )

            session_niveau_prec_reel = rec.session_calendrier_fi_prec_id.session_parente_fi_id.session_niveau_id

            if session_niveau_prec_reel != session_niveau_precedent_attendu:
                raise ValidationError(
                    "La session précédente doit correspondre au niveau "
                    "'{}'.".format(session_niveau_precedent_attendu.intitule)
                )

    @api.constrains('matiere_ids')
    def _check_demi_matieres_paires(self):
        for rec in self:
            selectionnees = rec.matiere_ids.filtered(lambda l: l.est_selectionnee)
            demi_matieres = selectionnees.mapped('matiere_id').filtered('est_demi_matiere')

            if len(demi_matieres) % 2 != 0:
                raise ValidationError("Le nombre de demi-matières sélectionnées doit être pair.")

            traitees = self.env['de_inscae.matiere']
            for demi in demi_matieres:
                if demi in traitees:
                    continue
                compatibles_selectionnees = demi.moities_compatibles_ids & demi_matieres
                if not compatibles_selectionnees:
                    raise ValidationError(
                        "'{}' n'a aucune moitié compatible sélectionnée dans cette session.".format(demi.intitule)
                    )
                traitees |= demi
                traitees |= compatibles_selectionnees[:1]

    @api.constrains('matiere_ids')
    def _check_matieres_non_amovibles(self):
        for rec in self:
            session_niveau = rec.session_parente_fi_id.session_niveau_id
            for ligne in rec.matiere_ids:
                matiere = ligne.matiere_id
                
                appartient_a_cette_session = matiere.session_niveau_ids.filtered(
                    lambda sm: sm.session_niveau_id == session_niveau
                )
                appartient_au_niveau = matiere.session_niveau_ids.filtered(
                    lambda sm: sm.session_niveau_id.niveau_id == session_niveau.niveau_id
                )
    
                # Toute matière sélectionnée doit appartenir au même niveau
                if ligne.est_selectionnee and not appartient_au_niveau:
                    raise ValidationError(
                        "'{}' n'appartient pas au niveau de cette session et ne peut pas être sélectionnée.".format(matiere.intitule)
                    )
    
                if not matiere.est_amovible:
                    if appartient_a_cette_session and not ligne.est_selectionnee:
                        raise ValidationError(
                            "'{}' n'est pas amovible et doit rester sélectionnée dans sa session d'origine.".format(matiere.intitule)
                        )
                    if not appartient_a_cette_session and ligne.est_selectionnee:
                        raise ValidationError(
                            "'{}' n'est pas amovible et ne peut pas être sélectionnée hors de sa session d'origine.".format(matiere.intitule)
                        )

    def _recalculer_tout(self):
        """Recalcule tous les résultats après changement de règle d'admission."""
        self.ensure_one()
        session_cal = self.session_calendrier_id
        regle = session_cal.regle_admission_id
        if not regle:
            raise ValidationError("La session n'a pas de règle d'admission configurée.")

        for groupe in self.groupe_ids:
            matieres_verrouillees = groupe.matiere_prof_ids.filtered(lambda m: m.notes_verrouillees)
            if not matieres_verrouillees:
                continue

            for matiere_prof in matieres_verrouillees:
                matiere_prof._recalculer_notes(session_cal, regle, remplacer_tentatives=True)

            for inscription in groupe.membre_ids:
                if not inscription.note_ids:
                    inscription.write({'moyenne_generale': 0.0, 'resultat_session': 'exclu'})
                    continue

                notes_non_verrouillees = inscription.note_ids.filtered(
                    lambda n: not n.matiere_prof_groupe_fi_id.notes_verrouillees
                )
                if notes_non_verrouillees:
                    continue

                moyenne_generale = groupe._calculer_moyenne_generale(inscription)
                resultat_session = groupe._determiner_resultat_session(
                    inscription, moyenne_generale,
                    regle.moyenne_admission_min,
                    regle.moyenne_deliberation_min
                )

                if resultat_session in ('transfere_fc', 'exclu'):
                    groupe._refuser_notes_en_deliberation(inscription)

                inscription.write({
                    'moyenne_generale': moyenne_generale,
                    'resultat_session': resultat_session,
                })
                inscription._mettre_a_jour_state_etudiant()

    def action_ouvrir_wizard_concours(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'de_inscae.wizard_inscription_concours_fi',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_session_calendrier_fi_id': self.id,
            }
        }

    def action_ouvrir_wizard_precedente(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'de_inscae.wizard_inscription_precedente_fi',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_session_calendrier_fi_id': self.id,
            }
        }

class SessionCalendrierFIMatiere(models.Model):
    _name = 'de_inscae.session_calendrier_fi_matiere'
    _description = "Matières d'un Calendrier FI"

    session_calendrier_fi_id = fields.Many2one(
        'de_inscae.session_calendrier_fi',
        ondelete='cascade'
    )
    name = fields.Char(related='matiere_id.intitule', string="Matière", readonly=True)
    matiere_id = fields.Many2one('de_inscae.matiere', ondelete='cascade')
    coefficient_id = fields.Many2one('de_inscae.coefficient', string='Coefficient', ondelete='cascade', required=True)
    est_selectionnee = fields.Boolean(string="Sélectionnée", default=True)

    _sql_constraints = [
        ('matiere_calendrier_unique', 'UNIQUE(session_calendrier_fi_id, matiere_id)', 'Cette matière est déjà dans ce calendrier.')
    ]

    def write(self, vals):
        if 'est_selectionnee' in vals:
            anciens_etats = {rec.id: rec.est_selectionnee for rec in self}
        
        result = super().write(vals)
        
        if 'est_selectionnee' in vals:
            for rec in self:
                ancien = anciens_etats[rec.id]
                nouveau = vals['est_selectionnee']
                
                if ancien and not nouveau:
                    # Désélectionnée → supprimer les affectations
                    self.env['de_inscae.matiere_prof_groupe_fi'].search([
                        ('session_calendrier_fi_matiere_id', '=', rec.id)
                    ]).unlink()
                
                elif not ancien and nouveau:
                    # Sélectionnée → créer les affectations manquantes pour chaque groupe_fi
                    groupes = self.env['de_inscae.groupe_fi'].search([
                        ('session_calendrier_fi_id', '=', rec.session_calendrier_fi_id.id)
                    ])
                    for groupe in groupes:
                        existant = self.env['de_inscae.matiere_prof_groupe_fi'].search([
                            ('session_calendrier_fi_matiere_id', '=', rec.id),
                            ('groupe_fi_id', '=', groupe.id),
                        ], limit=1)
                        if not existant:
                            self.env['de_inscae.matiere_prof_groupe_fi'].create({
                                'session_calendrier_fi_matiere_id': rec.id,
                                'groupe_fi_id': groupe.id,
                            })
        
        return result


class SessionCalendrierFC(models.Model):
    _name = 'de_inscae.session_calendrier_fc'
    _description = "Calendrier des Sessions FC à l'INSCAE"
    _inherits = {'de_inscae.session_calendrier': 'session_calendrier_id'}
    _rec_name = 'libelle'

    session_calendrier_id = fields.Many2one(
        'de_inscae.session_calendrier',
        required=True,
        ondelete='cascade'
    )
    session_parente_fc_id = fields.Many2one(
        'de_inscae.session_parente_fc',
        string="Session Parente FC",
        required=True
    )
    matiere_dispo_ids = fields.One2many('de_inscae.matiere_dispo_session_fc', 'session_calendrier_fc_id', string="Matières Disponibles")
    groupe_fc_ids = fields.One2many('de_inscae.groupe_fc', 'session_calendrier_fc_id', string="Groupes")
    etudiant_session_fc_ids = fields.One2many('de_inscae.etudiant_session_fc', 'session_calendrier_fc_id', string="Étudiants")

    session_calendrier_fc_prec_id = fields.Many2one(
        'de_inscae.session_calendrier_fc',
        string="Session FC Précédente",
    )
    session_calendrier_fi_prec_ids = fields.Many2many(
        'de_inscae.session_calendrier_fi',
        'session_calendrier_fc_fi_prec',
        'session_fc_id',
        'session_fi_id',
        string="Sessions FI Précédentes (transférés)",
    )

    _sql_constraints = [
        ('session_calendrier_unique_fc', 'UNIQUE(session_calendrier_id)',
         'Ce calendrier est déjà lié à une session FC.'),
    ]

    @api.onchange('session_parente_fc_id')
    def _onchange_session_parente_fc_id(self):
        if self.session_parente_fc_id:
            self.session_parente_id = self.session_parente_fc_id.session_parente_id

    @api.onchange('session_parente_fc_id', 'annee')
    def _onchange_generate_code_libelle(self):
        if self.session_parente_fc_id and self.annee:
            self.code = "{}-{}".format(self.session_parente_fc_id.code, self.annee)
            self.libelle = "{} {}".format(self.session_parente_fc_id.libelle, self.annee)

    def _recalculer_tout(self):
        self.ensure_one()
        session_cal = self.session_calendrier_id
        regle = session_cal.regle_admission_id
        if not regle:
            raise ValidationError("La session n'a pas de règle d'admission configurée.")

        for groupe in self.groupe_fc_ids:
            if not groupe.notes_verrouillees:
                continue

            matiere = groupe.matiere_dispo_session_fc_id.matiere_id
            coefficient = groupe.matiere_dispo_session_fc_id.coefficient_id

            detail = regle.detail_ids.filtered(lambda d: d.coefficient_id == coefficient)
            if not detail:
                continue
            detail = detail[0]

            for membre in groupe.membre_ids:
                moyenne = membre.moyenne
                etudiant = membre.etudiant_session_fc_id.etudiant_fc_id.etudiant_id

                if moyenne >= detail.note_admission:
                    resultat = 'admis'
                elif moyenne >= detail.note_deliberation:
                    resultat = 'deliberation'
                else:
                    resultat = 'refuse'

                membre.write({'resultat': resultat})

                if resultat in ('admis', 'refuse'):
                    self.env['de_inscae.tentative_matiere_etudiant'].search([
                        ('etudiant_id', '=', etudiant.id),
                        ('matiere_id', '=', matiere.id),
                        ('session_calendrier_id', '=', session_cal.id),
                    ]).unlink()
                    self.env['de_inscae.tentative_matiere_etudiant'].create({
                        'etudiant_id': etudiant.id,
                        'matiere_id': matiere.id,
                        'session_calendrier_id': session_cal.id,
                        'prof_id': groupe.prof_id.id if groupe.prof_id else False,
                        'note_finale': moyenne,
                        'est_reussie': resultat == 'admis',
                    })
            for membre in groupe.membre_ids:
                membre.etudiant_session_fc_id._recalculer_resultat_session()

    @api.model
    def create(self, vals):
        if vals.get('session_parente_fc_id') and not vals.get('session_parente_id'):
            fc = self.env['de_inscae.session_parente_fc'].browse(vals['session_parente_fc_id'])
            vals['session_parente_id'] = fc.session_parente_id.id
        return super().create(vals)

    def write(self, vals):
        if vals.get('session_parente_fc_id'):
            fc = self.env['de_inscae.session_parente_fc'].browse(vals['session_parente_fc_id'])
            vals['session_parente_id'] = fc.session_parente_id.id
        return super().write(vals)

    def unlink(self):
        calendriers = self.mapped('session_calendrier_id')
        result = super().unlink()
        calendriers.unlink()
        return result

    def action_ouvrir_wizard_concours_fc(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'de_inscae.wizard_inscription_concours_fc',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_session_calendrier_fc_id': self.id}
        }
    
    def action_ouvrir_wizard_precedente_fc(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'de_inscae.wizard_inscription_precedente_fc',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_session_calendrier_fc_id': self.id}
        }
    
    def action_ouvrir_wizard_transfere_fi(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'de_inscae.wizard_inscription_transfere_fi',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_session_calendrier_fc_id': self.id}
        }

class MatiereDispoSessionFC(models.Model):
    _name = 'de_inscae.matiere_dispo_session_fc'
    _description = "Matières disponibles pour une Session FC"
    _rec_name = 'matiere_id'

    session_calendrier_fc_id = fields.Many2one('de_inscae.session_calendrier_fc', string="Session Calendrier FC", required=True, ondelete='cascade')
    matiere_id = fields.Many2one('de_inscae.matiere', string="Matière", required=True, ondelete='cascade')
    coefficient_id = fields.Many2one('de_inscae.coefficient', string="Coefficient", required=True)

    _sql_constraints = [
        ('matiere_session_fc_unique', 'UNIQUE(matiere_id, session_calendrier_fc_id)',
         'Cette matière est déjà disponible dans cette session FC.'),
    ]

    def _get_coefficient_licence(self, matiere_id):
        snm = self.env['de_inscae.session_niveau_matiere'].search([
            ('matiere_id', '=', matiere_id),
            ('session_niveau_id.niveau_id.formation_id.parcours_academique_id.code', '=', 'L'),
        ], limit=1)
        if not snm:
            matiere = self.env['de_inscae.matiere'].browse(matiere_id)
            raise ValidationError(
                "La matière '{}' n'appartient à aucune session de niveau "
                "du parcours Licence — elle ne peut pas être ajoutée à une session FC.".format(matiere.intitule)
            )
        return snm.coefficient_id

    @api.onchange('matiere_id')
    def _onchange_matiere_id(self):
        if self.matiere_id:
            try:
                self.coefficient_id = self._get_coefficient_licence(self.matiere_id.id)
            except ValidationError:
                self.coefficient_id = False

    @api.model
    def create(self, vals):
        if vals.get('matiere_id') and not vals.get('coefficient_id'):
            coeff = self._get_coefficient_licence(vals['matiere_id'])
            vals['coefficient_id'] = coeff.id
        return super().create(vals)

    def write(self, vals):
        if vals.get('matiere_id') and not vals.get('coefficient_id'):
            coeff = self._get_coefficient_licence(vals['matiere_id'])
            vals['coefficient_id'] = coeff.id
        return super().write(vals)

    @api.constrains('matiere_id')
    def _check_matiere_licence(self):
        for rec in self:
            self._get_coefficient_licence(rec.matiere_id.id)