from odoo import models, fields, api
from odoo.exceptions import ValidationError


class Etudiant(models.Model):
    _name = 'de_inscae.etudiant'
    _description = "Etudiant à l'INSCAE"

    individu_id = fields.Many2one('de_inscae.individu', string="Individu", required=True, ondelete='cascade')
    formation_id = fields.Many2one('de_inscae.formation', string="Formation", required=True)
    matricule = fields.Char(string="Matricule", required=True, copy=False)
    ancien_id = fields.Many2one('de_inscae.etudiant', string="Ancien Dossier Étudiant")
    name = fields.Char(string="Etudiant", compute='_compute_name', readonly=True, store=True)
    tentative_matiere_ids = fields.One2many('de_inscae.tentative_matiere_etudiant', 'etudiant_id', string="Tentatives Matières")
    state = fields.Selection([
        ('actif', 'Actif'),
        ('sortant', 'Sortant'),
        ('transfere_fc', 'Transféré en FC'),
        ('exclu', 'Exclu'),
    ], string="Statut", default='actif', required=True)

    @api.depends('individu_id.nom_complet', 'matricule')
    def _compute_name(self):
        for record in self:
            record.name = (" [{}]".format(record.matricule) if record.matricule else '') + " - " + record.individu_id.nom_complet

    _sql_constraints = [
        ('matricule_unique', 'UNIQUE(matricule)', 'Ce matricule est déjà utilisé.'),
        ('ancien_unique', 'UNIQUE(ancien_id)', 'Cet ancien dossier est déjà lié à un autre étudiant.'),
    ]

    @api.model
    def _verifier_pas_double_inscription(self, individu_id):
        deja_inscrit = self.env['de_inscae.etudiant'].search([
            ('individu_id', '=', individu_id),
            ('formation_id.sigle', 'in', ('FI', 'FC')),
            ('state', '=', 'actif'),
        ], limit=1)
        if deja_inscrit:
            individu = self.env['de_inscae.individu'].browse(individu_id)
            raise ValidationError(
                "'{}' est déjà étudiant actif en {}.".format(individu.nom_complet, deja_inscrit.formation_id.sigle)
            )

class TentativeMatiereEtudiant(models.Model):
    _name = 'de_inscae.tentative_matiere_etudiant'
    _description = "Tentative d'un Étudiant à une Matière"

    etudiant_id = fields.Many2one('de_inscae.etudiant', string="Étudiant", required=True, ondelete='cascade')
    matiere_id = fields.Many2one('de_inscae.matiere', string="Matière", required=True, ondelete='cascade')
    session_calendrier_id = fields.Many2one('de_inscae.session_calendrier', string="Session Calendrier", required=True, ondelete='cascade')
    prof_id = fields.Many2one('de_inscae.prof', string="Professeur", ondelete='cascade')
    note_finale = fields.Float(string="Note")
    est_reussie = fields.Boolean(string="Réussie", required=True)

    _sql_constraints = [
        ('etudiant_matiere_session_unique', 'UNIQUE(etudiant_id, matiere_id, session_calendrier_id)',
         'Cet étudiant a déjà une tentative pour cette matière dans cette session.'),
    ]


class EtudiantFI(models.Model):
    _name = 'de_inscae.etudiant_fi'
    _description = "Etudiant FI à l'INSCAE"
    _inherits = {'de_inscae.etudiant': 'etudiant_id'}

    etudiant_id = fields.Many2one('de_inscae.etudiant', required=True, ondelete='cascade')
    session_niveau_actuelle = fields.Many2one('de_inscae.session_niveau', string="Session de Niveau Actuelle", required=True)
    session_fi_ids = fields.One2many('de_inscae.etudiant_session_fi', 'etudiant_fi_id', string="Inscriptions aux Sessions")

    _sql_constraints = [
        ('etudiant_fi_unique', 'UNIQUE(etudiant_id)', 'Cet étudiant est déjà lié à un dossier FI.'),
    ]

    @api.model
    def _generer_matricule(self):
        brut = self.env['ir.sequence'].next_by_code('de_inscae.etudiant.fi')
        if not brut:
            raise ValidationError("La séquence de matricule FI n'est pas configurée.")
        return "{} {}".format(brut[:3], brut[3:])

    def unlink(self):
        etudiant_ids = self.mapped('etudiant_id')
        result = super().unlink()
        etudiant_ids.unlink()
        return result

class EtudiantSessionFI(models.Model):
    _name = 'de_inscae.etudiant_session_fi'
    _description = "Inscription d'un Étudiant FI à une Session Calendrier"

    name = fields.Char(string="Étudiant", related='etudiant_fi_id.name', store=True, readonly=True)
    etudiant_fi_id = fields.Many2one('de_inscae.etudiant_fi', string="Étudiant FI", required=True, ondelete='cascade')
    session_calendrier_fi_id = fields.Many2one('de_inscae.session_calendrier_fi', string="Session Calendrier FI", required=True, ondelete='cascade')
    groupe_fi_id = fields.Many2one(
        'de_inscae.groupe_fi',
        string="Groupe",
        domain="[('session_calendrier_fi_id', '=', session_calendrier_fi_id)]"
    )
    moyenne_generale = fields.Float(string="Moyenne Générale")
    resultat_session = fields.Selection([
        ('admis', 'Admis'),
        ('admis_ap_deliberation', 'Admis après délibération'),
        ('en_attente_deliberation', 'En attente de délibération'),
        ('transfere_fc', 'Transféré en FC'),
        ('exclu', 'Exclu'),
    ], string="Résultat de la Session")
    note_ids = fields.One2many('de_inscae.note_fi', 'etudiant_session_fi_id', string="Notes")

    _sql_constraints = [
        ('etudiant_session_unique', 'UNIQUE(etudiant_fi_id, session_calendrier_fi_id)',
         'Cet étudiant est déjà inscrit à cette session.'),
    ]

    @api.constrains('groupe_fi_id', 'session_calendrier_fi_id')
    def _check_groupe_session_coherence(self):
        for rec in self:
            if rec.groupe_fi_id and rec.groupe_fi_id.session_calendrier_fi_id != rec.session_calendrier_fi_id:
                raise ValidationError(
                    "Le groupe sélectionné n'appartient pas à la session calendrier de cette inscription."
                )

    def write(self, vals):
        result = super().write(vals)
        if 'groupe_fi_id' in vals and vals['groupe_fi_id']:
            for rec in self:
                rec._synchroniser_notes()
        return result

    def _synchroniser_notes(self):
        for rec in self:
            if not rec.groupe_fi_id:
                return
            matieres = rec.groupe_fi_id.matiere_prof_ids
            notes_existantes = rec.note_ids.mapped('matiere_prof_groupe_fi_id')
            for matiere_prof in matieres:
                if matiere_prof not in notes_existantes:
                    self.env['de_inscae.note_fi'].create({
                        'etudiant_session_fi_id': rec.id,
                        'matiere_prof_groupe_fi_id': matiere_prof.id,
                    })

    def action_retirer_du_groupe(self):
        self.ensure_one()
        # Supprimer aussi les notes liées au groupe
        self.env['de_inscae.note_fi'].search([
            ('etudiant_session_fi_id', '=', self.id)
        ]).unlink()
        self.groupe_fi_id = False

    def _finaliser_deliberation_si_complete(self):
        """Déclenche le recalcul si toutes les notes sont tranchées."""
        self.ensure_one()
        notes = self.note_ids
        encore_en_deliberation = notes.filtered(lambda n: n.resultat == 'deliberation')
        if not encore_en_deliberation:
            self._recalculer_resultat_session()

    def _recalculer_resultat_session(self):
        self.ensure_one()
        groupe = self.groupe_fi_id
        regle, admission_min, deliberation_min = groupe._get_regle_et_seuils()
        moyenne_generale = groupe._calculer_moyenne_generale(self)
        resultats = self.note_ids.mapped('resultat')

        a_refuse = 'refuse' in resultats
        a_deliberation = 'deliberation' in resultats
        toutes_ok = not a_refuse and not a_deliberation

        if moyenne_generale >= admission_min:
            if a_refuse:
                resultat_session = 'transfere_fc'
            else:
                resultat_session = 'admis_ap_deliberation'

        elif deliberation_min <= moyenne_generale < admission_min:
            if a_refuse:
                resultat_session = 'exclu'
            else:
                resultat_session = 'en_attente_deliberation'

        else :
            if a_refuse:
                resultat_session = 'exclu'
            else:
                resultat_session = 'en_attente_deliberation'

        self.write({
            'moyenne_generale': moyenne_generale,
            'resultat_session': resultat_session,
        })
        self._mettre_a_jour_state_etudiant()

    peut_jury_decider = fields.Boolean(
        string="Jury peut décider",
        compute='_compute_peut_jury_decider'
    )

    @api.depends('resultat_session', 'note_ids.resultat')
    def _compute_peut_jury_decider(self):
        for rec in self:
            rec.peut_jury_decider = (
                rec.resultat_session == 'en_attente_deliberation'
                and not rec.note_ids.filtered(lambda n: n.resultat == 'deliberation')
                and not rec.note_ids.filtered(lambda n: not n.resultat)
            )

    def action_jury_admettre(self):
        self.ensure_one()
        if self.resultat_session != 'en_attente_deliberation':
            raise ValidationError("Cet étudiant n'est pas en attente de délibération manuelle.")
        self.write({'resultat_session': 'admis_ap_deliberation'})
        self._mettre_a_jour_state_etudiant()

    def action_jury_transferer_fc(self):
        self.ensure_one()
        if self.resultat_session != 'en_attente_deliberation':
            raise ValidationError("Cet étudiant n'est pas en attente de délibération manuelle.")
        self.write({'resultat_session': 'transfere_fc'})
        self._mettre_a_jour_state_etudiant()

    def _mettre_a_jour_state_etudiant(self):
        self.ensure_one()
        etudiant = self.etudiant_fi_id.etudiant_id
        resultat = self.resultat_session
        if resultat == 'exclu':
            etudiant.state = 'exclu'
        elif resultat == 'transfere_fc':
            etudiant.state = 'transfere_fc'
        elif resultat in ('admis', 'admis_ap_deliberation', 'en_attente_deliberation'):
            etudiant.state = 'actif'

class EtudiantFC(models.Model):
    _name = 'de_inscae.etudiant_fc'
    _description = "Etudiant FC à l'INSCAE"
    _inherits = {'de_inscae.etudiant': 'etudiant_id'}

    etudiant_id = fields.Many2one('de_inscae.etudiant', required=True, ondelete='cascade')
    session_fc_ids = fields.One2many('de_inscae.etudiant_session_fc', 'etudiant_fc_id', string="Inscriptions aux Sessions")
    _sql_constraints = [
        ('etudiant_fc_unique', 'UNIQUE(etudiant_id)', 'Cet étudiant est déjà lié à un dossier FC.'),
    ]
    name=fields.Char(string='Nom', compute="_compute_name")
    @api.model
    def _generer_matricule(self):
        brut = self.env['ir.sequence'].next_by_code('de_inscae.etudiant.fc')
        if not brut:
            raise ValidationError("La séquence de matricule FC n'est pas configurée.")
        return "CA {}".format(brut)

    @api.depends('etudiant_id.individu_id.nom_complet', 'matricule')
    def _compute_name(self):
        for record in self:
            record.name = (" [{}]".format(record.etudiant_id.matricule) if record.etudiant_id.matricule else '') + " - " + record.etudiant_id.individu_id.nom_complet


    def unlink(self):
        etudiant_ids = self.mapped('etudiant_id')
        result = super().unlink()
        etudiant_ids.unlink()
        return result

class EtudiantSessionFC(models.Model):
    _name = 'de_inscae.etudiant_session_fc'
    _description = "Inscription d'un Étudiant FC à une Session Calendrier"

    etudiant_fc_id = fields.Many2one('de_inscae.etudiant_fc', string="Étudiant FC", required=True, ondelete='cascade')
    session_calendrier_fc_id = fields.Many2one('de_inscae.session_calendrier_fc', string="Session Calendrier FC", required=True, ondelete='cascade')

    session_libelle = fields.Char(
        string="Session", 
        related='session_calendrier_fc_id.session_calendrier_id.libelle', 
        store=True, 
        readonly=True
    )

    resultat_session = fields.Selection([
        ('admis', 'Admis'),
        ('admis_ap_deliberation', 'Admis après délibération'),
        ('en_attente_deliberation', 'En attente de délibération'),
        ('exclu', 'Exclu'),
    ], string="Résultat de la Session")


    groupe_fc_ids = fields.One2many('de_inscae.etudiant_groupe_fc', 'etudiant_session_fc_id', string="Groupes Matières")
    name = fields.Char(related='etudiant_fc_id.name', store=True, readonly=True)
    tentative_matiere_ids = fields.Many2many(
        'de_inscae.tentative_matiere_etudiant',
        string="Tentatives Matières",
        compute='_compute_tentative_matiere_ids'
    )
    
    
    @api.depends('etudiant_fc_id.etudiant_id.tentative_matiere_ids',
                 'session_calendrier_fc_id.session_calendrier_id')
    def _compute_tentative_matiere_ids(self):
        for rec in self:
            session_cal = rec.session_calendrier_fc_id.session_calendrier_id
            etudiant = rec.etudiant_fc_id.etudiant_id
            rec.tentative_matiere_ids = etudiant.tentative_matiere_ids.filtered(
                lambda t: t.session_calendrier_id == session_cal
            )

    def _calculer_resultat_session(self):
        for rec in self:
            resultats = rec.groupe_fc_ids.mapped('resultat')

            if not resultats:
                rec.resultat_session = 'exclu'
                continue

            a_refuse = 'refuse' in resultats
            a_deliberation = 'deliberation' in resultats
            toutes_admis = all(r == 'admis' for r in resultats)
            toutes_admis_ou_delibere = all(r in ('admis', 'admis_ap_deliberation') for r in resultats)

            if toutes_admis:
                rec.resultat_session = 'admis'
            elif a_refuse:
                rec.resultat_session = 'exclu'
            elif a_deliberation and not a_refuse:
                rec.resultat_session = 'en_attente_deliberation'
            elif toutes_admis_ou_delibere:
                rec.resultat_session = 'admis_ap_deliberation'
            else:
                rec.resultat_session = 'exclu'

    def _finaliser_deliberation_si_complete(self):
        self.ensure_one()
        encore_en_deliberation = self.groupe_fc_ids.filtered(
            lambda g: g.resultat == 'deliberation'
        )
        if not encore_en_deliberation:
            self._recalculer_resultat_session()

    def _recalculer_resultat_session(self):
        self.ensure_one()
        resultats = self.groupe_fc_ids.mapped('resultat')

        if not resultats or any(not r for r in resultats):
            return  # notes pas encore toutes verrouillées

        a_refuse = 'refuse' in resultats
        resultat_session = 'exclu' if a_refuse else 'admis_ap_deliberation'

        self.write({'resultat_session': resultat_session})

    _sql_constraints = [
        ('etudiant_session_fc_unique', 'UNIQUE(etudiant_fc_id, session_calendrier_fc_id)',
         'Cet étudiant est déjà inscrit à cette session.'),
    ]

class EtudiantGroupeFC(models.Model):
    _name = 'de_inscae.etudiant_groupe_fc'
    _description = "Inscription d'un Étudiant FC à un Groupe Matière"
    _rec_name = 'name'

    groupe_fc_id = fields.Many2one('de_inscae.groupe_fc', string="Groupe Matière", required=True, ondelete='cascade')
    etudiant_session_fc_id = fields.Many2one('de_inscae.etudiant_session_fc', string="Étudiant Inscrit", required=True, ondelete='cascade')
    prerequis_issue = fields.Char(string="Prérequis manquants", compute='_compute_prerequis_issue', store=False, readonly=True)
    note_quizz = fields.Float(string="Note Quizz")
    note_intra = fields.Float(string="Note Intra")
    note_examen_final = fields.Float(string="Note Examen Final")
    moyenne = fields.Float(string="Moyenne", compute='_compute_moyenne', store=True)
    resultat = fields.Selection([
        ('admis', 'Admis'),
        ('admis_ap_deliberation', 'Délibéré'),
        ('deliberation', 'En attente de délibération'),
        ('refuse', 'Refusé'),
    ], string="Résultat")
    name = fields.Char(related='etudiant_session_fc_id.name', store=True, readonly=True)
    matiere_id = fields.Many2one(
        related='groupe_fc_id.matiere_dispo_session_fc_id.matiere_id',
        string="Matière", store=False, readonly=True
    )
    prof_id = fields.Many2one(
        related='groupe_fc_id.prof_id',
        string="Professeur", store=False, readonly=True
    )
    _sql_constraints = [
        ('etudiant_groupe_fc_unique', 'UNIQUE(groupe_fc_id, etudiant_session_fc_id)',
         'Cet étudiant est déjà inscrit à ce groupe matière.'),
    ]

    @api.model
    def create(self, vals):
        groupe_fc = self.env['de_inscae.groupe_fc'].browse(vals['groupe_fc_id'])
        etudiant_session = self.env['de_inscae.etudiant_session_fc'].browse(vals['etudiant_session_fc_id'])
        etudiant = etudiant_session.etudiant_fc_id.etudiant_id
        matiere = groupe_fc.matiere_dispo_session_fc_id.matiere_id

        # Vérifier doublon matière dans la même session
        deja_inscrit = self.search([
            ('etudiant_session_fc_id', '=', etudiant_session.id),
            ('groupe_fc_id.matiere_dispo_session_fc_id.matiere_id', '=', matiere.id),
        ], limit=1)
        if deja_inscrit:
            raise ValidationError(
                "'{}' est déjà inscrit à un groupe pour la matière '{}'.".format(etudiant.name, matiere.intitule)
            )

        return super().create(vals)

    def _get_tous_etudiant_ids(self, etudiant):
        ids = [etudiant.id]
        current = etudiant
        while current.ancien_id:
            current = current.ancien_id
            ids.append(current.id)
        return ids

    @api.depends('groupe_fc_id', 'etudiant_session_fc_id')
    def _compute_prerequis_issue(self):
        for rec in self:
            matiere = rec.groupe_fc_id.matiere_dispo_session_fc_id.matiere_id
            matieres_prealables = matiere.matiere_prealable_ids

            if not matieres_prealables:
                rec.prerequis_issue = False
                continue

            etudiant = rec.etudiant_session_fc_id.etudiant_fc_id.etudiant_id
            tous_etudiant_ids = rec._get_tous_etudiant_ids(etudiant)

            tentatives_reussies = self.env['de_inscae.tentative_matiere_etudiant'].search([
                ('etudiant_id', 'in', tous_etudiant_ids),
                ('matiere_id', 'in', matieres_prealables.ids),
                ('est_reussie', '=', True),
            ]).mapped('matiere_id')

            manquantes = matieres_prealables - tentatives_reussies
            rec.prerequis_issue = ', '.join(manquantes.mapped('code')) if manquantes else False

    @api.depends('note_quizz', 'note_intra', 'note_examen_final',
                 'groupe_fc_id.ponderation_quizz',
                 'groupe_fc_id.ponderation_intra',
                 'groupe_fc_id.ponderation_examen_final')
    def _compute_moyenne(self):
        for rec in self:
            g = rec.groupe_fc_id
            rec.moyenne = (
                rec.note_quizz * g.ponderation_quizz
                + rec.note_intra * g.ponderation_intra
                + rec.note_examen_final * g.ponderation_examen_final
            ) / 100.0

    @api.constrains('note_quizz', 'note_intra', 'note_examen_final', 'moyenne')
    def _check_plage_notes(self):
        for rec in self:
            for champ, valeur in [
                ('Quizz', rec.note_quizz),
                ('Intra', rec.note_intra),
                ('Examen Final', rec.note_examen_final),
            ]:
                if valeur < 0 or valeur > 20:
                    raise ValidationError("La note '{}' doit être comprise entre 0 et 20.".format(champ))

    @api.constrains('groupe_fc_id', 'etudiant_session_fc_id')
    def _check_coherence_session(self):
        for rec in self:
            if rec.groupe_fc_id.session_calendrier_fc_id != rec.etudiant_session_fc_id.session_calendrier_fc_id:
                raise ValidationError(
                    "L'étudiant n'est pas inscrit à la même session FC que ce groupe."
                )

    def action_retirer_du_groupe(self):
        self.ensure_one()
        self.unlink()

    def action_admettre_apres_deliberation(self):
        self.ensure_one()
        if self.resultat != 'deliberation':
            raise ValidationError("Cette matière n'est pas en attente de délibération.")
    
        self.write({'resultat': 'admis_ap_deliberation'})
    
        inscription = self.etudiant_session_fc_id
        session_cal = inscription.session_calendrier_fc_id.session_calendrier_id
        etudiant = inscription.etudiant_fc_id.etudiant_id
        matiere = self.groupe_fc_id.matiere_dispo_session_fc_id.matiere_id
    
        self.env['de_inscae.tentative_matiere_etudiant'].search([
            ('etudiant_id', '=', etudiant.id),
            ('matiere_id', '=', matiere.id),
            ('session_calendrier_id', '=', session_cal.id),
        ]).unlink()
    
        self.env['de_inscae.tentative_matiere_etudiant'].create({
            'etudiant_id': etudiant.id,
            'matiere_id': matiere.id,
            'session_calendrier_id': session_cal.id,
            'prof_id': self.groupe_fc_id.prof_id.id if self.groupe_fc_id.prof_id else False,
            'note_finale': self.moyenne,
            'est_reussie': True,
        })
    
        inscription._finaliser_deliberation_si_complete()
    
    def action_refuser_apres_deliberation(self):
        self.ensure_one()
        if self.resultat != 'deliberation':
            raise ValidationError("Cette matière n'est pas en attente de délibération.")
    
        self.write({'resultat': 'refuse'})
    
        inscription = self.etudiant_session_fc_id
        session_cal = inscription.session_calendrier_fc_id.session_calendrier_id
        etudiant = inscription.etudiant_fc_id.etudiant_id
        matiere = self.groupe_fc_id.matiere_dispo_session_fc_id.matiere_id
    
        self.env['de_inscae.tentative_matiere_etudiant'].search([
            ('etudiant_id', '=', etudiant.id),
            ('matiere_id', '=', matiere.id),
            ('session_calendrier_id', '=', session_cal.id),
        ]).unlink()
    
        self.env['de_inscae.tentative_matiere_etudiant'].create({
            'etudiant_id': etudiant.id,
            'matiere_id': matiere.id,
            'session_calendrier_id': session_cal.id,
            'prof_id': self.groupe_fc_id.prof_id.id if self.groupe_fc_id.prof_id else False,
            'note_finale': self.moyenne,
            'est_reussie': False,
        })
    
        inscription._finaliser_deliberation_si_complete()